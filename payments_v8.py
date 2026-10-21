"""Credit top-up via PromptPay QR (Thai QR Payment, EMVCo).

Flow: pick a package → server creates an order and a PromptPay QR for the exact
amount → the order is marked paid → credits are added atomically (once) and
written to credit_ledger.

PAYMENT_MODE decides how "paid" happens:
  simulate (default) — a "simulate payment" endpoint marks the order paid. No money
                       moves. If PROMPTPAY_ID is unset the QR is a demo code that no
                       banking app can pay.
  manual             — the QR pays PROMPTPAY_ID for real; an admin confirms the
                       transfer (POST /api/admin/payments/{id}/confirm).
"""
from __future__ import annotations

import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

PACKAGES = [
    {'id': 'starter', 'name': 'Starter', 'price': 99, 'credits': 100, 'bonus': 0,
     'desc': 'ลองสร้างคลิป AI ~10 คลิป'},
    {'id': 'creator', 'name': 'Creator', 'price': 299, 'credits': 350, 'bonus': 50,
     'desc': 'ทำคอนเทนต์ต่อเนื่อง ~35 คลิป', 'popular': True},
    {'id': 'pro', 'name': 'Pro', 'price': 699, 'credits': 900, 'bonus': 200,
     'desc': 'สายปั้นช่องจริงจัง ~90 คลิป'},
    {'id': 'business', 'name': 'Business', 'price': 1490, 'credits': 2100, 'bonus': 610,
     'desc': 'ทีม / หลายเพจ ~210 คลิป'},
]
PKG = {p['id']: p for p in PACKAGES}
ORDER_TTL_MIN = 15


def _mode() -> str:
    m = os.getenv('PAYMENT_MODE', 'simulate').strip().lower()
    return m if m in ('simulate', 'manual') else 'simulate'


def _promptpay_id() -> str:
    return re.sub(r'\D', '', os.getenv('PROMPTPAY_ID', ''))


# ----------------------------------------------------------------- PromptPay payload
def _tlv(tag: str, value: str) -> str:
    return f'{tag}{len(value):02d}{value}'


def _crc16(data: str) -> str:
    crc = 0xFFFF
    for b in data.encode('ascii'):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f'{crc:04X}'


def promptpay_payload(target: str, amount: float | None) -> str:
    """EMVCo Thai QR for a PromptPay phone (10 digits), national/tax ID (13) or e-wallet (15)."""
    t = re.sub(r'\D', '', target)
    if len(t) == 10 and t.startswith('0'):
        acc = _tlv('01', '0066' + t[1:])
    elif len(t) == 13:
        acc = _tlv('02', t)
    elif len(t) == 15:
        acc = _tlv('03', t)
    else:
        raise ValueError('PROMPTPAY_ID must be a 10-digit phone, 13-digit ID or 15-digit e-wallet')
    merchant = _tlv('00', 'A000000677010111') + acc
    body = (_tlv('00', '01') + _tlv('01', '12' if amount else '11') + _tlv('29', merchant)
            + _tlv('58', 'TH') + _tlv('53', '764') + (_tlv('54', f'{amount:.2f}') if amount else '') + '6304')
    return body + _crc16(body)


def _qr_svg(text: str) -> str:
    try:
        import segno
    except ImportError:  # QR is a convenience; the payload is still returned.
        return ''
    buf = io.BytesIO()
    segno.make(text, error='m').save(buf, kind='svg', scale=6, border=2, dark='#0f172a', light='#ffffff', xmldecl=False, svgns=True)
    return buf.getvalue().decode()


def _mask(pp: str) -> str:
    return pp[:3] + 'x' * max(0, len(pp) - 7) + pp[-4:] if len(pp) >= 8 else pp


class OrderIn(BaseModel):
    package_id: str = Field(min_length=2, max_length=32)


def register(app, *, connect, read, require_user, mutation, now):
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS payment_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ref TEXT NOT NULL UNIQUE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          package_id TEXT NOT NULL, credits INTEGER NOT NULL, amount_thb REAL NOT NULL,
          method TEXT NOT NULL DEFAULT 'promptpay', mode TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('pending','paid','expired','cancelled')),
          created_at TEXT NOT NULL, expires_at TEXT NOT NULL, paid_at TEXT, confirmed_by TEXT);
        CREATE INDEX IF NOT EXISTS idx_payorders_user ON payment_orders(user_id, id);
        CREATE TABLE IF NOT EXISTS credit_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          delta INTEGER NOT NULL, reason TEXT NOT NULL, project_id INTEGER, created_at TEXT NOT NULL);
        ''')

    def _expire_old():
        with connect() as c:
            c.execute("UPDATE payment_orders SET status='expired' WHERE status='pending' AND expires_at<=?", (now(),))

    def _public(o, with_qr=False):
        d = {'id': o['id'], 'ref': o['ref'], 'package_id': o['package_id'],
             'package_name': PKG.get(o['package_id'], {}).get('name', o['package_id']),
             'credits': o['credits'], 'amount_thb': round(o['amount_thb'], 2), 'mode': o['mode'],
             'status': o['status'], 'created_at': o['created_at'], 'expires_at': o['expires_at'], 'paid_at': o['paid_at']}
        if with_qr and o['status'] == 'pending':
            pp = _promptpay_id()
            if pp:
                payload = promptpay_payload(pp, o['amount_thb'])
                d.update(qr_payload=payload, payable=True, payee=_mask(pp),
                         payee_name=os.getenv('PROMPTPAY_NAME', '').strip())
            else:
                payload = f'AAS-DEMO-PAYMENT|{o["ref"]}|THB{o["amount_thb"]:.2f}'
                d.update(qr_payload=payload, payable=False, payee='', payee_name='')
            d['qr_svg'] = _qr_svg(payload)
        return d

    def _credit(c, order, confirmed_by):
        """Mark paid and add credits exactly once (caller holds BEGIN IMMEDIATE)."""
        row = c.execute('SELECT * FROM payment_orders WHERE id=?', (order['id'],)).fetchone()
        if row['status'] == 'paid':
            return False
        late_ok = confirmed_by.startswith('admin:') and row['status'] in ('pending', 'expired')
        if not late_ok and (row['status'] != 'pending' or row['expires_at'] <= now()):
            raise HTTPException(409, 'คำสั่งซื้อนี้หมดอายุหรือถูกยกเลิกแล้ว กรุณาสร้างรายการใหม่')
        c.execute("UPDATE payment_orders SET status='paid', paid_at=?, confirmed_by=? WHERE id=?",
                  (now(), confirmed_by, row['id']))
        c.execute('UPDATE users SET credits=COALESCE(credits,0)+? WHERE id=?', (row['credits'], row['user_id']))
        c.execute('INSERT INTO credit_ledger(user_id,delta,reason,project_id,created_at) VALUES(?,?,?,?,?)',
                  (row['user_id'], row['credits'], f'topup {row["package_id"]} ฿{row["amount_thb"]:.2f} ({row["ref"]})', None, now()))
        return True

    def _owned(oid, uid):
        o = read('SELECT * FROM payment_orders WHERE id=? AND user_id=?', (oid, uid), True)
        if not o:
            raise HTTPException(404, 'ไม่พบคำสั่งซื้อ')
        return o

    @app.get('/api/payments/packages')
    def packages():
        pp = _promptpay_id()
        return {'packages': PACKAGES, 'mode': _mode(), 'payable': bool(pp),
                'clip_cost': int(os.getenv('STUDIO_CLIP_CREDITS', '10') or 10), 'ttl_minutes': ORDER_TTL_MIN}

    @app.post('/api/payments/orders')
    def create_order(body: OrderIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        pkg = PKG.get(body.package_id)
        if not pkg:
            raise HTTPException(400, 'ไม่พบแพ็กเกจนี้')
        mode = _mode()
        amount = float(pkg['price'])
        if mode == 'manual':
            if not _promptpay_id():
                raise HTTPException(503, 'ระบบรับชำระเงินยังไม่ได้ตั้งค่า PromptPay — กรุณาติดต่อผู้ดูแล')
            # Unique satang lets the admin match a bank transfer to this order.
            amount = round(amount + secrets.randbelow(99) / 100 + 0.01, 2)
        _expire_old()
        created = datetime.now(timezone.utc)
        expires = (created + timedelta(minutes=ORDER_TTL_MIN)).isoformat(timespec='seconds')
        ref = 'AAS' + created.strftime('%y%m%d') + secrets.token_hex(3).upper()
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # One open order per user: a new choice replaces the previous QR.
            c.execute("UPDATE payment_orders SET status='cancelled' WHERE user_id=? AND status='pending'", (u['id'],))
            recent = c.execute('SELECT COUNT(*) FROM payment_orders WHERE user_id=? AND created_at>?',
                               (u['id'], (created - timedelta(hours=1)).isoformat(timespec='seconds'))).fetchone()[0]
            if recent >= 20:
                raise HTTPException(429, 'สร้างรายการชำระเงินบ่อยเกินไป กรุณาลองใหม่ภายหลัง')
            cur = c.execute('''INSERT INTO payment_orders(ref,user_id,package_id,credits,amount_thb,mode,status,created_at,expires_at)
                               VALUES(?,?,?,?,?,?,?,?,?)''',
                            (ref, u['id'], pkg['id'], pkg['credits'], amount, mode, 'pending', now(), expires))
            oid = cur.lastrowid
        return _public(read('SELECT * FROM payment_orders WHERE id=?', (oid,), True), with_qr=True)

    @app.get('/api/payments/orders')
    def my_orders(req: Request):
        u = require_user(req)
        _expire_old()
        rows = read('SELECT * FROM payment_orders WHERE user_id=? ORDER BY id DESC LIMIT 20', (u['id'],))
        return {'orders': [_public(r) for r in rows]}

    @app.get('/api/payments/orders/{oid}')
    def order_status(oid: int, req: Request):
        u = require_user(req)
        _expire_old()
        o = _owned(oid, u['id'])
        bal = read('SELECT credits FROM users WHERE id=?', (u['id'],), True)
        return {**_public(o), 'balance': bal['credits'] if bal else 0}

    @app.post('/api/payments/orders/{oid}/cancel')
    def cancel_order(oid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        _owned(oid, u['id'])
        with connect() as c:
            c.execute("UPDATE payment_orders SET status='cancelled' WHERE id=? AND status='pending'", (oid,))
        return {'ok': True}

    @app.post('/api/payments/orders/{oid}/simulate-paid')
    def simulate_paid(oid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if _mode() != 'simulate':
            raise HTTPException(403, 'ระบบอยู่ในโหมดรับเงินจริง — รอผู้ดูแลยืนยันยอดโอน')
        o = _owned(oid, u['id'])
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            added = _credit(c, o, 'simulate')
        bal = read('SELECT credits FROM users WHERE id=?', (u['id'],), True)
        return {**_public(read('SELECT * FROM payment_orders WHERE id=?', (oid,), True)),
                'credited': added, 'balance': bal['credits']}

    # ---------------------------------------------------------------- admin (manual mode)
    def _admin(u):
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')

    @app.get('/api/admin/payments')
    def admin_orders(req: Request, status: str = ''):
        _admin(require_user(req))
        _expire_old()
        q = '''SELECT p.*, u.username, u.email FROM payment_orders p JOIN users u ON u.id=p.user_id'''
        args = ()
        if status in ('pending', 'paid', 'expired', 'cancelled'):
            q += ' WHERE p.status=?'
            args = (status,)
        rows = read(q + ' ORDER BY p.id DESC LIMIT 200', args)
        return {'orders': [{**_public(r), 'username': r['username'], 'email': r['email'], 'confirmed_by': r['confirmed_by']} for r in rows]}

    @app.post('/api/admin/payments/{oid}/confirm')
    def admin_confirm(oid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        _admin(u)
        o = read('SELECT * FROM payment_orders WHERE id=?', (oid,), True)
        if not o:
            raise HTTPException(404, 'ไม่พบคำสั่งซื้อ')
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            added = _credit(c, o, 'admin:' + u['username'])
        return {'ok': True, 'credited': added}
