"""PromptPay credit top-up: payload format, simulate → credits once, ownership, expiry, manual mode."""
import binascii
import sqlite3

import pytest
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


def _reg(c, name):
    r = c.post('/api/register', json={'username': name, 'email': f'{name}@ex.com', 'password': 'SecretPass12345'})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf']}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('PROMPTPAY_ID', raising=False)
    monkeypatch.setenv('PAYMENT_MODE', 'simulate')
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    return c, _reg(c, 'payer'), tmp_path


def test_promptpay_payload_crc():
    from payments_v8 import promptpay_payload
    p = promptpay_payload('081-234-5678', 299)
    assert p.startswith('000201010212') and '0113006681234567858' in p and '5406299.00' in p
    body, crc = p[:-4], p[-4:]
    assert crc == f'{binascii.crc_hqx(body.encode(), 0xFFFF):04X}'
    assert promptpay_payload('1234567890123', None)[10:12] == '11'  # static QR when no amount
    with pytest.raises(ValueError):
        promptpay_payload('123', 10)


def test_simulated_topup_adds_credits_once(client):
    c, h, tmp = client
    me0 = c.get('/api/me').json()['credits']
    pk = c.get('/api/payments/packages').json()
    assert pk['mode'] == 'simulate' and pk['payable'] is False and {p['id'] for p in pk['packages']} >= {'starter', 'creator'}
    o = c.post('/api/payments/orders', headers=h, json={'package_id': 'creator'}).json()
    assert o['status'] == 'pending' and o['amount_thb'] == 299 and o['credits'] == 350
    assert o['payable'] is False and o['qr_payload'].startswith('AAS-DEMO-PAYMENT') and '<svg' in o['qr_svg']
    r = c.post(f'/api/payments/orders/{o["id"]}/simulate-paid', headers=h).json()
    assert r['status'] == 'paid' and r['credited'] is True and r['balance'] == me0 + 350
    # second confirmation is a no-op
    r2 = c.post(f'/api/payments/orders/{o["id"]}/simulate-paid', headers=h).json()
    assert r2['credited'] is False and r2['balance'] == me0 + 350
    assert c.get('/api/me').json()['credits'] == me0 + 350
    db = sqlite3.connect(tmp / 'community.db')
    assert db.execute("SELECT delta FROM credit_ledger WHERE reason LIKE 'topup creator%'").fetchall() == [(350,)]
    hist = c.get('/api/payments/orders').json()['orders']
    assert hist[0]['status'] == 'paid'


def test_new_order_cancels_previous_and_validation(client):
    c, h, _ = client
    assert c.post('/api/payments/orders', headers=h, json={'package_id': 'nope'}).status_code == 400
    a = c.post('/api/payments/orders', headers=h, json={'package_id': 'starter'}).json()
    b = c.post('/api/payments/orders', headers=h, json={'package_id': 'pro'}).json()
    assert c.get(f'/api/payments/orders/{a["id"]}').json()['status'] == 'cancelled'
    assert c.post(f'/api/payments/orders/{a["id"]}/simulate-paid', headers=h).status_code == 409
    assert c.get(f'/api/payments/orders/{b["id"]}').json()['status'] == 'pending'
    # no CSRF → rejected
    assert c.post('/api/payments/orders', json={'package_id': 'pro'}).status_code == 403


def test_other_user_cannot_touch_order(client):
    c, h, _ = client
    o = c.post('/api/payments/orders', headers=h, json={'package_id': 'starter'}).json()
    c.cookies.clear()
    h2 = _reg(c, 'intruder')
    assert c.get(f'/api/payments/orders/{o["id"]}').status_code == 404
    assert c.post(f'/api/payments/orders/{o["id"]}/simulate-paid', headers=h2).status_code == 404


def test_expired_order_cannot_be_paid(client):
    c, h, tmp = client
    o = c.post('/api/payments/orders', headers=h, json={'package_id': 'starter'}).json()
    db = sqlite3.connect(tmp / 'community.db')
    db.execute("UPDATE payment_orders SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (o['id'],)); db.commit()
    assert c.post(f'/api/payments/orders/{o["id"]}/simulate-paid', headers=h).status_code == 409
    assert c.get(f'/api/payments/orders/{o["id"]}').json()['status'] == 'expired'


def test_free_self_topup_is_closed(client):
    c, h, _ = client
    before = c.get('/api/me').json()['credits']
    r = c.post('/api/my/credits/topup', headers=h, json={'package_id': 'x', 'credits': 999})
    assert r.status_code in (410, 422)
    assert c.get('/api/me').json()['credits'] == before


def test_manual_mode_real_qr_and_admin_confirm(tmp_path, monkeypatch):
    monkeypatch.setenv('PAYMENT_MODE', 'manual')
    monkeypatch.setenv('PROMPTPAY_ID', '0812345678')
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    h = _reg(c, 'buyer')
    o = c.post('/api/payments/orders', headers=h, json={'package_id': 'starter'}).json()
    assert o['payable'] is True and o['payee'].endswith('5678') and o['qr_payload'].startswith('000201010212')
    assert 99 < o['amount_thb'] < 100  # unique satang for matching the transfer
    assert c.post(f'/api/payments/orders/{o["id"]}/simulate-paid', headers=h).status_code == 403
    db = sqlite3.connect(tmp_path / 'community.db')
    uid = db.execute("SELECT id FROM users WHERE username='buyer'").fetchone()[0]
    before = db.execute('SELECT credits FROM users WHERE id=?', (uid,)).fetchone()[0]
    db.execute("UPDATE users SET role='admin' WHERE id=?", (uid,)); db.commit()
    assert c.post(f'/api/admin/payments/{o["id"]}/confirm', headers=h).json()['credited'] is True
    assert db.execute('SELECT credits FROM users WHERE id=?', (uid,)).fetchone()[0] == before + 100
    assert c.get('/api/admin/payments?status=paid').json()['orders'][0]['confirmed_by'] == 'admin:buyer'
