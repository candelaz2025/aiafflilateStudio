"""Affiliate Auto Studio Community V7: local pre-release multi-user foundation.
NOT an internet-production system. The V6 automation endpoints are deliberately NOT exposed.
"""
from __future__ import annotations
import base64
import hashlib
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Header, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from urllib.parse import urlsplit
from studio_v6.product_discovery import discover, trending_topics
from studio_v6 import video_service as veo
from studio_v6 import grok_service as grok
from studio_v6.shopee_user_import import pasted_preview, report_preview

ROOT = Path(__file__).resolve().parent
PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
SESSION_DAYS = 7
MAX_BETA_USERS = max(1, int(os.getenv('MAX_BETA_USERS', '100')))
REQUIRE_INVITE = os.getenv('BETA_INVITE_CODE', '').strip()
PUBLIC_MODE = os.getenv('PUBLIC_DEPLOYMENT') == '1'
PROVIDERS = ('gemini', 'xai', 'brave', 'openai')
GROK_MODELS = grok.MODELS
VEO_MODEL = 'veo-3.1-generate-preview'
MAX_VIDEO_JOBS_PER_DAY = 3
# Provider calls time out well within this; a 'submitting' row older than this was orphaned
# by a crash/restart and must not block the member forever.
STALE_SUBMIT_MINUTES = 5
STALE_SUBMIT_MESSAGE = 'ส่งงานไม่สำเร็จหรือขาดการติดต่อระหว่างส่ง โปรดตรวจการใช้เครดิตในบัญชีผู้ให้บริการก่อนสั่งใหม่'
STATES = ('proposed', 'planned', 'building', 'released', 'declined')
DONATION_BANK = {
    'bank': 'ธนาคารไทยพาณิชย์ (SCB)',
    'account_number': '4210116946',
    'account_name': 'นาย กฤตลักษณ์ สุขใส',
    'purpose': 'สนับสนุนค่าดูแลเซิร์ฟเวอร์และพัฒนา Affiliate Auto Studio',
    'notice': 'การสนับสนุนเป็นความสมัครใจ ไม่ใช่ค่าสมัครหรือการซื้อฟีเจอร์ และไม่ใช่เงินบริจาคที่ยืนยันสิทธิลดหย่อนภาษี',
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def get_key(data_dir: Path, key_override=None):
    if key_override:
        return key_override if isinstance(key_override, bytes) else key_override.encode()
    override = os.getenv('APP_MASTER_KEY', '').strip()
    if override:
        return override.encode()
    if os.getenv('PUBLIC_DEPLOYMENT') == '1':
        raise RuntimeError('PUBLIC_DEPLOYMENT requires APP_MASTER_KEY from a secret manager')
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / 'community.key'
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(key)
    return key


class AuthBody(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=12, max_length=128)

class Register(AuthBody):
    username: str = Field(min_length=3, max_length=32)
    invite_code: str = Field(default='', max_length=128)

class IdeaIn(BaseModel):
    kind: str = Field(default='feature')
    title: str = Field(min_length=5, max_length=110)
    body: str = Field(min_length=10, max_length=2000)

class CommentIn(BaseModel):
    body: str = Field(min_length=2, max_length=800)

class KeyIn(BaseModel):
    key: str = Field(min_length=8, max_length=1500)

class StatusIn(BaseModel):
    status: str

class DonationReportIn(BaseModel):
    amount_baht: Decimal = Field(gt=0, le=1000000, max_digits=9, decimal_places=2)
    note: str = Field(default='', max_length=200)

class DonationStatusIn(BaseModel):
    status: str

class DraftIn(BaseModel):
    product_id: int = Field(gt=0)
    style: str = Field(default='pov', max_length=32)

class QueueIn(BaseModel):
    draft_id: int = Field(gt=0)
    platform: str
    video_url: str = Field(default='', max_length=1500)
    video_job_id: int | None = Field(default=None, gt=0)

class QueueStatusIn(BaseModel):
    status: str

class ProductIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    url: str = Field(default='', max_length=1000)
    platform: str
    extra_comm_checked: bool = False
    extra_comm_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class ShopeeCopiedIn(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class ExtraCommIn(BaseModel):
    checked: bool
    rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class PerformanceIn(BaseModel):
    # Cumulative metrics for ONE draft/video, not additive snapshots.
    views: int = Field(ge=0, le=1000000000)
    clicks: int = Field(ge=0, le=1000000000)
    orders: int = Field(ge=0, le=100000000)
    sales_baht: Decimal = Field(default=Decimal('0'), ge=0, le=1000000000, max_digits=12, decimal_places=2)
    commission_baht: Decimal = Field(default=Decimal('0'), ge=0, le=1000000000, max_digits=12, decimal_places=2)
    note: str = Field(default='', max_length=300)


class UserRoleIn(BaseModel):
    role: str


class UserCreateIn(BaseModel):
    username: str
    email: str
    password: str
    role: str = 'member'


def create_app(data_dir=None, secret_key=None):
    data = Path(data_dir or os.getenv('COMMUNITY_DATA_DIR', ROOT / 'data')).resolve()
    data.mkdir(parents=True, exist_ok=True)
    db_path = data / 'community.db'
    if PUBLIC_MODE and not REQUIRE_INVITE:
        raise RuntimeError('PUBLIC_DEPLOYMENT requires BETA_INVITE_CODE to protect the 100 beta seats')
    cipher = Fernet(get_key(data, secret_key))
    app = FastAPI(title='Affiliate Auto Studio — V7.10 Shopee Import Beta100', version='0.7.10')

    @app.middleware("http")
    async def add_no_cache_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static") or path in ("/updates", "/donate", "/landing", "/community"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    def connect():
        c = sqlite3.connect(db_path, timeout=12)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','admin')),
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS credentials (
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          provider TEXT NOT NULL, encrypted TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(user_id, provider));
        CREATE TABLE IF NOT EXISTS ideas (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
          kind TEXT NOT NULL CHECK(kind IN ('feature','bug','feedback')),
          title TEXT NOT NULL, body TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'proposed', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS votes (
          idea_id INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          PRIMARY KEY(idea_id,user_id));
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          idea_id INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS donation_reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          amount_satang INTEGER NOT NULL CHECK(amount_satang > 0),
          note TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','rejected')),
          created_at TEXT NOT NULL, verified_at TEXT,
          verified_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
        CREATE INDEX IF NOT EXISTS donation_reports_user_idx ON donation_reports(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS login_failures (
          email TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset_at TEXT NOT NULL);
        -- V7.11: throttle per (email, client IP) so failures from one address cannot lock out the owner.
        CREATE TABLE IF NOT EXISTS login_attempts (
          email TEXT NOT NULL, ip TEXT NOT NULL, attempts INTEGER NOT NULL, reset_at TEXT NOT NULL,
          PRIMARY KEY(email, ip));
        CREATE TABLE IF NOT EXISTS drafts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          style TEXT NOT NULL, script TEXT NOT NULL, prompt TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS drafts_owner ON drafts(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS publishing_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
          platform TEXT NOT NULL CHECK(platform IN ('tiktok','shopee')),
          video_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'needs_review'
          CHECK(status IN ('needs_review','ready_manual','completed_manual','cancelled')),
          created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS queue_owner ON publishing_queue(user_id,id DESC);
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
          platform TEXT NOT NULL CHECK(platform IN ('tiktok','shopee','other')),
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS product_use_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          draft_id INTEGER NOT NULL UNIQUE REFERENCES drafts(id) ON DELETE CASCADE,
          use_number INTEGER NOT NULL CHECK(use_number>0),
          created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS product_use_owner_idx
          ON product_use_events(user_id,product_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS draft_performance (
          draft_id INTEGER PRIMARY KEY REFERENCES drafts(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          views INTEGER NOT NULL DEFAULT 0 CHECK(views>=0),
          clicks INTEGER NOT NULL DEFAULT 0 CHECK(clicks>=0),
          orders INTEGER NOT NULL DEFAULT 0 CHECK(orders>=0),
          sales_satang INTEGER NOT NULL DEFAULT 0 CHECK(sales_satang>=0),
          commission_satang INTEGER NOT NULL DEFAULT 0 CHECK(commission_satang>=0),
          note TEXT NOT NULL DEFAULT '',
          recorded_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS draft_performance_owner_idx ON draft_performance(user_id);
        CREATE TABLE IF NOT EXISTS video_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
          provider TEXT NOT NULL DEFAULT 'gemini',
          model TEXT NOT NULL DEFAULT 'veo-3.1-generate-preview',
          duration INTEGER NOT NULL DEFAULT 8,
          prompt TEXT NOT NULL,
          operation_name TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL CHECK(status IN ('submitting','running','ready','failed')),
          file_name TEXT NOT NULL DEFAULT '',
          error_message TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          checked_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS video_jobs_owner ON video_jobs(user_id,id DESC);
        ''')
        # Safe migration for data created by previous V7.4/V7.5 installations.
        columns = {row[1] for row in db.execute('PRAGMA table_info(products)')}
        for name, ddl in [('extra_comm_checked','INTEGER NOT NULL DEFAULT 0'),
                          ('extra_comm_rate','REAL'), ('extra_comm_checked_at','TEXT')]:
            if name not in columns:
                db.execute(f'ALTER TABLE products ADD COLUMN {name} {ddl}')
        # Non-destructive migration: V7.8 had provider but no selected model/duration.
        video_columns={row[1] for row in db.execute('PRAGMA table_info(video_jobs)')}
        if 'model' not in video_columns:
            db.execute("ALTER TABLE video_jobs ADD COLUMN model TEXT NOT NULL DEFAULT 'veo-3.1-generate-preview'")
        if 'duration' not in video_columns:
            db.execute('ALTER TABLE video_jobs ADD COLUMN duration INTEGER NOT NULL DEFAULT 8')
        # Backfill old V7.4–V7.6 drafts into the usage timeline without deleting data.
        # Deterministic counts/order; rerunning application startup is idempotent.
        db.execute('''INSERT OR IGNORE INTO product_use_events
                      (user_id,product_id,draft_id,use_number,created_at)
                      SELECT user_id,product_id,id,
                             ROW_NUMBER() OVER (PARTITION BY user_id,product_id ORDER BY created_at,id),
                             created_at FROM drafts''')

    def read(sql, params=(), one=False):
        with connect() as c:
            rs = c.execute(sql, params)
            vals = [dict(v) for v in rs.fetchall()]
        return (vals[0] if vals else None) if one else vals

    def require_user(req: Request, csrf=None):
        raw = req.cookies.get('community_session')
        if not raw:
            raise HTTPException(401, 'กรุณาเข้าสู่ระบบ')
        digest = hashlib.sha256(raw.encode()).hexdigest()
        session = read('''SELECT u.id,u.username,u.email,u.role,s.csrf,s.expires_at
           FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (digest,), True)
        if not session or session['expires_at'] <= now():
            raise HTTPException(401, 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบอีกครั้ง')
        if csrf is not None and not secrets.compare_digest(session['csrf'], csrf):
            raise HTTPException(403, 'CSRF token ไม่ถูกต้อง')
        return session

    def mutation(req: Request, csrf: str | None):
        return require_user(req, csrf or '')

    def new_session(user, resp: Response):
        token = secrets.token_urlsafe(40)
        csrf = secrets.token_urlsafe(24)
        expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec='seconds')
        with connect() as c:
            c.execute('DELETE FROM sessions WHERE expires_at<=?',(now(),))
            c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                      (hashlib.sha256(token.encode()).hexdigest(), user['id'], csrf, expires))
        # Secure cookies are mandatory when running with TLS/public deployment.
        secure = os.getenv('COOKIE_SECURE') == '1' or os.getenv('PUBLIC_DEPLOYMENT') == '1'
        resp.set_cookie('community_session', token, httponly=True, secure=secure,
                        samesite='strict', max_age=SESSION_DAYS * 86400, path='/')
        return {'username': user['username'], 'role': user['role'], 'csrf': csrf}

    # Headers and simple same-process throttling are a defense-in-depth layer, not a WAF.
    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        if PUBLIC_MODE:
            response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        return response

    @app.get('/api/system/version')
    def system_version():
        return {'version': '0.7.10', 'channel': 'beta100', 'updates': 'offline-windows-patches', 'studio':'member-private', 'legacy_studio':'local-admin-only'}

    @app.get('/updates')
    def updates():
        return FileResponse(ROOT / 'static' / 'updates.html')

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'static' / 'index.html')

    @app.get('/donate')
    def donate():
        return FileResponse(ROOT / 'static' / 'donate.html')

    @app.get('/landing')
    def landing():
        return FileResponse(ROOT / 'static' / 'landing.html')

    @app.get('/community')
    def community():
        return FileResponse(ROOT / 'static' / 'community.html')

    @app.get('/api/donate/info')
    def donation_info():
        return DONATION_BANK

    @app.get('/health')
    def health():
        return {'ok': True, 'mode': 'beta100', 'member_studio':True, 'public_deploy':PUBLIC_MODE}

    @app.get('/api/beta/capacity')
    def beta_capacity():
        n = read('SELECT COUNT(*) AS n FROM users',one=True)['n']
        return {'limit':MAX_BETA_USERS,'registered':n,'remaining':max(0,MAX_BETA_USERS-n),
                'invite_only':bool(REQUIRE_INVITE)}

    @app.post('/api/register')
    def register(item: Register, response: Response):
        email = item.email.strip().lower()
        username = item.username.strip()
        if not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username):
            raise HTTPException(400, 'ชื่อผู้ใช้ต้องมีเฉพาะอังกฤษ ตัวเลข หรือ _')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(400, 'อีเมลไม่ถูกต้อง')
        if not any(c.isalpha() for c in item.password) or not any(c.isdigit() for c in item.password):
            raise HTTPException(400, 'รหัสผ่านต้องมีตัวอักษรและตัวเลข')
        if REQUIRE_INVITE and not secrets.compare_digest(item.invite_code, REQUIRE_INVITE):
            raise HTTPException(403, 'ต้องใช้รหัสเชิญเข้าร่วม Beta')
        # Serialize capacity check and insert to avoid over-registering during races.
        try:
            with connect() as c:
                c.execute('BEGIN IMMEDIATE')
                total = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
                if total >= MAX_BETA_USERS:
                    raise HTTPException(409,'Beta เต็มจำนวนแล้ว กรุณารอเปิดรอบต่อไป')
                cur = c.execute('INSERT INTO users(username,email,password_hash,created_at) VALUES(?,?,?,?)',
                                (username,email,PH.hash(item.password),now()))
                uid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'อีเมลหรือชื่อผู้ใช้มีอยู่แล้ว')
        return new_session({'id':uid, 'username':username, 'role':'member'},response)

    @app.post('/api/login')
    def login(item: AuthBody, req: Request, response: Response):
        email=item.email.strip().lower()
        # Behind Caddy, uvicorn --proxy-headers sets the real client address.
        ip=req.client.host if req.client else ''
        failure=read('SELECT * FROM login_attempts WHERE email=? AND ip=?',(email,ip),True)
        if failure and failure['attempts']>=8 and failure['reset_at']>now():
            raise HTTPException(429,'ลองผิดหลายครั้ง โปรดลองใหม่อีก 15 นาที')
        user=read('SELECT * FROM users WHERE email=?',(email,),True)
        try:
            if not user:
                # Keep a similar password-hashing workload for non-existent accounts.
                PH.hash(item.password)
                raise VerifyMismatchError('')
            PH.verify(user['password_hash'],item.password)
        except (VerifyMismatchError, VerificationError):
            reset=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(timespec='seconds')
            with connect() as c:
                # Expired rows are dead weight; unknown emails would otherwise accumulate forever.
                c.execute('DELETE FROM login_attempts WHERE reset_at<=?',(now(),))
                if failure and failure['reset_at']>now():
                    c.execute('UPDATE login_attempts SET attempts=attempts+1 WHERE email=? AND ip=?',(email,ip))
                else:
                    c.execute('INSERT INTO login_attempts VALUES(?,?,?,?) ON CONFLICT(email,ip) DO UPDATE SET attempts=excluded.attempts, reset_at=excluded.reset_at',(email,ip,1,reset))
            raise HTTPException(401,'อีเมลหรือรหัสผ่านไม่ถูกต้อง')
        with connect() as c:
            c.execute('DELETE FROM login_attempts WHERE email=? AND ip=?',(email,ip))
        return new_session(user,response)

    @app.get('/api/me')
    def me(req: Request):
        u=require_user(req)
        return {'id':u['id'],'username':u['username'],'role':u['role'],'csrf':u['csrf']}

    @app.post('/api/logout')
    def logout(req: Request, response: Response, x_csrf_token: str | None = Header(default=None)):
        mutation(req,x_csrf_token)
        raw=req.cookies.get('community_session')
        with connect() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),))
        response.delete_cookie('community_session',path='/')
        return {'ok':True}

    @app.get('/api/ideas')
    def ideas(req:Request, order:str='top'):
        u=require_user(req)
        if order not in ('top','new'):
            raise HTTPException(400,'เลือกการเรียงลำดับไม่ถูกต้อง')
        ordering='votes DESC,i.id DESC' if order=='top' else 'i.id DESC'
        return read(f'''SELECT i.id,i.kind,i.title,i.body,i.status,i.created_at,u.username AS author,
              COUNT(v.user_id) AS votes,
              MAX(CASE WHEN v.user_id=? THEN 1 ELSE 0 END) AS voted,
              (SELECT COUNT(*) FROM comments c WHERE c.idea_id=i.id) AS comments
            FROM ideas i JOIN users u ON u.id=i.user_id LEFT JOIN votes v ON v.idea_id=i.id
            GROUP BY i.id ORDER BY {ordering} LIMIT 150''',(u['id'],))

    @app.post('/api/ideas')
    def add_idea(req:Request, item:IdeaIn, x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if item.kind not in ('feature','bug','feedback'):
            raise HTTPException(400,'หมวดไม่ถูกต้อง')
        with connect() as c:
            cur=c.execute('INSERT INTO ideas(user_id,kind,title,body,status,created_at) VALUES(?,?,?,?,?,?)',
                          (u['id'],item.kind,item.title.strip(),item.body.strip(),'proposed',now()))
        return {'id':cur.lastrowid,'status':'proposed'}

    @app.post('/api/ideas/{idea_id}/vote')
    def toggle_vote(idea_id:int,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if not read('SELECT id FROM ideas WHERE id=?',(idea_id,),True):
            raise HTTPException(404,'ไม่พบไอเดีย')
        with connect() as c:
            present=c.execute('SELECT 1 FROM votes WHERE idea_id=? AND user_id=?',(idea_id,u['id'])).fetchone()
            if present:
                c.execute('DELETE FROM votes WHERE idea_id=? AND user_id=?',(idea_id,u['id']))
            else:
                c.execute('INSERT INTO votes(idea_id,user_id) VALUES(?,?)',(idea_id,u['id']))
        return {'voted':not bool(present)}

    @app.get('/api/ideas/{idea_id}/comments')
    def get_comments(idea_id:int,req:Request):
        require_user(req)
        if not read('SELECT id FROM ideas WHERE id=?',(idea_id,),True):
            raise HTTPException(404,'ไม่พบไอเดีย')
        return read('''SELECT c.id,u.username AS author,c.body,c.created_at FROM comments c
            JOIN users u ON c.user_id=u.id WHERE c.idea_id=? ORDER BY c.id LIMIT 200''',(idea_id,))

    @app.post('/api/ideas/{idea_id}/comments')
    def add_comment(idea_id:int, item:CommentIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if not read('SELECT id FROM ideas WHERE id=?',(idea_id,),True):
            raise HTTPException(404,'ไม่พบไอเดีย')
        with connect() as c:
            cur=c.execute('INSERT INTO comments(idea_id,user_id,body,created_at) VALUES(?,?,?,?)',
                          (idea_id,u['id'],item.body.strip(),now()))
        return {'id':cur.lastrowid}

    @app.patch('/api/ideas/{idea_id}/status')
    def change_status(idea_id:int,item:StatusIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if u['role']!='admin':
            raise HTTPException(403,'เฉพาะผู้ดูแลระบบ')
        if item.status not in STATES:
            raise HTTPException(400,'สถานะไม่ถูกต้อง')
        with connect() as c:
            result=c.execute('UPDATE ideas SET status=? WHERE id=?',(item.status,idea_id))
            if result.rowcount<1:
                raise HTTPException(404,'ไม่พบไอเดีย')
        return {'ok':True,'status':item.status}

    @app.get('/api/my/keys')
    def key_status(req:Request):
        u=require_user(req)
        found=read('SELECT provider,created_at FROM credentials WHERE user_id=?',(u['id'],))
        return {'supported':PROVIDERS,'connected':found,
                'note':'คีย์ของแต่ละบัญชีเข้ารหัสไว้ ไม่ส่งกลับให้หน้าเว็บ'}

    @app.put('/api/my/keys/{provider}')
    def save_key(provider:str,body:KeyIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if provider not in PROVIDERS:
            raise HTTPException(400,'ผู้ให้บริการนี้ยังไม่รองรับการเก็บ API key')
        value=body.key.strip()
        if not value or any(ch in value for ch in '\r\n\x00'):
            raise HTTPException(400,'API key ไม่ถูกต้อง')
        encrypted=cipher.encrypt(value.encode()).decode()
        with connect() as c:
            c.execute('''INSERT INTO credentials(user_id,provider,encrypted,created_at)
                VALUES(?,?,?,?) ON CONFLICT(user_id,provider) DO UPDATE SET
                encrypted=excluded.encrypted, created_at=excluded.created_at''',
                (u['id'],provider,encrypted,now()))
        return {'saved':True,'provider':provider}

    @app.delete('/api/my/keys/{provider}')
    def delete_key(provider:str,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if provider not in PROVIDERS:
            raise HTTPException(400,'ผู้ให้บริการไม่ถูกต้อง')
        with connect() as c:
            c.execute('DELETE FROM credentials WHERE user_id=? AND provider=?',(u['id'],provider))
        return {'deleted':True}

    @app.get('/api/my/connections')
    def my_connections(req: Request):
        u=require_user(req)
        saved={r['provider'] for r in read('SELECT provider FROM credentials WHERE user_id=?',(u['id'],))}
        return {'providers':[
            {'id':'gemini','label':'Google Gemini / Veo','configured':'gemini' in saved,'supports':'สร้างวิดีโอแนวตั้ง 8 วินาทีผ่าน Gemini API','enabled':True,'verified':False},
            {'id':'xai','label':'xAI / Grok Imagine','configured':'xai' in saved,'supports':'สร้างวิดีโอแนวตั้ง 10 วินาที (Lite / 1.5) ผ่าน xAI API','enabled':True,'verified':False},
            {'id':'brave','label':'Brave Search','configured':'brave' in saved,'supports':'ค้นหาหน้าสินค้าภายนอก','enabled':True,'verified':False},
            {'id':'openai','label':'OpenAI','configured':'openai' in saved,'supports':'เก็บคีย์ไว้ใช้กับฟีเจอร์ในอนาคต (ยังไม่เรียกใช้)','enabled':False,'verified':False},
            {'id':'tiktok','label':'TikTok Shop / Creator','configured':False,'supports':'ต้องเชื่อม OAuth และได้รับสิทธิ์เผยแพร่จาก TikTok','enabled':False,'verified':False},
            {'id':'shopee','label':'Shopee Affiliate / Video','configured':False,'supports':'ยังไม่มีช่องทางโพสต์อัตโนมัติที่เปิดให้ระบบนี้ใช้','enabled':False,'verified':False},
        ],'note':'บันทึกคีย์แล้วไม่ได้แปลว่า API มีเครดิต/สิทธิ์ใช้งาน โปรดตรวจสิทธิ์กับผู้ให้บริการ'}

    @app.get('/api/my/video-jobs')
    def list_video_jobs(req: Request):
        u=require_user(req)
        return read("""SELECT v.id,v.draft_id,v.provider,v.model,v.duration,v.status,v.prompt,v.error_message,v.created_at,
                      v.checked_at,v.updated_at,p.title
                      FROM video_jobs v JOIN drafts d ON d.id=v.draft_id
                      JOIN products p ON p.id=d.product_id
                      WHERE v.user_id=? ORDER BY v.id DESC LIMIT 50""", (u['id'],))

    def stale_submit_cutoff():
        return (datetime.now(timezone.utc)-timedelta(minutes=STALE_SUBMIT_MINUTES)).isoformat(timespec='seconds')

    def load_api_key(user_id, provider):
        row=read('SELECT encrypted FROM credentials WHERE user_id=? AND provider=?',(user_id,provider),True)
        if not row: raise HTTPException(400, 'กรุณาเชื่อม '+('xAI / Grok Imagine' if provider=='xai' else 'Google Gemini / Veo')+' API ในเมนู API ของฉันก่อน')
        try: return cipher.decrypt(row['encrypted'].encode()).decode()
        except InvalidToken: raise HTTPException(400,'ถอดรหัสคีย์ไม่ได้ กรุณาบันทึกคีย์ใหม่')

    @app.post('/api/my/video-jobs')
    async def create_video_job(req: Request, draft_id: int = Form(...),
                         provider: str = Form('gemini'), model: str = Form('veo-3.1-generate-preview'),
                         confirm_paid: bool = Form(False),
                         prompt: str = Form(''),
                         image: UploadFile | None = File(default=None),
                         x_csrf_token: str | None = Header(default=None)):
        u=mutation(req,x_csrf_token)
        if not confirm_paid:
            raise HTTPException(400,'ต้องยืนยันว่าการสร้างวิดีโออาจมีค่าใช้จ่ายตามเครดิต API ก่อน')
        owned=read('SELECT id,prompt FROM drafts WHERE id=? AND user_id=?',(draft_id,u['id']),True)
        if not owned: raise HTTPException(404,'ไม่พบบทของบัญชีนี้')
        if provider=='gemini' and model==VEO_MODEL:
            duration=8
            service=veo
        elif provider=='xai' and model in GROK_MODELS:
            duration=10
            service=grok
        else:
            raise HTTPException(400,'ผู้ให้บริการกับโมเดลที่เลือกไม่ตรงกัน')
        api_key=load_api_key(u['id'],provider)
        final_prompt=(prompt.strip() or owned['prompt'].strip())
        if len(final_prompt)<15 or len(final_prompt)>1200:
            raise HTTPException(400,'Prompt ต้องยาว 15–1,200 ตัวอักษร')
        # Do not let a user request an undisclosed large/multiple generation.
        reference = None
        mime = None
        if image is not None and image.filename:
            mime=image.content_type
            if mime not in ('image/png','image/jpeg'):
                raise HTTPException(400,'รูปอ้างอิงต้องเป็น JPG หรือ PNG เท่านั้น')
            reference=await image.read(5*1024*1024+1)
            if len(reference)>5*1024*1024 or not reference:
                raise HTTPException(400,'รูปอ้างอิงต้องมีขนาด 1 byte ถึง 5MB')
            import io
            from PIL import Image
            try:
                im=Image.open(io.BytesIO(reference))
                im.verify()
                if im.width * im.height > 12000000:
                    raise ValueError('image pixel limit')
                if (im.format=='JPEG' and mime!='image/jpeg') or (im.format=='PNG' and mime!='image/png'):
                    raise ValueError('image format mismatch')
            except Exception:
                raise HTTPException(400,'ไฟล์รูปอ้างอิงไม่ถูกต้อง')
        # Reserve exactly one in-flight slot per user, atomically.
        # Committed on its own so a 409/429 below cannot roll the cleanup back.
        with connect() as c:
            c.execute("UPDATE video_jobs SET status='failed',error_message=?,updated_at=? WHERE user_id=? AND status='submitting' AND updated_at<?",
                      (STALE_SUBMIT_MESSAGE,now(),u['id'],stale_submit_cutoff()))
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            active=c.execute("SELECT COUNT(*) FROM video_jobs WHERE user_id=? AND status IN ('submitting','running')",(u['id'],)).fetchone()[0]
            if active:
                raise HTTPException(409,'มีงานกำลังสร้างอยู่แล้ว กรุณารอให้เสร็จก่อน')
            usage=c.execute("SELECT COUNT(*) FROM video_jobs WHERE user_id=? AND created_at>=?",(u['id'],datetime.now(timezone.utc).date().isoformat())).fetchone()[0]
            if usage>=MAX_VIDEO_JOBS_PER_DAY:
                raise HTTPException(429,'จำกัดสร้างวิดีโอไม่เกิน 3 ครั้งต่อวันต่อบัญชีใน Beta')
            timestamp=now()
            cur=c.execute("INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,created_at,checked_at,updated_at) VALUES(?,?,?,?,?,?,'submitting',?,?,?)",
                          (u['id'],draft_id,provider,model,duration,final_prompt,timestamp,timestamp,timestamp))
            job_id=cur.lastrowid
        try:
            # Run potentially slow HTTP requests outside the async event loop.
            from starlette.concurrency import run_in_threadpool
            if provider=='xai':
                operation=await run_in_threadpool(grok.start_video,api_key,final_prompt,reference,mime,model=model,duration=duration)
            else:
                operation=await run_in_threadpool(veo.start_video,api_key,final_prompt,reference,mime)
        except (veo.VideoProviderError, grok.VideoProviderError) as e:
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message=?,updated_at=? WHERE id=? AND user_id=?",(str(e)[:280],now(),job_id,u['id']))
            raise HTTPException(502,str(e))
        except Exception:
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message='ไม่สามารถส่งงานไปยังผู้ให้บริการ AI ได้',updated_at=? WHERE id=? AND user_id=?",(now(),job_id,u['id']))
            raise HTTPException(502,'ไม่สามารถส่งงานไปยังผู้ให้บริการ AI ได้')
        with connect() as c:
            c.execute("UPDATE video_jobs SET status='running',operation_name=?,updated_at=? WHERE id=? AND user_id=?",(operation,now(),job_id,u['id']))
        return {'id':job_id,'status':'running','provider':provider,'model':model,'duration':duration,'notice':'ส่งงานให้ '+('xAI Grok' if provider=='xai' else 'Google Veo')+' แล้ว กรุณาตรวจสถานะตามรอบ (มีค่าใช้จ่ายตาม API ของสมาชิก)'}

    @app.post('/api/my/video-jobs/{job_id}/refresh')
    def refresh_video_job(job_id:int,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        job=read('SELECT * FROM video_jobs WHERE id=? AND user_id=?',(job_id,u['id']),True)
        if not job: raise HTTPException(404,'ไม่พบงานวิดีโอนี้')
        if job['status']=='submitting' and job['updated_at']<stale_submit_cutoff():
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message=?,updated_at=? WHERE id=? AND user_id=? AND status='submitting'",
                          (STALE_SUBMIT_MESSAGE,now(),job_id,u['id']))
            return {'id':job_id,'status':'failed','notice':STALE_SUBMIT_MESSAGE}
        if job['status'] in ('failed','ready','submitting'):
            return {'id':job_id,'status':job['status'],'note':'งานนี้ไม่ต้องตรวจสถานะซ้ำ'}
        if job['status']!='running': raise HTTPException(409,'งานนี้ไม่อยู่ระหว่างสร้าง')
        # Debounce high-frequency polling; limit duplicate provider calls.
        if (datetime.now(timezone.utc)-datetime.fromisoformat(job['checked_at'])).total_seconds() < 8:
            return {'id':job_id,'status':'running','notice':'โปรดรอประมาณ 8 วินาทีก่อนตรวจอีกครั้ง'}
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            changed=c.execute('UPDATE video_jobs SET checked_at=? WHERE id=? AND user_id=? AND checked_at=?',
                              (now(),job_id,u['id'],job['checked_at']))
            if changed.rowcount != 1:
                return {'id':job_id,'status':'running','notice':'กำลังตรวจสถานะอยู่'}
        provider=job['provider']
        if provider not in ('gemini','xai'):
            raise HTTPException(400,'ไม่รู้จักผู้ให้บริการที่บันทึกไว้')
        api_key=load_api_key(u['id'],provider)
        service=grok if provider=='xai' else veo
        try:
            state, uri=service.poll_video(api_key,job['operation_name'])
            if state=='running': return {'id':job_id,'status':'running'}
            target=data/'videos'/str(u['id'])/f'{job_id}.mp4'
            service.download_video(api_key,uri,target)
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='ready',file_name=?,updated_at=? WHERE id=? AND user_id=?",(str(target.relative_to(data)),now(),job_id,u['id']))
            return {'id':job_id,'status':'ready','video_url':f'/api/my/video-jobs/{job_id}/file'}
        except (veo.VideoProviderError, grok.VideoProviderError) as e:
            # Transient API errors should be retryable; a provider rejection is terminal.
            error=str(e)[:280]
            if 'เชื่อมต่อ' in error or 'ขัดข้อง' in error or 'ดาวน์โหลด' in error or 'ตรวจสถานะ' in error:
                return {'id':job_id,'status':'running','notice':error+' กรุณาลองใหม่'}
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message=?,updated_at=? WHERE id=? AND user_id=?",(error,now(),job_id,u['id']))
            return {'id':job_id,'status':'failed','notice':error}

    @app.get('/api/my/video-jobs/{job_id}/file')
    def get_video_file(job_id:int,req:Request):
        u=require_user(req)
        job=read('SELECT file_name,status FROM video_jobs WHERE id=? AND user_id=?',(job_id,u['id']),True)
        if not job or job['status']!='ready': raise HTTPException(404,'ไม่พบวิดีโอพร้อมใช้งาน')
        expected=f'videos/{u["id"]}/{job_id}.mp4'
        if job['file_name'] != expected: raise HTTPException(404,'ไฟล์วิดีโอไม่ถูกต้อง')
        location=data/expected
        if not location.is_file(): raise HTTPException(404,'ไม่พบไฟล์วิดีโอในระบบจัดเก็บ')
        return FileResponse(location,media_type='video/mp4',filename=f'video_{job_id}.mp4',content_disposition_type='inline',
                            headers={'Cache-Control':'private, no-store'})

    @app.post('/api/my/donation-reports')
    def report_donation(body:DonationReportIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        # Money stored in integer satang, without floating-point rounding.
        satang = int(body.amount_baht * 100)
        note = body.note.strip()
        if len(note) > 200:
            raise HTTPException(400, 'หมายเหตุยาวเกินไป')
        with connect() as c:
            cur=c.execute('''INSERT INTO donation_reports
                (user_id,amount_satang,note,status,created_at)
                VALUES(?,?,?,'pending',?)''',(u['id'],satang,note,now()))
        return {'id':cur.lastrowid,'status':'pending',
                'message':'บันทึกการแจ้งโอนแล้ว รอผู้ดูแลตรวจสอบยอดเงินจริง ไม่ใช่หลักฐานว่าได้รับเงิน'}

    @app.get('/api/my/donation-reports')
    def my_donation_reports(req:Request):
        u=require_user(req)
        return read('''SELECT id,amount_satang,note,status,created_at,verified_at
                 FROM donation_reports WHERE user_id=? ORDER BY id DESC LIMIT 100''',(u['id'],))

    @app.get('/api/admin/donation-reports')
    def admin_donation_reports(req:Request):
        u=require_user(req)
        if u['role']!='admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        return read('''SELECT d.id,d.amount_satang,d.note,d.status,d.created_at,
                 d.verified_at,u.username AS member
                 FROM donation_reports d JOIN users u ON u.id=d.user_id
                 ORDER BY CASE d.status WHEN 'pending' THEN 0 ELSE 1 END,d.id DESC LIMIT 300''')

    @app.patch('/api/admin/donation-reports/{report_id}')
    def update_donation_report(report_id:int,body:DonationStatusIn,req:Request,
                               x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if u['role']!='admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        if body.status not in ('confirmed','rejected'):
            raise HTTPException(400,'สถานะไม่ถูกต้อง')
        with connect() as c:
            result=c.execute('''UPDATE donation_reports SET status=?, verified_at=?,verified_by=?
                WHERE id=? AND status='pending' ''',(body.status,now(),u['id'],report_id))
            if result.rowcount<1:
                raise HTTPException(409,'รายการไม่มีอยู่หรือถูกตรวจสอบแล้ว')
        return {'status':body.status,'message':'ยืนยันสถานะโดยผู้ดูแลแล้ว หลังตรวจรายการธนาคารจริง'}

    @app.get('/api/admin/users')
    def admin_list_users(req: Request):
        require_user(req)
        return read('''SELECT u.id, u.username, u.email, u.role, u.created_at,
                   (SELECT COUNT(*) FROM products p WHERE p.user_id=u.id) AS products_count,
                   (SELECT COUNT(*) FROM drafts d WHERE d.user_id=u.id) AS drafts_count,
                   (SELECT COUNT(*) FROM publishing_queue q WHERE q.user_id=u.id) AS queue_count
            FROM users u ORDER BY u.id DESC LIMIT 100''')

    @app.post('/api/admin/users')
    def admin_create_user(body: UserCreateIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        email = body.email.strip().lower()
        username = body.username.strip()
        role = 'admin' if body.role == 'admin' else 'member'
        if not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username):
            raise HTTPException(400, 'ชื่อผู้ใช้ต้องมีเฉพาะอังกฤษ ตัวเลข หรือ _')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(400, 'อีเมลไม่ถูกต้อง')
        if len(body.password) < 4:
            raise HTTPException(400, 'รหัสผ่านสั้นเกินไป')
        try:
            with connect() as c:
                cur = c.execute('INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                                (username, email, PH.hash(body.password), role, now()))
                return {'id': cur.lastrowid, 'username': username, 'email': email, 'role': role}
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'อีเมลหรือชื่อผู้ใช้มีอยู่แล้ว')

    @app.patch('/api/admin/users/{user_id}/role')
    def admin_update_user_role(user_id: int, body: UserRoleIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        if body.role not in ('admin', 'member'):
            raise HTTPException(400, 'บทบาทไม่ถูกต้อง')
        with connect() as c:
            c.execute('UPDATE users SET role=? WHERE id=?', (body.role, user_id))
        return {'ok': True, 'role': body.role}

    @app.delete('/api/admin/users/{user_id}')
    def admin_delete_user(user_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        if user_id == u['id']:
            raise HTTPException(400, 'ไม่สามารถลบบัญชีตนเองได้')
        with connect() as c:
            c.execute('DELETE FROM users WHERE id=?', (user_id,))
        return {'ok': True}

    @app.get('/api/my/radar/trending')
    def radar_trending(req:Request):
        require_user(req)
        return trending_topics()

    @app.get('/api/my/radar/search')
    def search_product_radar(req:Request, q:str='', extra_comm_only:bool=False):
        u=require_user(req)
        saved=read('SELECT encrypted FROM credentials WHERE user_id=? AND provider=?',
                   (u['id'],'brave'),True)
        token=None
        if saved:
            try:
                token=cipher.decrypt(saved['encrypted'].encode()).decode()
            except InvalidToken:
                raise HTTPException(503,'ถอดรหัส Brave API key ไม่ได้ กรุณาตรวจการตั้งค่าคีย์')
        try:
            return discover(q,token=token,extra_comm_only=extra_comm_only)
        except ValueError as e:
            raise HTTPException(400,str(e))
        except RuntimeError as e:
            raise HTTPException(429,str(e))

    def is_shopee_url(raw):
        try:
            parts=urlsplit(raw)
            return (parts.scheme == 'https' and (parts.hostname or '').lower() in
                    ('shopee.co.th','www.shopee.co.th','s.shopee.co.th') and
                    not parts.username and not parts.password and parts.port in (None,443))
        except ValueError:
            return False

    @app.post('/api/my/shopee/preview')
    def shopee_copied_preview(body: ShopeeCopiedIn, req:Request,
                               x_csrf_token:str|None=Header(default=None)):
        mutation(req,x_csrf_token)
        try:
            return pasted_preview(body.content)
        except ValueError as e:
            raise HTTPException(400,str(e))

    @app.post('/api/my/shopee/report-preview')
    async def shopee_report_upload(req:Request, file:UploadFile=File(...),
                                   x_csrf_token:str|None=Header(default=None)):
        mutation(req,x_csrf_token)
        binary=await file.read(2*1024*1024+1)
        try:
            return report_preview(binary,file.filename or '')
        except ValueError as e:
            raise HTTPException(400,str(e))

    @app.get('/api/my/products')
    def my_products(req:Request):
        u=require_user(req)
        return read('SELECT id,title,url,platform,created_at,extra_comm_checked,extra_comm_rate,extra_comm_checked_at FROM products WHERE user_id=? ORDER BY id DESC LIMIT 200',(u['id'],))

    @app.post('/api/my/products')
    def add_product(body:ProductIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if body.platform not in ('tiktok','shopee','other'):
            raise HTTPException(400,'แพลตฟอร์มไม่ถูกต้อง')
        if body.url and not (body.url.startswith('https://') and ' ' not in body.url):
            raise HTTPException(400,'ลิงก์ต้องเริ่มด้วย https://')
        if body.extra_comm_rate is not None and not body.extra_comm_checked:
            raise HTTPException(400,'ต้องยืนยัน EXTRA COMM ก่อนระบุค่าคอม')
        if body.extra_comm_checked and (body.platform != 'shopee' or not body.url or not is_shopee_url(body.url)):
            raise HTTPException(400,'การยืนยัน EXTRA COMM ต้องเป็นลิงก์ Shopee อย่างเป็นทางการที่ตรวจจากบัญชี Affiliate แล้ว')
        with connect() as c:
            cur=c.execute('''INSERT INTO products(user_id,title,url,platform,created_at,extra_comm_checked,extra_comm_rate,extra_comm_checked_at)
                VALUES(?,?,?,?,?,?,?,?)''',
                          (u['id'],body.title.strip(),body.url.strip(),body.platform,now(),
                           int(body.extra_comm_checked),float(body.extra_comm_rate) if body.extra_comm_rate is not None else None,now() if body.extra_comm_checked else None))
        return {'id':cur.lastrowid}

    @app.patch('/api/my/products/{product_id}/extra-comm')
    def update_extra_comm(product_id:int, body:ExtraCommIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if body.rate is not None and not body.checked:
            raise HTTPException(400,'ต้องยืนยัน Extra Comm ก่อนระบุเรท')
        p=read('SELECT id,url,platform FROM products WHERE id=? AND user_id=?',(product_id,u['id']),True)
        if not p:
            raise HTTPException(404,'ไม่พบสินค้าของบัญชีนี้')
        if body.checked and (p['platform']!='shopee' or not is_shopee_url(p['url'])):
            raise HTTPException(400,'ต้องมีลิงก์ Shopee ทางการก่อนยืนยัน Extra Comm')
        with connect() as c:
            c.execute('''UPDATE products SET extra_comm_checked=?,extra_comm_rate=?,extra_comm_checked_at=?
                         WHERE id=? AND user_id=?''',
                      (int(body.checked),float(body.rate) if body.rate is not None else None,
                       now() if body.checked else None,product_id,u['id']))
        return {'id':product_id,'extra_comm_checked':body.checked,'rate':str(body.rate) if body.rate is not None else None,
                'note':'ข้อมูลนี้สมาชิกตรวจและยืนยันเอง ไม่ได้ตรวจโดย Shopee API'}

    # Private member workflow: all ownership checks happen server-side, not in JS.
    @app.get('/api/my/drafts')
    def my_drafts(req: Request):
        u=require_user(req)
        return read('''SELECT d.id,d.product_id,d.style,d.script,d.prompt,d.created_at,p.title,p.platform
                    FROM drafts d JOIN products p ON p.id=d.product_id
                    WHERE d.user_id=? ORDER BY d.id DESC LIMIT 100''',(u['id'],))

    @app.post('/api/my/drafts')
    def create_draft(body: DraftIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if body.style not in ('pov','demo','problem_solution'):
            raise HTTPException(400,'รูปแบบคลิปไม่ถูกต้อง')
        p=read('SELECT * FROM products WHERE id=? AND user_id=?',(body.product_id,u['id']),True)
        if not p:
            raise HTTPException(404,'ไม่พบสินค้าในบัญชีของคุณ')
        label=p['title'].strip()
        hook={'pov':'ของชิ้นนี้ใช้ทำอะไรได้บ้าง?','demo':'มาดูวิธีใช้สินค้าชิ้นนี้กัน','problem_solution':'ใครกำลังเจอปัญหานี้บ้าง?'}[body.style]
        script=(f'0–3 วินาที: {hook}\n3–7 วินาที: สาธิต {label} โดยแสดงการใช้งานจริงตามคุณสมบัติที่ตรวจสอบได้\n7–10 วินาที: ดูข้อมูลเพิ่มเติมจากลิงก์สินค้าก่อนตัดสินใจ')
        prompt=(f'Create a natural 9:16 Thai POV hands-on product video, about 10 seconds, focusing on {label}. '
                'Show authentic hands demonstrating the actual product; no face or misleading results. '
                'Use submitted product images as reference only, never use listing screenshots as an overlay or first frame. '
                'Thai narration, no unsupported claims. Check product details before generation.')
        with connect() as c:
            # Serialize creation so two simultaneous requests cannot receive the same use number.
            c.execute('BEGIN IMMEDIATE')
            number=c.execute('''SELECT COUNT(*) FROM product_use_events
                                   WHERE user_id=? AND product_id=?''',(u['id'],p['id'])).fetchone()[0] + 1
            created=now()
            cur=c.execute('INSERT INTO drafts(user_id,product_id,style,script,prompt,created_at) VALUES(?,?,?,?,?,?)',
                          (u['id'],p['id'],body.style,script,prompt,created))
            draft_id=cur.lastrowid
            c.execute('''INSERT INTO product_use_events(user_id,product_id,draft_id,use_number,created_at)
                         VALUES(?,?,?,?,?)''',(u['id'],p['id'],draft_id,number,created))
        return {'id':draft_id,'script':script,'prompt':prompt,'status':'draft_only',
                'use_number':number,'used_at':created,
                'notice':'บันทึกเวลาเริ่มทำคอนเทนต์แล้ว เป็นสคริปต์แม่แบบ ยังไม่ได้สร้างไฟล์วิดีโอ MP4 หรือโพสต์'}

    @app.get('/api/my/product-tracking')
    def product_tracking(req:Request):
        u=require_user(req)
        # Metrics are provided by the member, never asserted to be platform-verified sales.
        rows=read('''SELECT p.id,p.title,p.platform,p.url,p.extra_comm_checked,
                         COUNT(ev.id) AS use_count,
                         MIN(ev.created_at) AS first_used_at,
                         MAX(ev.created_at) AS last_used_at,
                         COALESCE(SUM(perf.views),0) AS views,
                         COALESCE(SUM(perf.clicks),0) AS clicks,
                         COALESCE(SUM(perf.orders),0) AS orders,
                         COALESCE(SUM(perf.sales_satang),0) AS sales_satang,
                         COALESCE(SUM(perf.commission_satang),0) AS commission_satang,
                         COUNT(perf.draft_id) AS reported_count
                    FROM products p
                    LEFT JOIN product_use_events ev ON ev.product_id=p.id AND ev.user_id=p.user_id
                    LEFT JOIN draft_performance perf ON perf.draft_id=ev.draft_id AND perf.user_id=p.user_id
                    WHERE p.user_id=? GROUP BY p.id ORDER BY last_used_at DESC,p.id DESC''',(u['id'],))
        for r in rows:
            r['performance_label'] = ('ยังไม่บันทึกผล' if not r['reported_count'] else
              'มีออเดอร์ ≥ 5 (ตามข้อมูลที่กรอก)' if r['orders']>=5 else
              'มีออเดอร์ (ตามข้อมูลที่กรอก)' if r['orders']>0 else 'ยังไม่มีออเดอร์ที่รายงาน')
        return {'products':rows,'basis':'สถิติส่วนตัวที่สมาชิกกรอกเอง ไม่ใช่ยอดขายที่ยืนยันจาก TikTok/Shopee'}

    @app.get('/api/my/products/{product_id}/history')
    def product_history(product_id:int,req:Request):
        u=require_user(req)
        p=read('SELECT id,title,platform FROM products WHERE id=? AND user_id=?',(product_id,u['id']),True)
        if not p: raise HTTPException(404,'ไม่พบสินค้าของบัญชีนี้')
        events=read('''SELECT ev.id,ev.draft_id,ev.use_number,ev.created_at,d.style,
                             perf.views,perf.clicks,perf.orders,perf.sales_satang,
                             perf.commission_satang,perf.recorded_at,perf.note
                      FROM product_use_events ev JOIN drafts d ON d.id=ev.draft_id
                      LEFT JOIN draft_performance perf ON perf.draft_id=ev.draft_id
                      WHERE ev.user_id=? AND ev.product_id=? ORDER BY ev.id DESC LIMIT 200''',(u['id'],product_id))
        return {'product':p,'events':events,'notice':'เวลาเป็นเวลาสร้างสคริปต์/หยิบสินค้ามาทำ ไม่ใช่เวลาเผยแพร่คลิป'}

    @app.put('/api/my/drafts/{draft_id}/performance')
    def save_draft_performance(draft_id:int,body:PerformanceIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        owned=read('SELECT id FROM drafts WHERE id=? AND user_id=?',(draft_id,u['id']),True)
        if not owned: raise HTTPException(404,'ไม่พบสคริปต์ในบัญชีนี้')
        if body.clicks > body.views and body.views > 0:
            raise HTTPException(400,'ยอดคลิกมากกว่ายอดวิว กรุณาตรวจสอบข้อมูลก่อนบันทึก')
        with connect() as c:
            c.execute('''INSERT INTO draft_performance
                        (draft_id,user_id,views,clicks,orders,sales_satang,commission_satang,note,recorded_at)
                        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(draft_id) DO UPDATE SET
                        views=excluded.views,clicks=excluded.clicks,orders=excluded.orders,
                        sales_satang=excluded.sales_satang,commission_satang=excluded.commission_satang,
                        note=excluded.note,recorded_at=excluded.recorded_at''',
                      (draft_id,u['id'],body.views,body.clicks,body.orders,
                       int(body.sales_baht*100),int(body.commission_baht*100),body.note.strip(),now()))
        return {'saved':True,'draft_id':draft_id,'source':'member_reported',
                'notice':'บันทึกผลที่กรอกด้วยตัวเอง ไม่ใช่ยอดขายที่ตรวจสอบผ่าน API'}

    @app.get('/api/my/queue')
    def my_queue(req: Request):
        u=require_user(req)
        return read('''SELECT q.id,q.platform,q.video_url,q.status,q.created_at,d.script,p.title
                    FROM publishing_queue q JOIN drafts d ON q.draft_id=d.id
                    JOIN products p ON d.product_id=p.id
                    WHERE q.user_id=? ORDER BY q.id DESC LIMIT 100''',(u['id'],))

    @app.post('/api/my/queue')
    def add_queue(body:QueueIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if body.platform not in ('tiktok','shopee'):
            raise HTTPException(400,'เลือก TikTok หรือ Shopee')
        draft=read('SELECT id FROM drafts WHERE id=? AND user_id=?',(body.draft_id,u['id']),True)
        if not draft:
            raise HTTPException(404,'ไม่พบสคริปต์ของคุณ')
        url=body.video_url.strip()
        if body.video_job_id is not None:
            job=read("SELECT id FROM video_jobs WHERE id=? AND user_id=? AND draft_id=? AND status='ready'",
                     (body.video_job_id,u['id'],body.draft_id),True)
            if not job: raise HTTPException(400,'ไม่พบคลิป AI ที่สร้างเสร็จและตรงกับบทนี้')
            url=f'/api/my/video-jobs/{body.video_job_id}/file'
        if url and body.video_job_id is None:
            parsed=urlsplit(url)
            if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or any(ch in url for ch in ('\r','\n','\x00',' ')):
                raise HTTPException(400,'ลิงก์วิดีโอต้องเป็น HTTPS ที่ถูกต้อง')
        with connect() as c:
            cur=c.execute('INSERT INTO publishing_queue(user_id,draft_id,platform,video_url,status,created_at) VALUES(?,?,?,?,?,?)',
                          (u['id'],body.draft_id,body.platform,url,'needs_review' if not url else 'ready_manual',now()))
        return {'id':cur.lastrowid,'status':'needs_review' if not url else 'ready_manual',
                'notice':'เป็นคิวเตรียมโพสต์ ยังไม่ส่งไป TikTok/Shopee และไม่ปักตะกร้า'}

    @app.patch('/api/my/queue/{item_id}')
    def update_queue(item_id:int,body:QueueStatusIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        if body.status not in ('completed_manual','cancelled'):
            raise HTTPException(400,'สถานะไม่ถูกต้อง')
        with connect() as c:
            r=c.execute('UPDATE publishing_queue SET status=? WHERE id=? AND user_id=? AND status IN (\'needs_review\',\'ready_manual\')',
                        (body.status,item_id,u['id']))
            if not r.rowcount:
                raise HTTPException(404,'ไม่พบงานหรืออัปเดตงานนี้ไม่ได้')
        return {'ok':True,'status':body.status,'notice':'สถานะนี้เป็นการบันทึกโดยผู้ใช้ ไม่ได้ตรวจสอบการโพสต์จริง'}

    # V6 is a single-tenant application. Only allow admins into its entire route tree.
    # This middleware runs before Starlette dispatches to the mounted V6 app.
    from fastapi.responses import JSONResponse, RedirectResponse
    @app.middleware('http')
    async def studio_membership_gate(request: Request, call_next):
        path=request.scope.get('path', request.url.path)
        if path == '/studio' or path.startswith('/studio/'):
            try:
                member=require_user(request)
            except HTTPException:
                if path in ('/studio','/studio/') and request.method == 'GET':
                    return RedirectResponse('/', status_code=303)
                return JSONResponse({'detail':'กรุณาเข้าสู่ระบบก่อน'},status_code=401)
            if member['role'] != 'admin':
                return JSONResponse({'detail':'Studio V6 เป็นพื้นที่ผู้ดูแลสำหรับทดลองเท่านั้น'},status_code=403)
            if request.method.upper() not in ('GET','HEAD','OPTIONS'):
                csrf=request.headers.get('x-csrf-token','')
                if not secrets.compare_digest(csrf,member['csrf']):
                    return JSONResponse({'detail':'CSRF token ไม่ถูกต้อง'},status_code=403)
        return await call_next(request)

    # Mount the existing V6 features without mixing its single-tenant database
    # into community.db. Never publish this combined prototype to the internet.
    if PUBLIC_MODE:
        return app
    import sys, importlib.util
    studio_path=(ROOT/'studio_v6').resolve()
    if str(studio_path) not in sys.path: sys.path.insert(0, str(studio_path))
    spec=importlib.util.spec_from_file_location('unified_v6_app', studio_path/'app.py')
    studio_module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(studio_module)
    studio=studio_module.app
    app.mount('/studio', studio, name='studio')

    # Mounted apps do not consistently receive lifespan events across ASGI versions.
    # Start/stop V6's opt-in background worker routines when V7 starts/stops.
    @app.on_event('startup')
    async def start_studio():
        await studio.router.startup()
    @app.on_event('shutdown')
    async def stop_studio():
        await studio.router.shutdown()

    return app


app=create_app()
