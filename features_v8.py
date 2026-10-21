"""V8 features mounted onto the community app.

* Help Center articles + realtime support chat (WebSocket with REST polling fallback)
* Real connectors: Facebook Pages (OAuth), Instagram (via Page or Instagram Login), LINE OA (Messaging API)
* Real Shopee product import via Shopee Affiliate Open API (image, price, commission)
* Publish a product to connected channels
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import (BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from integrations import help_content, line_oa, meta, shopee_affiliate as shopee
from studio_v6 import file_import

OAUTH_STATE_MINUTES = 15
SUPPORT_MAX_LEN = 2000
IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CONFIG_KEYS = {  # key -> env var
    'meta_app_id': 'META_APP_ID', 'meta_app_secret': 'META_APP_SECRET',
    'ig_app_id': 'IG_APP_ID', 'ig_app_secret': 'IG_APP_SECRET',
    'public_base_url': 'PUBLIC_BASE_URL',
}
SECRET_KEYS = {'meta_app_secret', 'ig_app_secret'}


# ------------------------------------------------------------------ request models
class SupportMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=SUPPORT_MAX_LEN)
    thread_id: int | None = Field(default=None, gt=0)


class ThreadStatusIn(BaseModel):
    status: str = Field(pattern=r'^(open|resolved)$')


class IntegrationConfigIn(BaseModel):
    meta_app_id: str | None = Field(default=None, max_length=64)
    meta_app_secret: str | None = Field(default=None, max_length=128)
    ig_app_id: str | None = Field(default=None, max_length=64)
    ig_app_secret: str | None = Field(default=None, max_length=128)
    public_base_url: str | None = Field(default=None, max_length=200)


class ProductPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    offer_link: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, ge=0, le=10_000_000)
    commission_rate: float | None = Field(default=None, ge=0, le=100)
    active: bool | None = None


class BulkDeleteIn(BaseModel):
    source: str = Field(min_length=3, max_length=32)


class FbTokenIn(BaseModel):
    token: str = Field(min_length=40, max_length=1000)


class LineConnectIn(BaseModel):
    channel_id: str = Field(min_length=5, max_length=20)
    channel_secret: str = Field(min_length=16, max_length=64)
    access_token: str | None = Field(default=None, max_length=600)


class TestPostIn(BaseModel):
    message: str = Field(default='', max_length=2000)
    product_id: int | None = Field(default=None, gt=0)
    line_mode: str = Field(default='push', pattern=r'^(push|broadcast)$')
    confirm_broadcast: bool = False


class PublishIn(BaseModel):
    channel_ids: list[int] = Field(min_length=1, max_length=20)
    caption: str = Field(default='', max_length=2000)
    line_mode: str = Field(default='push', pattern=r'^(push|broadcast)$')
    confirm_broadcast: bool = False


class ShopeeCredIn(BaseModel):
    app_id: str = Field(min_length=4, max_length=40)
    secret: str = Field(min_length=8, max_length=128)


class ShopeeLookupIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000)


class ShopeeFetchIn(BaseModel):
    mode: str = Field(default='search', pattern='^(search|category)$')
    keyword: str = Field(default='', max_length=120)
    list_type: str = Field(default='highest_commission', pattern='^(highest_commission|top_performing)$')
    ams_only: bool = True
    sort: str = Field(default='relevance', pattern='^(relevance|sales|commission)$')
    limit: int = Field(default=20, ge=1, le=100)


class ShopeeImportIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=24, pattern=r'^\d+$')
    shop_id: str | None = Field(default=None, max_length=24, pattern=r'^\d*$')


# ------------------------------------------------------------------ realtime hub
class SupportHub:
    def __init__(self):
        self.conns: list[tuple[WebSocket, dict]] = []
        self.lock = asyncio.Lock()

    def admins_online(self) -> int:
        return len({u['id'] for _, u in self.conns if u['role'] == 'admin'})

    async def add(self, ws, user):
        async with self.lock:
            self.conns.append((ws, user))
        await self.presence()

    async def remove(self, ws):
        async with self.lock:
            self.conns = [(w, u) for w, u in self.conns if w is not ws]
        await self.presence()

    async def _send(self, targets, payload):
        dead = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                self.conns = [(w, u) for w, u in self.conns if w not in dead]

    async def to_thread(self, owner_id: int, payload: dict, include_owner=True):
        targets = [w for w, u in self.conns if u['role'] == 'admin' or (include_owner and u['id'] == owner_id)]
        await self._send(targets, payload)

    async def presence(self):
        await self._send([w for w, _ in self.conns], {'type': 'presence', 'admins_online': self.admins_online()})


def register(app: FastAPI, *, connect, read, require_user, mutation, cipher, now, data_dir: Path, public_mode: bool):
    media_dir = (data_dir / 'media' / 'products')
    media_dir.mkdir(parents=True, exist_ok=True)
    hub = SupportHub()
    app.state.support_hub = hub
    throttle: dict[tuple, list[float]] = {}

    # -------------------------------------------------------------- schema / migrations
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS oauth_states (
          state TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          platform TEXT NOT NULL, redirect_uri TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS integration_config (
          key TEXT PRIMARY KEY, value_encrypted TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS line_recipients (
          channel_id INTEGER NOT NULL REFERENCES connected_channels(id) ON DELETE CASCADE,
          line_user_id TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '', last_seen TEXT NOT NULL,
          PRIMARY KEY(channel_id, line_user_id));
        CREATE TABLE IF NOT EXISTS publish_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          channel_id INTEGER, platform TEXT NOT NULL, product_id INTEGER,
          ok INTEGER NOT NULL, external_id TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS publish_log_owner ON publish_log(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS support_threads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
          unread_admin INTEGER NOT NULL DEFAULT 0, unread_user INTEGER NOT NULL DEFAULT 0,
          last_message_at TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS support_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          thread_id INTEGER NOT NULL REFERENCES support_threads(id) ON DELETE CASCADE,
          sender_role TEXT NOT NULL CHECK(sender_role IN ('user','admin','bot')),
          sender_id INTEGER, sender_name TEXT NOT NULL DEFAULT '', body TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS support_messages_thread ON support_messages(thread_id, id);
        ''')
        st_cols = {r[1] for r in db.execute('PRAGMA table_info(oauth_states)')}
        if 'return_tab' not in st_cols:
            db.execute("ALTER TABLE oauth_states ADD COLUMN return_tab TEXT NOT NULL DEFAULT 'connectors'")
        ch_cols = {r[1] for r in db.execute('PRAGMA table_info(connected_channels)')}
        for name, ddl in [('kind', "TEXT NOT NULL DEFAULT 'manual'"), ('meta_json', "TEXT NOT NULL DEFAULT '{}'"),
                          ('secret_encrypted', 'TEXT'), ('token_expires_at', 'TEXT'), ('verified_at', 'TEXT'),
                          ('last_error', "TEXT NOT NULL DEFAULT ''")]:
            if name not in ch_cols:
                db.execute(f'ALTER TABLE connected_channels ADD COLUMN {name} {ddl}')
        p_cols = {r[1] for r in db.execute('PRAGMA table_info(products)')}
        for name, ddl in [('price', 'REAL'), ('price_min', 'REAL'), ('price_max', 'REAL'), ('commission_rate', 'REAL'),
                          ('seller_comm_rate', 'REAL'), ('shopee_comm_rate', 'REAL'), ('commission_baht', 'REAL'),
                          ('image_url', "TEXT NOT NULL DEFAULT ''"), ('image_file', "TEXT NOT NULL DEFAULT ''"),
                          ('shop_name', "TEXT NOT NULL DEFAULT ''"), ('shop_id', "TEXT NOT NULL DEFAULT ''"),
                          ('item_id', "TEXT NOT NULL DEFAULT ''"), ('offer_link', "TEXT NOT NULL DEFAULT ''"),
                          ('product_link', "TEXT NOT NULL DEFAULT ''"), ('sales', 'INTEGER'), ('rating', 'REAL'),
                          ('source', "TEXT NOT NULL DEFAULT 'manual'"), ('synced_at', 'TEXT'),
                          ('active', 'INTEGER NOT NULL DEFAULT 1'), ('discount_rate', 'REAL')]:
            if name not in p_cols:
                db.execute(f'ALTER TABLE products ADD COLUMN {name} {ddl}')
        db.execute('CREATE INDEX IF NOT EXISTS products_item ON products(user_id, item_id)')

    # -------------------------------------------------------------- helpers
    def enc(v: str) -> str:
        return cipher.encrypt(v.encode()).decode()

    def dec(v: str | None) -> str:
        if not v:
            return ''
        try:
            return cipher.decrypt(v.encode()).decode()
        except Exception:
            return ''

    def cfg(key: str) -> str:
        env = os.getenv(CONFIG_KEYS[key], '').strip()
        if env:
            return env
        row = read('SELECT value_encrypted FROM integration_config WHERE key=?', (key,), True)
        return dec(row['value_encrypted']) if row else ''

    def base_url(req: Request) -> str:
        configured = cfg('public_base_url').rstrip('/')
        if configured:
            return configured
        return str(req.base_url).rstrip('/')

    app.state.v8_base_url = lambda req: base_url(req)

    def limit(user_id, bucket, per_minute):
        key = (user_id, bucket)
        t = time.monotonic()
        hits = [x for x in throttle.get(key, []) if t - x < 60]
        if len(hits) >= per_minute:
            raise HTTPException(429, 'เรียกใช้งานถี่เกินไป กรุณารอสักครู่')
        hits.append(t)
        throttle[key] = hits

    def require_admin(req, csrf=None):
        u = require_user(req, csrf) if csrf is not None else require_user(req)
        if u['role'] != 'admin':
            raise HTTPException(403, 'สำหรับผู้ดูแลระบบเท่านั้น')
        return u

    def channel_public(row: dict) -> dict:
        m = {}
        try:
            m = json.loads(row.get('meta_json') or '{}')
        except ValueError:
            pass
        m.pop('webhook_key', None)
        out = {k: row.get(k) for k in ('id', 'platform', 'account_name', 'account_id', 'auto_post_enabled', 'status',
                                      'last_synced_at', 'created_at', 'kind', 'token_expires_at', 'verified_at',
                                      'last_error')}
        out['meta'] = m
        out['has_token'] = bool(row.get('access_token_encrypted'))
        return out

    def own_channel(user_id, channel_id):
        ch = read('SELECT * FROM connected_channels WHERE id=? AND user_id=?', (channel_id, user_id), True)
        if not ch:
            raise HTTPException(404, 'ไม่พบช่องทางนี้ในบัญชีของคุณ')
        return ch

    def upsert_channel(user_id, platform, account_id, account_name, token, *, kind, meta_obj, secret=None,
                       expires_at=None):
        with connect() as c:
            existing = c.execute('SELECT id, meta_json FROM connected_channels WHERE user_id=? AND platform=? AND account_id=?',
                                 (user_id, platform, account_id)).fetchone()
            if existing:
                old = {}
                try:
                    old = json.loads(existing['meta_json'] or '{}')
                except ValueError:
                    pass
                if old.get('webhook_key') and 'webhook_key' not in meta_obj:
                    meta_obj['webhook_key'] = old['webhook_key']
                c.execute('''UPDATE connected_channels SET account_name=?, access_token_encrypted=?, kind=?, meta_json=?,
                             secret_encrypted=COALESCE(?, secret_encrypted), token_expires_at=?, status='connected',
                             verified_at=?, last_synced_at=?, last_error='' WHERE id=?''',
                          (account_name, enc(token), kind, json.dumps(meta_obj, ensure_ascii=False),
                           enc(secret) if secret else None, expires_at, now(), now(), existing['id']))
                return existing['id']
            cur = c.execute('''INSERT INTO connected_channels(user_id, platform, account_name, account_id, access_token_encrypted,
                               auto_post_enabled, status, last_synced_at, created_at, kind, meta_json, secret_encrypted,
                               token_expires_at, verified_at) VALUES (?,?,?,?,?,1,'connected',?,?,?,?,?,?,?)''',
                            (user_id, platform, account_name, account_id, enc(token), now(), now(), kind,
                             json.dumps(meta_obj, ensure_ascii=False), enc(secret) if secret else None, expires_at, now()))
            return cur.lastrowid

    def set_channel_error(ch_id, error):
        with connect() as c:
            c.execute("UPDATE connected_channels SET last_error=?, status='error' WHERE id=?", (str(error)[:400], ch_id))

    def log_publish(user_id, ch, product_id, ok, external_id='', detail=''):
        with connect() as c:
            c.execute('''INSERT INTO publish_log(user_id, channel_id, platform, product_id, ok, external_id, detail, created_at)
                         VALUES (?,?,?,?,?,?,?,?)''', (user_id, ch['id'], ch['platform'], product_id, int(ok),
                                                       str(external_id or '')[:120], str(detail)[:400], now()))

    def expires_iso(seconds):
        if not seconds:
            return None
        return (datetime.now(timezone.utc) + timedelta(seconds=int(seconds))).isoformat(timespec='seconds')

    def new_state(user_id, platform, redirect_uri, return_tab='connectors'):
        state = secrets.token_urlsafe(32)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=OAUTH_STATE_MINUTES)).isoformat(timespec='seconds')
        with connect() as c:
            c.execute('DELETE FROM oauth_states WHERE created_at<?', (cutoff,))
            c.execute('INSERT INTO oauth_states(state,user_id,platform,redirect_uri,created_at,return_tab) VALUES(?,?,?,?,?,?)',
                      (state, user_id, platform, redirect_uri, now(), return_tab if return_tab in ('connectors', 'studio') else 'connectors'))
        return state

    def take_state(state, platform):
        if not state or len(state) > 100:
            return None
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=OAUTH_STATE_MINUTES)).isoformat(timespec='seconds')
        with connect() as c:
            row = c.execute('SELECT * FROM oauth_states WHERE state=? AND platform=?', (state, platform)).fetchone()
            c.execute('DELETE FROM oauth_states WHERE state=?', (state,))
        if not row or row['created_at'] < cutoff:
            return None
        return dict(row)

    def back(platform, ok, tab='connectors', **extra):
        q = {'tab': tab, 'oauth': 'success' if ok else 'error', 'platform': platform, **extra}
        return RedirectResponse('/?' + urlencode(q), status_code=303)

    # ============================================================== HELP CENTER
    @app.get('/api/help/articles')
    def help_articles():
        return help_content.public_articles()

    @app.get('/api/help/search')
    def help_search(q: str = ''):
        return {'results': [{'id': a['id'], 'title': a['title'], 'summary': a['summary']}
                            for a in help_content.search(q[:200], 5)]}

    # ============================================================== SUPPORT CHAT
    def thread_for(user, create=False):
        t = read('SELECT * FROM support_threads WHERE user_id=?', (user['id'],), True)
        if not t and create:
            with connect() as c:
                c.execute('INSERT OR IGNORE INTO support_threads(user_id,status,last_message_at,created_at) VALUES(?,?,?,?)',
                          (user['id'], 'open', now(), now()))
            t = read('SELECT * FROM support_threads WHERE user_id=?', (user['id'],), True)
        return t

    def thread_checked(user, thread_id):
        if user['role'] == 'admin' and thread_id:
            t = read('SELECT * FROM support_threads WHERE id=?', (thread_id,), True)
            if not t:
                raise HTTPException(404, 'ไม่พบห้องแชท')
            return t
        return thread_for(user, create=True)

    def insert_message(thread, role, user, body):
        body = body.strip()
        if not body:
            raise HTTPException(400, 'กรุณาพิมพ์ข้อความ')
        with connect() as c:
            cur = c.execute('''INSERT INTO support_messages(thread_id,sender_role,sender_id,sender_name,body,created_at)
                               VALUES(?,?,?,?,?,?)''', (thread['id'], role, user['id'] if user else None,
                                                        (user or {}).get('username', 'Studio Bot') if role != 'bot' else 'Studio Bot',
                                                        body[:SUPPORT_MAX_LEN], now()))
            if role == 'user':
                c.execute("UPDATE support_threads SET unread_admin=unread_admin+1, last_message_at=?, status='open' WHERE id=?",
                          (now(), thread['id']))
            else:
                c.execute('UPDATE support_threads SET unread_user=unread_user+1, last_message_at=? WHERE id=?',
                          (now(), thread['id']))
            mid = cur.lastrowid
        return read('SELECT * FROM support_messages WHERE id=?', (mid,), True)

    async def post_message(user, body, thread_id=None):
        is_admin = user['role'] == 'admin' and thread_id
        thread = thread_checked(user, thread_id)
        if not is_admin and thread['user_id'] != user['id']:
            raise HTTPException(403, 'ไม่มีสิทธิ์ในห้องแชทนี้')
        role = 'admin' if is_admin else 'user'
        msg = insert_message(thread, role, user, body)
        await hub.to_thread(thread['user_id'], {'type': 'message', 'thread_id': thread['id'], 'message': msg})
        out = [msg]
        if role == 'user' and hub.admins_online() == 0:
            recent_bot = read('''SELECT COUNT(*) n FROM support_messages WHERE thread_id=? AND sender_role='bot'
                                 AND created_at>?''', (thread['id'], (datetime.now(timezone.utc) - timedelta(seconds=20))
                                                       .isoformat(timespec='seconds')), True)['n']
            if not recent_bot:
                bot = insert_message(thread, 'bot', None, help_content.bot_reply(body))
                await hub.to_thread(thread['user_id'], {'type': 'message', 'thread_id': thread['id'], 'message': bot})
                out.append(bot)
        return thread, out

    @app.get('/api/support/thread')
    def my_thread(req: Request, thread_id: int | None = None, after: int = 0):
        u = require_user(req)
        if u['role'] == 'admin' and thread_id:
            t = thread_checked(u, thread_id)
        else:
            t = thread_for(u)
        if not t:
            return {'thread': None, 'messages': [], 'admins_online': hub.admins_online()}
        msgs = read('SELECT * FROM support_messages WHERE thread_id=? AND id>? ORDER BY id ASC LIMIT 300',
                    (t['id'], max(0, after)))
        return {'thread': t, 'messages': msgs, 'admins_online': hub.admins_online()}

    @app.post('/api/support/messages')
    async def send_support(body: SupportMessageIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'support', 20)
        thread, msgs = await post_message(u, body.body, body.thread_id)
        return {'thread_id': thread['id'], 'messages': msgs}

    @app.post('/api/support/threads/{thread_id}/read')
    def mark_read(thread_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        t = read('SELECT * FROM support_threads WHERE id=?', (thread_id,), True)
        if not t or (u['role'] != 'admin' and t['user_id'] != u['id']):
            raise HTTPException(404, 'ไม่พบห้องแชท')
        col = 'unread_admin' if u['role'] == 'admin' and t['user_id'] != u['id'] else 'unread_user'
        with connect() as c:
            c.execute(f'UPDATE support_threads SET {col}=0 WHERE id=?', (thread_id,))
        return {'ok': True}

    @app.get('/api/support/threads')
    def admin_threads(req: Request, status: str = 'all'):
        require_admin(req)
        where = '' if status not in ('open', 'resolved') else 'WHERE t.status=?'
        params = () if not where else (status,)
        return {'threads': read(f'''SELECT t.*, u.username, u.email,
            (SELECT body FROM support_messages m WHERE m.thread_id=t.id ORDER BY m.id DESC LIMIT 1) AS last_body,
            (SELECT sender_role FROM support_messages m WHERE m.thread_id=t.id ORDER BY m.id DESC LIMIT 1) AS last_role
            FROM support_threads t JOIN users u ON u.id=t.user_id {where}
            ORDER BY t.last_message_at DESC LIMIT 200''', params), 'admins_online': hub.admins_online()}

    @app.patch('/api/support/threads/{thread_id}')
    async def set_thread_status(thread_id: int, body: ThreadStatusIn, req: Request,
                                x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'สำหรับผู้ดูแลระบบเท่านั้น')
        t = read('SELECT * FROM support_threads WHERE id=?', (thread_id,), True)
        if not t:
            raise HTTPException(404, 'ไม่พบห้องแชท')
        with connect() as c:
            c.execute('UPDATE support_threads SET status=? WHERE id=?', (body.status, thread_id))
        await hub.to_thread(t['user_id'], {'type': 'thread', 'thread_id': thread_id, 'status': body.status})
        return {'ok': True, 'status': body.status}

    @app.get('/api/support/unread')
    def unread(req: Request):
        u = require_user(req)
        if u['role'] == 'admin':
            n = read('SELECT COALESCE(SUM(unread_admin),0) n FROM support_threads', (), True)['n']
        else:
            t = thread_for(u)
            n = t['unread_user'] if t else 0
        return {'unread': n, 'admins_online': hub.admins_online()}

    def ws_user(ws: WebSocket):
        origin = ws.headers.get('origin')
        host = ws.headers.get('host', '')
        if origin and (urlsplit(origin).netloc or '').lower() != host.lower():
            return None
        raw = ws.cookies.get('community_session')
        if not raw:
            return None
        import hashlib
        digest = hashlib.sha256(raw.encode()).hexdigest()
        s = read('''SELECT u.id,u.username,u.role,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id
                    WHERE s.token_hash=?''', (digest,), True)
        if not s or s['expires_at'] <= now():
            return None
        return {'id': s['id'], 'username': s['username'], 'role': s['role']}

    @app.websocket('/ws/support')
    async def support_ws(ws: WebSocket):
        user = ws_user(ws)
        if not user:
            # Accept then close with an app code so the browser can tell "login required" from a network drop.
            await ws.accept()
            await ws.close(code=4401)
            return
        await ws.accept()
        await hub.add(ws, user)
        sent = []
        raw_cookie = ws.cookies.get('community_session', '')
        import hashlib as _h
        digest = _h.sha256(raw_cookie.encode()).hexdigest()

        def still_valid():
            s = read('SELECT expires_at FROM sessions WHERE token_hash=?', (digest,), True)
            return bool(s and s['expires_at'] > now())

        async def watchdog():
            # Close the socket soon after logout / session expiry.
            while True:
                await asyncio.sleep(15)
                if not still_valid():
                    await ws.close(code=4401)
                    return
        watcher = asyncio.get_running_loop().create_task(watchdog())
        try:
            while True:
                data = await ws.receive_json()
                if not still_valid():
                    await ws.close(code=4401)
                    break
                kind = data.get('type') if isinstance(data, dict) else None
                if kind == 'send':
                    t = time.monotonic()
                    sent = [x for x in sent if t - x < 60]
                    if len(sent) >= 20:
                        await ws.send_json({'type': 'error', 'detail': 'ส่งข้อความถี่เกินไป'})
                        continue
                    sent.append(t)
                    body = str(data.get('body') or '')[:SUPPORT_MAX_LEN]
                    tid = data.get('thread_id')
                    tid = int(tid) if isinstance(tid, (int, str)) and str(tid).isdigit() else None
                    try:
                        await post_message(user, body, tid)
                    except HTTPException as e:
                        await ws.send_json({'type': 'error', 'detail': e.detail})
                elif kind == 'typing':
                    tid = data.get('thread_id')
                    if user['role'] == 'admin' and str(tid).isdigit():
                        t = read('SELECT user_id FROM support_threads WHERE id=?', (int(tid),), True)
                        if t:
                            await hub.to_thread(t['user_id'], {'type': 'typing', 'thread_id': int(tid), 'from': 'admin'})
                    else:
                        t = thread_for(user)
                        if t:
                            await hub.to_thread(t['user_id'], {'type': 'typing', 'thread_id': t['id'], 'from': 'user'},
                                                include_owner=False)
                elif kind == 'ping':
                    await ws.send_json({'type': 'pong'})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            watcher.cancel()
            await hub.remove(ws)

    # ============================================================== CONNECTORS
    @app.get('/api/connectors')
    def connectors(req: Request):
        u = require_user(req)
        b = base_url(req)
        rows = read("SELECT * FROM connected_channels WHERE user_id=? AND platform IN ('facebook','instagram','line_oa') ORDER BY id",
                    (u['id'],))
        chans = []
        for r in rows:
            item = channel_public(r)
            if r['platform'] == 'line_oa':
                m = json.loads(r.get('meta_json') or '{}')
                item['webhook_url'] = f"{b}/api/webhooks/line/{m.get('webhook_key', '')}" if m.get('webhook_key') else ''
                item['recipients'] = read('SELECT COUNT(*) n FROM line_recipients WHERE channel_id=?', (r['id'],), True)['n']
            chans.append(item)
        return {
            'config': {
                'facebook': {'ready': bool(cfg('meta_app_id') and cfg('meta_app_secret')),
                             'redirect_uri': f'{b}/api/oauth/facebook/callback'},
                'instagram': {'ready': bool(cfg('ig_app_id') and cfg('ig_app_secret')),
                              'via_facebook_ready': bool(cfg('meta_app_id') and cfg('meta_app_secret')),
                              'redirect_uri': f'{b}/api/oauth/instagram/callback'},
                'line_oa': {'ready': True, 'public_https': b.startswith('https://')},
                'base_url': b, 'graph_version': meta.graph_version(),
            },
            'channels': chans, 'is_admin': u['role'] == 'admin',
        }

    @app.get('/api/admin/integrations')
    def get_integrations(req: Request):
        require_admin(req)
        out = {}
        for k, env in CONFIG_KEYS.items():
            v = cfg(k)
            from_env = bool(os.getenv(env, '').strip())
            if k in SECRET_KEYS:
                out[k] = {'set': bool(v), 'from_env': from_env}
            else:
                out[k] = {'set': bool(v), 'value': v, 'from_env': from_env}
        return out

    @app.put('/api/admin/integrations')
    def put_integrations(body: IntegrationConfigIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'สำหรับผู้ดูแลระบบเท่านั้น')
        changes = body.model_dump(exclude_none=True)
        for k, v in changes.items():
            v = v.strip()
            if k == 'public_base_url' and v:
                p = urlsplit(v)
                if p.scheme not in ('https', 'http') or not p.netloc or p.path not in ('', '/') or p.query:
                    raise HTTPException(400, 'PUBLIC_BASE_URL ต้องเป็นโดเมนล้วน เช่น https://studio.example.com')
                if public_mode and p.scheme != 'https':
                    raise HTTPException(400, 'โหมด Public ต้องใช้ https')
                v = v.rstrip('/')
            if k in ('meta_app_id', 'ig_app_id') and v and not re.fullmatch(r'\d{5,25}', v):
                raise HTTPException(400, 'App ID ต้องเป็นตัวเลข')
            with connect() as c:
                if v:
                    c.execute('''INSERT INTO integration_config(key,value_encrypted,updated_at) VALUES(?,?,?)
                                 ON CONFLICT(key) DO UPDATE SET value_encrypted=excluded.value_encrypted, updated_at=excluded.updated_at''',
                              (k, enc(v), now()))
                else:
                    c.execute('DELETE FROM integration_config WHERE key=?', (k,))
        return {'ok': True, 'updated': sorted(changes)}

    # ---------------- Facebook
    @app.post('/api/connectors/facebook/start')
    def fb_start(req: Request, return_tab: str = 'connectors', x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        app_id = cfg('meta_app_id')
        if not app_id or not cfg('meta_app_secret'):
            raise HTTPException(409, 'ผู้ดูแลระบบยังไม่ได้ตั้งค่า Meta App ID/Secret (ดูคู่มือ "ตั้งค่า Meta App")')
        redirect_uri = f'{base_url(req)}/api/oauth/facebook/callback'
        state = new_state(u['id'], 'facebook', redirect_uri, return_tab)
        return {'auth_url': meta.facebook_auth_url(app_id, redirect_uri, state)}

    @app.get('/api/oauth/facebook/callback')
    def fb_callback(state: str = '', code: str = '', error: str = '', error_description: str = ''):
        st = take_state(state, 'facebook')
        if not st:
            return back('facebook', False, tab=(st or {}).get('return_tab', 'connectors'), reason='ลิงก์เชื่อมต่อหมดอายุหรือไม่ถูกต้อง กรุณากด Connect ใหม่')
        if error or not code:
            if error == 'access_denied':
                return back('facebook', False, tab=(st or {}).get('return_tab', 'connectors'), reason='คุณกดยกเลิกการอนุญาต — กด Connect ใหม่และเลือกเพจเมื่อพร้อม')
            return back('facebook', False, tab=(st or {}).get('return_tab', 'connectors'), reason=(error_description or error or 'ยกเลิกการเชื่อมต่อ')[:200])
        try:
            user_token = meta.facebook_exchange_code(cfg('meta_app_id'), cfg('meta_app_secret'), st['redirect_uri'], code)
            pages = meta.facebook_pages(user_token)
        except meta.MetaError as e:
            return back('facebook', False, tab=(st or {}).get('return_tab', 'connectors'), reason=str(e)[:200])
        if not pages:
            return back('facebook', False, tab=(st or {}).get('return_tab', 'connectors'), reason='ไม่พบเพจที่อนุญาต — กด Connect ใหม่แล้วเลือกเพจใน "Edit settings"')
        ig_count = 0
        for p in pages:
            upsert_channel(st['user_id'], 'facebook', p['id'], p['name'], p['access_token'], kind='oauth',
                           meta_obj={'picture': p['picture'], 'category': p['category']})
            if p['instagram']:
                ig = p['instagram']
                upsert_channel(st['user_id'], 'instagram', ig['id'], '@' + (ig['username'] or ig['id']), p['access_token'],
                               kind='oauth', meta_obj={'via': 'facebook', 'page_id': p['id'], 'page_name': p['name'],
                                                       'picture': ig['picture'], 'username': ig['username']})
                ig_count += 1
        return back('facebook', True, tab=st['return_tab'], count=len(pages), ig=ig_count)

    @app.post('/api/connectors/facebook/token')
    def fb_connect_token(body: FbTokenIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        """Connect a page by pasting its Page Access Token — no Meta App required."""
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'fb-token', 6)
        token = body.token.strip()
        try:
            page = meta.facebook_page_from_token(token)
        except meta.MetaError as e:
            raise HTTPException(400, str(e))
        upsert_channel(u['id'], 'facebook', page['id'], page['name'], token, kind='page_token',
                       meta_obj={'picture': page['picture'], 'category': page['category'], 'via': 'page_token'})
        ig = page['instagram']
        if ig:
            upsert_channel(u['id'], 'instagram', ig['id'], '@' + (ig['username'] or ig['id']), token, kind='page_token',
                           meta_obj={'via': 'facebook', 'page_id': page['id'], 'page_name': page['name'],
                                     'picture': ig['picture'], 'username': ig['username']})
        return {'ok': True, 'page': {'id': page['id'], 'name': page['name'], 'picture': page['picture']},
                'instagram': bool(ig),
                'message': f'เชื่อมเพจ "{page["name"]}" สำเร็จ' + (' · พบ Instagram ที่ผูกไว้' if ig else '')}

    # ---------------- Instagram Login
    @app.post('/api/connectors/instagram/start')
    def ig_start(req: Request, return_tab: str = 'connectors', x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        app_id = cfg('ig_app_id')
        if not app_id or not cfg('ig_app_secret'):
            raise HTTPException(409, 'ผู้ดูแลระบบยังไม่ได้ตั้งค่า Instagram App ID/Secret — หรือเชื่อม IG ผ่านเพจ Facebook แทน')
        redirect_uri = f'{base_url(req)}/api/oauth/instagram/callback'
        state = new_state(u['id'], 'instagram', redirect_uri, return_tab)
        return {'auth_url': meta.instagram_auth_url(app_id, redirect_uri, state)}

    @app.get('/api/oauth/instagram/callback')
    def ig_callback(state: str = '', code: str = '', error: str = '', error_description: str = ''):
        st = take_state(state, 'instagram')
        if not st:
            return back('instagram', False, tab=(st or {}).get('return_tab', 'connectors'), reason='ลิงก์เชื่อมต่อหมดอายุหรือไม่ถูกต้อง กรุณากด Connect ใหม่')
        if error or not code:
            if error == 'access_denied':
                return back('instagram', False, tab=(st or {}).get('return_tab', 'connectors'), reason='คุณกดยกเลิกการอนุญาต — กด Connect ใหม่เมื่อพร้อม')
            return back('instagram', False, tab=(st or {}).get('return_tab', 'connectors'), reason=(error_description or error or 'ยกเลิกการเชื่อมต่อ')[:200])
        code = code.split('#')[0]
        try:
            tok = meta.instagram_exchange_code(cfg('ig_app_id'), cfg('ig_app_secret'), st['redirect_uri'], code)
            me_ = meta.instagram_me(tok['access_token'])
        except meta.MetaError as e:
            return back('instagram', False, tab=(st or {}).get('return_tab', 'connectors'), reason=str(e)[:200])
        upsert_channel(st['user_id'], 'instagram', me_['id'], '@' + (me_['username'] or me_['id']), tok['access_token'],
                       kind='oauth', meta_obj={'via': 'instagram', 'picture': me_['picture'], 'username': me_['username'],
                                               'account_type': me_['account_type']},
                       expires_at=expires_iso(tok['expires_in']))
        return back('instagram', True, tab=st['return_tab'], count=1)

    # ---------------- LINE OA
    @app.post('/api/connectors/line')
    def line_connect(body: LineConnectIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'line-connect', 6)
        cid, secret = body.channel_id.strip(), body.channel_secret.strip()
        if not cid.isdigit():
            raise HTTPException(400, 'Channel ID ต้องเป็นตัวเลข')
        token = (body.access_token or '').strip()
        expires_at, token_kind = None, 'long_lived'
        try:
            if not token:
                issued = line_oa.issue_token(cid, secret)
                token, expires_at, token_kind = issued['access_token'], expires_iso(issued['expires_in']), 'issued_30d'
            info = line_oa.bot_info(token)
        except line_oa.LineError as e:
            raise HTTPException(400, str(e))
        try:
            q = line_oa.quota(token)
        except line_oa.LineError:
            q = {}
        meta_obj = {'basic_id': info['basic_id'], 'picture': info['picture'], 'chat_mode': info['chat_mode'],
                    'channel_id': cid, 'token_kind': token_kind, 'quota': q}
        prev = read("SELECT meta_json FROM connected_channels WHERE user_id=? AND platform='line_oa' AND account_id=?",
                    (u['id'], info['user_id']), True)
        # Keep the webhook URL stable across reconnects (users paste it into LINE Developers by hand).
        prev_key = json.loads(prev['meta_json']).get('webhook_key') if prev else None
        meta_obj['webhook_key'] = prev_key or secrets.token_urlsafe(18)
        ch_id = upsert_channel(u['id'], 'line_oa', info['user_id'], info['display_name'], token, kind='token',
                               meta_obj=meta_obj, secret=secret, expires_at=expires_at)
        ch = own_channel(u['id'], ch_id)
        m = json.loads(ch['meta_json'])
        webhook = f"{base_url(req)}/api/webhooks/line/{m['webhook_key']}"
        webhook_result = {'set': False, 'reason': 'เว็บยังไม่เป็น https สาธารณะ — ตั้ง PUBLIC_BASE_URL แล้วกดตรวจสอบอีกครั้ง'}
        if webhook.startswith('https://'):
            try:
                r = line_oa.set_webhook(token, webhook)
                webhook_result = {'set': True, 'test': r}
            except line_oa.LineError as e:
                webhook_result = {'set': False, 'reason': str(e)}
        return {'channel': channel_public(ch), 'webhook_url': webhook, 'webhook': webhook_result,
                'message': f'เชื่อมต่อ LINE OA "{info["display_name"]}" ({info["basic_id"]}) สำเร็จ'}

    @app.post('/api/webhooks/line/{webhook_key}')
    async def line_webhook(webhook_key: str, req: Request, background: BackgroundTasks):
        if not re.fullmatch(r'[A-Za-z0-9_\-]{10,40}', webhook_key):
            raise HTTPException(404, 'not found')
        body = await req.body()
        if len(body) > 1_000_000:
            raise HTTPException(413, 'too large')
        rows = read("SELECT * FROM connected_channels WHERE platform='line_oa' AND meta_json LIKE ?",
                    (f'%"webhook_key": "{webhook_key}"%',))
        ch = next((r for r in rows if json.loads(r['meta_json']).get('webhook_key') == webhook_key), None)
        if not ch:
            raise HTTPException(404, 'not found')
        if not line_oa.verify_signature(dec(ch['secret_encrypted']), body, req.headers.get('x-line-signature', '')):
            raise HTTPException(401, 'bad signature')
        try:
            events = json.loads(body or b'{}').get('events', [])
        except ValueError:
            raise HTTPException(400, 'bad json')
        token = dec(ch['access_token_encrypted'])
        new_profiles = []
        for ev in events[:50]:
            src = ev.get('source') or {}
            uid = src.get('userId')
            if src.get('type') != 'user' or not uid or not re.fullmatch(r'U[0-9a-f]{32}', uid):
                continue
            if ev.get('type') == 'unfollow':
                with connect() as c:
                    c.execute('DELETE FROM line_recipients WHERE channel_id=? AND line_user_id=?', (ch['id'], uid))
                continue
            existing = read('SELECT display_name FROM line_recipients WHERE channel_id=? AND line_user_id=?', (ch['id'], uid), True)
            if not existing:
                new_profiles.append(uid)
            name = ''
            with connect() as c:
                c.execute('''INSERT INTO line_recipients(channel_id,line_user_id,display_name,last_seen) VALUES(?,?,?,?)
                             ON CONFLICT(channel_id,line_user_id) DO UPDATE SET last_seen=excluded.last_seen,
                             display_name=CASE WHEN excluded.display_name!='' THEN excluded.display_name ELSE display_name END''',
                          (ch['id'], uid, name, now()))

        def fill_names(ids, channel_id):
            # LINE expects a fast 200; resolve display names after the response is sent.
            for uid in ids[:20]:
                prof = line_oa.profile(token, uid)
                if prof.get('displayName'):
                    with connect() as c:
                        c.execute('UPDATE line_recipients SET display_name=? WHERE channel_id=? AND line_user_id=?',
                                  (prof['displayName'][:80], channel_id, uid))
        if new_profiles:
            background.add_task(fill_names, new_profiles, ch['id'])
        return {'ok': True}

    @app.get('/api/connectors/{channel_id}/recipients')
    def line_recipients(channel_id: int, req: Request):
        u = require_user(req)
        ch = own_channel(u['id'], channel_id)
        if ch['platform'] != 'line_oa':
            raise HTTPException(400, 'ใช้ได้กับ LINE OA เท่านั้น')
        rows = read('SELECT line_user_id, display_name, last_seen FROM line_recipients WHERE channel_id=? ORDER BY last_seen DESC LIMIT 50',
                    (channel_id,))
        for r in rows:
            r['line_user_id'] = r['line_user_id'][:6] + '…' + r['line_user_id'][-4:]
        return {'recipients': rows}

    # ---------------- verify / test / publish
    def live_check(ch):
        token = dec(ch['access_token_encrypted'])
        m = json.loads(ch.get('meta_json') or '{}')
        if not token:
            raise HTTPException(400, 'ช่องทางนี้ยังไม่มี token (ถูกเพิ่มแบบ manual) กรุณาเชื่อมต่อใหม่ด้วยปุ่ม Connect')
        p = ch['platform']
        updates = {}
        if p == 'facebook':
            info = meta.facebook_page_check(ch['account_id'], token)
            detail = {'name': info.get('name'), 'followers': info.get('followers_count') or info.get('fan_count')}
        elif p == 'instagram':
            via = m.get('via', 'instagram')
            if via == 'instagram' and ch.get('token_expires_at'):
                left = datetime.fromisoformat(ch['token_expires_at']) - datetime.now(timezone.utc)
                if left < timedelta(days=7):
                    r = meta.instagram_refresh(token)
                    token = r['access_token']
                    updates['token'] = token
                    updates['expires_at'] = expires_iso(r['expires_in'])
            info = meta.instagram_check(ch['account_id'], token, via)
            detail = {'username': info.get('username'), 'followers': info.get('followers_count'),
                      'media_count': info.get('media_count')}
        elif p == 'line_oa':
            try:
                info = line_oa.bot_info(token)
            except line_oa.LineError:
                if m.get('token_kind') != 'issued_30d':
                    raise
                issued = line_oa.issue_token(m.get('channel_id', ''), dec(ch['secret_encrypted']))
                token = issued['access_token']
                updates['token'] = token
                updates['expires_at'] = expires_iso(issued['expires_in'])
                info = line_oa.bot_info(token)
            try:
                m['quota'] = line_oa.quota(token)
            except line_oa.LineError:
                pass
            m.update({'basic_id': info['basic_id'], 'picture': info['picture'], 'chat_mode': info['chat_mode']})
            updates['meta'] = m
            detail = {'name': info['display_name'], 'basic_id': info['basic_id'], 'quota': m.get('quota')}
        else:
            raise HTTPException(400, 'ช่องทางนี้ยังไม่รองรับการตรวจสอบจริง')
        with connect() as c:
            if 'token' in updates:
                c.execute('UPDATE connected_channels SET access_token_encrypted=?, token_expires_at=? WHERE id=?',
                          (enc(updates['token']), updates.get('expires_at'), ch['id']))
            if 'meta' in updates:
                c.execute('UPDATE connected_channels SET meta_json=? WHERE id=?', (json.dumps(updates['meta'], ensure_ascii=False), ch['id']))
            c.execute("UPDATE connected_channels SET status='connected', last_error='', verified_at=?, last_synced_at=? WHERE id=?",
                      (now(), now(), ch['id']))
        return detail

    @app.post('/api/connectors/{channel_id}/verify')
    def verify_channel(channel_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'verify', 20)
        ch = own_channel(u['id'], channel_id)
        try:
            detail = live_check(ch)
        except (meta.MetaError, line_oa.LineError) as e:
            set_channel_error(ch['id'], e)
            raise HTTPException(502, str(e))
        return {'ok': True, 'platform': ch['platform'], 'detail': detail,
                'message': f'ตรวจสอบกับ {ch["platform"].upper()} สำเร็จ: ใช้งานได้จริง'}

    def product_for(user_id, product_id):
        if not product_id:
            return None
        p = read('SELECT * FROM products WHERE id=? AND user_id=?', (product_id, user_id), True)
        if not p:
            raise HTTPException(404, 'ไม่พบสินค้าของบัญชีนี้')
        return p

    def product_image(req, p):
        if not p:
            return ''
        if p.get('image_url', '').startswith('https://'):
            return p['image_url']
        if p.get('image_file'):
            return f"{base_url(req)}/media/products/{p['image_file']}"
        return ''

    def default_caption(p):
        if not p:
            return '✅ ทดสอบการเชื่อมต่อจาก Affiliate Auto Studio'
        lines = [f"🔥 {p['title']}"]
        if p.get('price'):
            lines.append(f"💰 ราคาเริ่ม ฿{p['price']:,.0f}")
        if p.get('rating'):
            lines.append(f"⭐ {p['rating']:.1f}/5" + (f" · ขายแล้ว {p['sales']:,} ชิ้น" if p.get('sales') else ''))
        link = p.get('offer_link') or p.get('url')
        if link:
            lines.append(f'🛒 สั่งซื้อ: {link}')
        lines.append('#ShopeeAffiliate #ของดีบอกต่อ')
        return '\n'.join(lines)

    def publish_one(req, user, ch, p, caption, line_mode, confirm_broadcast):
        token = dec(ch['access_token_encrypted'])
        if not token:
            raise HTTPException(400, f'{ch["account_name"]}: ยังไม่มี token กรุณาเชื่อมต่อด้วยปุ่ม Connect')
        m = json.loads(ch.get('meta_json') or '{}')
        img = product_image(req, p)
        link = (p or {}).get('offer_link') or (p or {}).get('url') or ''
        if ch['platform'] == 'facebook':
            msg = caption if (not link or link in caption) else caption
            return meta.facebook_publish(ch['account_id'], token, msg, '' if link in caption else link,
                                         img if img.startswith('https://') else '')
        if ch['platform'] == 'instagram':
            if not img.startswith('https://'):
                raise meta.MetaError('Instagram ต้องใช้รูปจาก URL https สาธารณะ (เลือกสินค้าที่มีรูปจาก Shopee หรือตั้ง PUBLIC_BASE_URL เป็น https)')
            return meta.instagram_publish(ch['account_id'], token, caption, img, m.get('via', 'instagram'))
        if ch['platform'] == 'line_oa':
            if p:
                price = f"฿{p['price']:,.0f}" if p.get('price') else ''
                messages = [line_oa.product_flex(p['title'], price, img if img.startswith('https://') else '', link,
                                                 caption.split('\n')[0] if caption else '')]
            else:
                messages = [{'type': 'text', 'text': caption[:4900] or 'ทดสอบ'}]
            if line_mode == 'broadcast':
                if not confirm_broadcast:
                    raise HTTPException(400, 'Broadcast จะส่งหาเพื่อนทุกคนและนับโควต้า — ต้องยืนยันก่อน')
                line_oa.broadcast(token, messages)
                return {'post_id': '', 'kind': 'broadcast'}
            r = read('SELECT line_user_id FROM line_recipients WHERE channel_id=? ORDER BY last_seen DESC LIMIT 1', (ch['id'],), True)
            if not r:
                raise line_oa.LineError('ยังไม่มีผู้รับสำหรับ Push — แอดเพื่อน OA แล้วพิมพ์ข้อความ 1 ครั้ง (ต้องเปิด Use webhook)')
            line_oa.push(token, r['line_user_id'], messages)
            return {'post_id': '', 'kind': 'push'}
        raise HTTPException(400, 'ช่องทางนี้ยังไม่รองรับการโพสต์จริง')

    @app.post('/api/connectors/{channel_id}/test-post')
    def test_post(channel_id: int, body: TestPostIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'publish', 10)
        ch = own_channel(u['id'], channel_id)
        p = product_for(u['id'], body.product_id)
        caption = body.message.strip() or default_caption(p)
        try:
            r = publish_one(req, u, ch, p, caption, body.line_mode, body.confirm_broadcast)
        except (meta.MetaError, line_oa.LineError) as e:
            log_publish(u['id'], ch, body.product_id, False, '', str(e))
            raise HTTPException(502, str(e))
        log_publish(u['id'], ch, body.product_id, True, r.get('post_id'), r.get('kind'))
        return {'ok': True, **r, 'message': f'ส่งไปยัง {ch["account_name"]} สำเร็จ'}

    @app.post('/api/products/{product_id}/publish')
    def publish_product(product_id: int, body: PublishIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'publish', 10)
        p = product_for(u['id'], product_id)
        caption = body.caption.strip() or default_caption(p)
        results = []
        for cid in dict.fromkeys(body.channel_ids):
            ch = read('SELECT * FROM connected_channels WHERE id=? AND user_id=?', (cid, u['id']), True)
            if not ch:
                results.append({'channel_id': cid, 'ok': False, 'error': 'ไม่พบช่องทาง'})
                continue
            try:
                r = publish_one(req, u, ch, p, caption, body.line_mode, body.confirm_broadcast)
                log_publish(u['id'], ch, product_id, True, r.get('post_id'), r.get('kind'))
                results.append({'channel_id': cid, 'platform': ch['platform'], 'account_name': ch['account_name'], 'ok': True, **r})
            except HTTPException as e:
                results.append({'channel_id': cid, 'platform': ch['platform'], 'account_name': ch['account_name'], 'ok': False, 'error': e.detail})
            except (meta.MetaError, line_oa.LineError) as e:
                log_publish(u['id'], ch, product_id, False, '', str(e))
                results.append({'channel_id': cid, 'platform': ch['platform'], 'account_name': ch['account_name'], 'ok': False, 'error': str(e)})
        ok = sum(1 for r in results if r['ok'])
        return {'results': results, 'ok_count': ok, 'message': f'โพสต์สำเร็จ {ok}/{len(results)} ช่องทาง'}

    @app.get('/api/connectors/logs')
    def publish_logs(req: Request):
        u = require_user(req)
        return {'logs': read('''SELECT l.*, c.account_name, p.title AS product_title FROM publish_log l
                                LEFT JOIN connected_channels c ON c.id=l.channel_id
                                LEFT JOIN products p ON p.id=l.product_id
                                WHERE l.user_id=? ORDER BY l.id DESC LIMIT 50''', (u['id'],))}

    @app.delete('/api/connectors/{channel_id}')
    def delete_connector(channel_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        own_channel(u['id'], channel_id)
        with connect() as c:
            c.execute('DELETE FROM connected_channels WHERE id=? AND user_id=?', (channel_id, u['id']))
        return {'ok': True}

    # ============================================================== SHOPEE AFFILIATE
    def shopee_creds(user_id):
        row = read("SELECT encrypted FROM credentials WHERE user_id=? AND provider='shopee_affiliate'", (user_id,), True)
        if not row:
            return None
        try:
            d = json.loads(dec(row['encrypted']))
            return d['app_id'], d['secret']
        except (ValueError, KeyError):
            return None

    def need_creds(user_id):
        c = shopee_creds(user_id)
        if not c:
            raise HTTPException(409, 'ยังไม่ได้ตั้งค่า Shopee Affiliate AppID/Secret — ใส่ที่กล่อง "ดึงสินค้าจาก Shopee"')
        return c

    @app.get('/api/shopee/status')
    def shopee_status(req: Request):
        u = require_user(req)
        c = shopee_creds(u['id'])
        return {'configured': bool(c), 'app_id': (c[0][:3] + '•••' + c[0][-2:]) if c else '',
                'endpoint': shopee.endpoint()}

    @app.put('/api/shopee/credentials')
    def shopee_save(body: ShopeeCredIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'shopee', 30)
        app_id, secret = body.app_id.strip(), body.secret.strip()
        if not app_id.isdigit():
            raise HTTPException(400, 'AppID ต้องเป็นตัวเลข')
        try:
            sample = shopee.product_offers(app_id, secret, keyword='พัดลม', limit=1)
        except shopee.ShopeeError as e:
            raise HTTPException(400, f'ทดสอบคีย์ไม่ผ่าน: {e}')
        with connect() as c:
            c.execute('''INSERT INTO credentials(user_id,provider,encrypted,created_at) VALUES(?,?,?,?)
                         ON CONFLICT(user_id,provider) DO UPDATE SET encrypted=excluded.encrypted, created_at=excluded.created_at''',
                      (u['id'], 'shopee_affiliate', enc(json.dumps({'app_id': app_id, 'secret': secret})), now()))
        return {'saved': True, 'verified': True, 'sample_count': len(sample['items'])}

    @app.delete('/api/shopee/credentials')
    def shopee_delete(req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        with connect() as c:
            c.execute("DELETE FROM credentials WHERE user_id=? AND provider='shopee_affiliate'", (u['id'],))
        return {'deleted': True}

    def fetch_item(creds, shop_id, item_id):
        res = shopee.product_offers(*creds, shop_id=shop_id or None, item_id=item_id, limit=1)
        items = [i for i in res['items'] if i['item_id'] == str(item_id)] or res['items']
        if not items:
            raise HTTPException(404, 'ไม่พบสินค้านี้ในโปรแกรม Shopee Affiliate (อาจไม่ได้เข้าร่วม หรือหมดแคมเปญ)')
        return items[0]

    @app.post('/api/shopee/lookup')
    def shopee_lookup(body: ShopeeLookupIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'shopee', 30)
        creds = need_creds(u['id'])
        try:
            shop_id, item_id = shopee.ids_from_link(body.url.strip())
            item = fetch_item(creds, shop_id, item_id)
        except shopee.ShopeeError as e:
            raise HTTPException(400, str(e))
        dup = read('SELECT id FROM products WHERE user_id=? AND item_id=?', (u['id'], item['item_id']), True)
        item['already_added'] = dup['id'] if dup else None
        return {'item': item}

    @app.get('/api/shopee/search')
    def shopee_search(req: Request, keyword: str = '', sort: str = 'commission', page: int = 1):
        u = require_user(req)
        limit(u['id'], 'shopee', 30)
        creds = need_creds(u['id'])
        keyword = keyword.strip()[:120]
        if len(keyword) < 2:
            raise HTTPException(400, 'พิมพ์คีย์เวิร์ดอย่างน้อย 2 ตัวอักษร')
        if sort not in shopee.SORT_TYPES:
            raise HTTPException(400, 'รูปแบบการเรียงไม่ถูกต้อง')
        try:
            res = shopee.product_offers(*creds, keyword=keyword, sort=sort, page=max(1, min(page, 50)), limit=20)
        except shopee.ShopeeError as e:
            raise HTTPException(400, str(e))
        added = {r['item_id']: r['id'] for r in read("SELECT id,item_id FROM products WHERE user_id=? AND item_id!=''", (u['id'],))}
        for it in res['items']:
            it['already_added'] = added.get(it['item_id'])
        return res

    def save_item(user_id, item, product_id=None):
        url = item['offer_link'] or item['product_link']
        if url and not shopee.is_shopee_url(url):
            url = ''
        vals = (item['title'] or 'สินค้า Shopee', url, item['price'], item['price_min'], item['price_max'],
                item['commission_rate'], item['seller_comm_rate'], item['shopee_comm_rate'], item['commission_baht'],
                item['image_url'] if item['image_url'].startswith('https://') else '', item['shop_name'], item['shop_id'],
                item['item_id'], item['offer_link'], item['product_link'], item['sales'], item['rating'], now())
        with connect() as c:
            if product_id:
                c.execute('''UPDATE products SET title=?, url=?, price=?, price_min=?, price_max=?, commission_rate=?,
                             seller_comm_rate=?, shopee_comm_rate=?, commission_baht=?, image_url=?, shop_name=?, shop_id=?,
                             item_id=?, offer_link=?, product_link=?, sales=?, rating=?, synced_at=?, source='shopee_affiliate_api',
                             discount_rate=? WHERE id=? AND user_id=?''', vals + (item.get('discount_rate'), product_id, user_id))
                return product_id
            cur = c.execute('''INSERT INTO products(user_id, platform, created_at, title, url, price, price_min, price_max,
                               commission_rate, seller_comm_rate, shopee_comm_rate, commission_baht, image_url, shop_name,
                               shop_id, item_id, offer_link, product_link, sales, rating, synced_at, source, discount_rate)
                               VALUES (?, 'shopee', ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'shopee_affiliate_api', ?)''',
                            (user_id, now()) + vals + (item.get('discount_rate'),))
            return cur.lastrowid

    @app.post('/api/shopee/import')
    def shopee_import(body: ShopeeImportIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'shopee', 30)
        creds = need_creds(u['id'])
        dup = read('SELECT id FROM products WHERE user_id=? AND item_id=?', (u['id'], body.item_id), True)
        if dup:
            raise HTTPException(409, f'สินค้านี้อยู่ในคลังแล้ว (#{dup["id"]}) — กด 🔄 เพื่ออัปเดตข้อมูล')
        try:
            item = fetch_item(creds, body.shop_id, body.item_id)  # server-side truth, never trust client prices
        except shopee.ShopeeError as e:
            raise HTTPException(400, str(e))
        pid = save_item(u['id'], item)
        return {'id': pid, 'item': item, 'message': f'เพิ่ม "{item["title"][:40]}" สำเร็จ'}

    # ---- bulk fetch via the official Open API (background job + progress polling)
    import threading
    fetch_jobs: dict[str, dict] = {}

    def _run_fetch(job_id: str):
        job = fetch_jobs[job_id]
        try:
            creds, want = job['creds'], job['limit']
            page, seen = 1, set()
            while len(seen) < want and page <= 10:
                res = shopee.product_offers(*creds, keyword=job['keyword'], sort=job['sort'], page=page, limit=min(50, want),
                                            list_type=job['list_type'] if job['mode'] == 'category' else '',
                                            ams_only=job['ams_only'])
                items = res['items']
                if not items:
                    break
                job['total'] = min(want, job['total'] + len(items)) if job['total'] else min(want, len(items))
                for it in items:
                    if len(seen) >= want:
                        break
                    if not it['item_id'] or it['item_id'] in seen:
                        continue
                    seen.add(it['item_id'])
                    existing = read('SELECT id FROM products WHERE user_id=? AND item_id=?', (job['user_id'], it['item_id']), True)
                    pid = save_item(job['user_id'], it, existing['id'] if existing else None)
                    job['updated' if existing else 'added'] += 1
                    job['done'] = len(seen)
                    job['items'].append({'id': pid, 'title': it['title'], 'image_url': it['image_url'], 'price': it['price'],
                                         'commission_rate': it['commission_rate'], 'sales': it['sales'],
                                         'discount_rate': it.get('discount_rate'), 'updated': bool(existing)})
                if not (res.get('page_info') or {}).get('hasNextPage'):
                    break
                page += 1
                time.sleep(0.4)  # be polite to the API between pages
            job['total'] = job['done']
            job['status'] = 'done'
        except shopee.ShopeeError as e:
            job['status'] = 'error'; job['error'] = str(e)
        except Exception as e:  # never leave a job spinning forever
            job['status'] = 'error'; job['error'] = f'เกิดข้อผิดพลาด: {e}'
        finally:
            job.pop('creds', None)
            job['finished_at'] = time.time()

    @app.post('/api/shopee/fetch')
    def shopee_fetch_start(body: ShopeeFetchIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        """Pull products from Shopee Affiliate Open API into the user's library (no cookies, no scraping)."""
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'shopee-fetch', 4)
        creds = need_creds(u['id'])
        kw = body.keyword.strip()
        if body.mode == 'search' and len(kw) < 2:
            raise HTTPException(400, 'พิมพ์คีย์เวิร์ดอย่างน้อย 2 ตัวอักษร')
        # one running job per user
        for j in fetch_jobs.values():
            if j['user_id'] == u['id'] and j['status'] == 'running':
                raise HTTPException(409, 'กำลังดึงสินค้าอยู่ รอให้รอบก่อนเสร็จก่อน')
        # drop finished jobs older than 10 minutes
        for k in [k for k, j in fetch_jobs.items() if j['status'] != 'running' and time.time() - j.get('finished_at', 0) > 600]:
            fetch_jobs.pop(k, None)
        job_id = secrets.token_urlsafe(12)
        fetch_jobs[job_id] = {'user_id': u['id'], 'status': 'running', 'mode': body.mode, 'keyword': kw if body.mode == 'search' else '',
                              'list_type': body.list_type, 'ams_only': body.ams_only, 'sort': body.sort, 'limit': body.limit,
                              'creds': creds, 'total': 0, 'done': 0, 'added': 0, 'updated': 0, 'items': [], 'error': '',
                              'started_at': time.time()}
        threading.Thread(target=_run_fetch, args=(job_id,), daemon=True).start()
        return {'job_id': job_id}

    @app.get('/api/shopee/fetch/{job_id}')
    def shopee_fetch_status(job_id: str, req: Request, since: int = 0):
        u = require_user(req)
        job = fetch_jobs.get(job_id)
        if not job or job['user_id'] != u['id']:
            raise HTTPException(404, 'ไม่พบงานดึงสินค้า')
        return {'status': job['status'], 'total': job['total'], 'done': job['done'], 'added': job['added'],
                'updated': job['updated'], 'error': job['error'], 'items': job['items'][since:],
                'next': len(job['items'])}

    @app.post('/api/my/products/{product_id}/refresh')
    def shopee_refresh(product_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'shopee', 30)
        p = product_for(u['id'], product_id)
        creds = need_creds(u['id'])
        shop_id, item_id = p.get('shop_id'), p.get('item_id')
        try:
            if not item_id:
                if not p.get('url') or not shopee.is_shopee_url(p['url']):
                    raise HTTPException(400, 'สินค้านี้ไม่มีลิงก์ Shopee ให้ดึงข้อมูล')
                shop_id, item_id = shopee.ids_from_link(p['url'])
            item = fetch_item(creds, shop_id, item_id)
        except shopee.ShopeeError as e:
            raise HTTPException(400, str(e))
        save_item(u['id'], item, product_id)
        return {'id': product_id, 'item': item, 'message': 'อัปเดตราคาและค่าคอมล่าสุดแล้ว'}

    @app.post('/api/my/products/manual')
    async def manual_product(req: Request, title: str = Form(...), url: str = Form(''), platform: str = Form('shopee'),
                             price: str = Form(''), commission_rate: str = Form(''), image_url: str = Form(''),
                             image: UploadFile | None = File(None), x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        title = title.strip()
        if not 3 <= len(title) <= 200:
            raise HTTPException(400, 'ชื่อสินค้าต้องยาว 3-200 ตัวอักษร')
        if platform not in ('shopee', 'tiktok', 'other'):
            raise HTTPException(400, 'แพลตฟอร์มไม่ถูกต้อง')
        url = url.strip()
        if url and (not url.startswith('https://') or any(ch.isspace() for ch in url) or len(url) > 1000):
            raise HTTPException(400, 'ลิงก์ต้องเริ่มด้วย https://')

        def num(v, lo, hi, label):
            v = v.strip().replace(',', '')
            if not v:
                return None
            try:
                x = float(v)
            except ValueError:
                raise HTTPException(400, f'{label} ต้องเป็นตัวเลข')
            if not lo <= x <= hi:
                raise HTTPException(400, f'{label} ต้องอยู่ระหว่าง {lo}-{hi}')
            return x
        p = num(price, 0, 10_000_000, 'ราคา')
        rate = num(commission_rate, 0, 100, 'ค่าคอม %')
        image_url = image_url.strip()
        if image_url and (not image_url.startswith('https://') or len(image_url) > 1000 or any(ch.isspace() for ch in image_url)):
            raise HTTPException(400, 'ลิงก์รูปต้องเริ่มด้วย https://')
        fname = ''
        if image is not None and image.filename:
            ext = IMAGE_TYPES.get(image.content_type or '')
            data = await image.read(MAX_IMAGE_BYTES + 1)
            if not ext:
                raise HTTPException(400, 'รองรับรูป JPG, PNG, WEBP เท่านั้น')
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(400, 'รูปต้องไม่เกิน 5 MB')
            sig = data[:12]
            if not (sig.startswith(b'\xff\xd8\xff') or sig.startswith(b'\x89PNG') or (sig[:4] == b'RIFF' and sig[8:12] == b'WEBP')):
                raise HTTPException(400, 'ไฟล์ไม่ใช่รูปภาพที่ถูกต้อง')
            fname = secrets.token_urlsafe(16) + ext
            (media_dir / fname).write_bytes(data)
        comm_baht = round(p * rate / 100, 2) if p is not None and rate is not None else None
        with connect() as c:
            cur = c.execute('''INSERT INTO products(user_id,title,url,platform,created_at,price,commission_rate,commission_baht,
                               image_url,image_file,source) VALUES (?,?,?,?,?,?,?,?,?,?,'manual')''',
                            (u['id'], title, url, platform, now(), p, rate, comm_baht, image_url, fname))
        return {'id': cur.lastrowid, 'message': 'บันทึกสินค้า (กรอกเอง) เรียบร้อย'}

    def _fetch_product_image(url: str) -> str:
        """Best-effort server-side download of a Shopee-CDN image. Returns saved
        filename, or '' on any failure (caller then keeps the plain image_url)."""
        import requests
        if not file_import.image_link(url):
            return ''
        try:
            r = requests.get(url, timeout=12, stream=True,
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://shopee.co.th/'})
            if r.status_code != 200:
                return ''
            data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
        except requests.RequestException:
            return ''
        if not data or len(data) > MAX_IMAGE_BYTES:
            return ''
        sig = data[:12]
        if sig.startswith(b'\xff\xd8\xff'):
            ext = '.jpg'
        elif sig.startswith(b'\x89PNG'):
            ext = '.png'
        elif sig[:4] == b'RIFF' and sig[8:12] == b'WEBP':
            ext = '.webp'
        else:
            return ''
        fname = secrets.token_urlsafe(16) + ext
        (media_dir / fname).write_bytes(data)
        return fname

    @app.post('/api/my/products/import-file/preview')
    async def import_file_preview(req: Request, file: UploadFile = File(...),
                                  x_csrf_token: str | None = Header(default=None)):
        mutation(req, x_csrf_token)
        binary = await file.read(file_import.MAX_FILE_BYTES + 1)
        try:
            out = file_import.preview(binary, file.filename or '')
        except ValueError as e:
            raise HTTPException(400, str(e))
        out['filename'] = (file.filename or 'file')[:120]
        return out

    @app.post('/api/my/products/import-file/commit')
    async def import_file_commit(req: Request, file: UploadFile = File(...), mapping: str = Form('{}'),
                                 download_images: str = Form('1'), overwrite_images: str = Form('0'),
                                 x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        limit(u['id'], 'import_file', 10)
        binary = await file.read(file_import.MAX_FILE_BYTES + 1)
        try:
            mp = json.loads(mapping or '{}')
            if not isinstance(mp, dict):
                raise ValueError('mapping ไม่ถูกต้อง')
            items, skipped = file_import.build_items(binary, file.filename or '', mp)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except json.JSONDecodeError:
            raise HTTPException(400, 'mapping ไม่ถูกต้อง')
        want_img = download_images not in ('0', 'false', '', 'no')
        overwrite = overwrite_images in ('1', 'true', 'yes')
        added = updated = images = 0
        with connect() as c:
            for it in items:
                comm_baht = (round(it['price'] * it['commission_rate'] / 100, 2)
                             if it['price'] is not None and it['commission_rate'] is not None else None)
                # Same affiliate link (or same item id) → update in place, never duplicate.
                existing = None
                if it['url']:
                    existing = c.execute('SELECT id, image_file FROM products WHERE user_id=? AND offer_link=? AND offer_link!=""',
                                         (u['id'], it['url'])).fetchone()
                if not existing and it['item_id']:
                    existing = c.execute('SELECT id, image_file FROM products WHERE user_id=? AND item_id=? AND item_id!=""',
                                         (u['id'], it['item_id'])).fetchone()
                fname = ''
                have_img = existing and existing['image_file']
                if want_img and it['image_url'] and (overwrite or not have_img):
                    fname = _fetch_product_image(it['image_url'])
                    if fname:
                        images += 1
                if existing:
                    sets = ['title=?', 'price=?', 'commission_rate=?', 'commission_baht=?', 'image_url=?',
                            'item_id=?', 'offer_link=?', "source='file_import'"]
                    vals = [it['title'], it['price'], it['commission_rate'], comm_baht, it['image_url'],
                            it['item_id'], it['url']]
                    if fname:
                        old = existing['image_file']
                        sets.append('image_file=?')
                        vals.append(fname)
                        if old:
                            try:
                                (media_dir / old).unlink()
                            except OSError:
                                pass
                    c.execute(f'UPDATE products SET {",".join(sets)} WHERE id=? AND user_id=?',
                              vals + [existing['id'], u['id']])
                    updated += 1
                else:
                    c.execute('''INSERT INTO products(user_id,title,url,platform,created_at,price,commission_rate,
                                 commission_baht,image_url,image_file,item_id,offer_link,source)
                                 VALUES(?,?,?,'shopee',?,?,?,?,?,?,?,?,'file_import')''',
                              (u['id'], it['title'], it['url'], now(), it['price'], it['commission_rate'],
                               comm_baht, it['image_url'], fname, it['item_id'], it['url']))
                    added += 1
        return {'added': added, 'updated': updated, 'images': images, 'skipped': skipped,
                'total': added + updated,
                'message': f'นำเข้าสำเร็จ — เพิ่ม {added}, อัปเดต {updated} รายการ' + (f' · ดาวน์โหลดรูป {images}' if images else '')}

    @app.patch('/api/my/products/{product_id}')
    def patch_product(product_id: int, body: ProductPatchIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        """Edit the user's own product: name, affiliate link, price, commission, active toggle."""
        u = mutation(req, x_csrf_token)
        p = product_for(u['id'], product_id)
        sets, vals = [], []
        if body.title is not None:
            sets.append('title=?'); vals.append(body.title.strip())
        if body.offer_link is not None:
            link = body.offer_link.strip()
            if link and not file_import.aff_link(link):
                raise HTTPException(400, 'ลิงก์ affiliate ต้องเป็น https ของ shopee.co.th / s.shopee.co.th / shp.ee')
            sets.append('offer_link=?'); vals.append(link)
            if link and not p.get('url'):
                sets.append('url=?'); vals.append(link)
        if body.price is not None:
            sets.append('price=?'); vals.append(body.price)
        if body.commission_rate is not None:
            sets.append('commission_rate=?'); vals.append(body.commission_rate)
        if body.active is not None:
            sets.append('active=?'); vals.append(1 if body.active else 0)
        if not sets:
            raise HTTPException(400, 'ไม่มีข้อมูลที่จะแก้ไข')
        price = body.price if body.price is not None else p.get('price')
        rate = body.commission_rate if body.commission_rate is not None else p.get('commission_rate')
        if body.price is not None or body.commission_rate is not None:
            sets.append('commission_baht=?'); vals.append(round(price * rate / 100, 2) if price is not None and rate is not None else None)
        with connect() as c:
            c.execute(f'UPDATE products SET {",".join(sets)} WHERE id=? AND user_id=?', vals + [product_id, u['id']])
        return {'ok': True, 'id': product_id}

    @app.get('/api/my/products/import-file/sample.csv')
    def import_sample_csv():
        from fastapi.responses import Response
        rows = ['ชื่อสินค้า,ราคา,ลิงก์ affiliate,URL ภาพสินค้า,รหัสสินค้า',
                'หูฟังบลูทูธ TWS รุ่นใหม่,199,https://s.shopee.co.th/xxxxxxxx,,',
                'เซรั่มบำรุงผิวหน้า,390,,,']
        return Response(('\ufeff' + '\n'.join(rows) + '\n').encode('utf-8'), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="product-import-sample.csv"'})

    @app.get('/api/my/products/import-file/sample.xlsx')
    def import_sample_xlsx():
        import io
        from fastapi.responses import Response
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(503, 'เซิร์ฟเวอร์ยังไม่มี openpyxl — ใช้ไฟล์ตัวอย่าง .csv แทน')
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'products'
        ws.append(['ชื่อสินค้า', 'ราคา', 'ลิงก์ affiliate', 'URL ภาพสินค้า', 'รหัสสินค้า'])
        ws.append(['หูฟังบลูทูธ TWS รุ่นใหม่', 199, 'https://s.shopee.co.th/xxxxxxxx', '', ''])
        ws.append(['เซรั่มบำรุงผิวหน้า', 390, '', '', ''])
        for col, w in zip('ABCDE', (34, 10, 36, 44, 16)):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO(); wb.save(buf)
        return Response(buf.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': 'attachment; filename="product-import-sample.xlsx"'})

    @app.post('/api/my/products/bulk-delete')
    def bulk_delete_products(body: BulkDeleteIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        """Remove every product of one source for this user (e.g. a mistaken file import)."""
        u = mutation(req, x_csrf_token)
        if body.source not in ('file_import', 'manual', 'radar'):
            raise HTTPException(400, 'ลบได้เฉพาะสินค้าที่นำเข้าจากไฟล์ กรอกเอง หรือจาก Radar')
        rows = read('SELECT id, image_file FROM products WHERE user_id=? AND source=?', (u['id'], body.source))
        with connect() as c:
            c.execute('DELETE FROM products WHERE user_id=? AND source=?', (u['id'], body.source))
        for r in rows:
            if r['image_file']:
                try:
                    (media_dir / r['image_file']).unlink()
                except OSError:
                    pass
        return {'deleted': len(rows), 'message': f'ลบสินค้า {len(rows)} รายการแล้ว'}

    @app.get('/media/products/{name}')
    def product_media(name: str):
        if not re.fullmatch(r'[A-Za-z0-9_\-]{16,40}\.(jpg|png|webp)', name):
            raise HTTPException(404, 'not found')
        path = media_dir / name
        if not path.is_file():
            raise HTTPException(404, 'not found')
        return FileResponse(path, headers={'Cache-Control': 'public, max-age=86400'})

    @app.delete('/api/my/products/{product_id}')
    def delete_product(product_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = product_for(u['id'], product_id)
        with connect() as c:
            c.execute('DELETE FROM products WHERE id=? AND user_id=?', (product_id, u['id']))
        if p.get('image_file'):
            try:
                (media_dir / p['image_file']).unlink()
            except OSError:
                pass
        return {'ok': True}

    return hub
