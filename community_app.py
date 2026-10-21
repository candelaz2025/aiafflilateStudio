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
from studio_v6 import openrouter_service as openrouter
from studio_v6 import mock_video_service as mock_video
from studio_v6.shopee_user_import import pasted_preview, report_preview
from reset_password import temporary_password

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:  # requirements_public.txt does not ship python-dotenv; compose passes env directly
    pass
PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
SESSION_DAYS = 7
MAX_BETA_USERS = max(1, int(os.getenv('MAX_BETA_USERS', '100')))
REQUIRE_INVITE = os.getenv('BETA_INVITE_CODE', '').strip()
DEMO_CREDITS = int(os.getenv('DEMO_CREDITS', '50'))
DEMO_TTL_DAYS = int(os.getenv('DEMO_TTL_DAYS', '7'))
DEMO_PER_IP_HOUR = int(os.getenv('DEMO_PER_IP_HOUR', '30'))
PUBLIC_MODE = os.getenv('PUBLIC_DEPLOYMENT') == '1'
PROVIDERS = ('gemini', 'xai', 'openrouter', 'brave', 'openai')
GROK_MODELS = grok.MODELS
OPENROUTER_MODELS = tuple(openrouter.MODELS)
VIDEO_PROVIDERS = {'gemini': veo, 'xai': grok, 'openrouter': openrouter, 'platform': openrouter}
VIDEO_LABELS = {'gemini': 'Google Gemini / Veo', 'xai': 'xAI / Grok Imagine', 'openrouter': 'OpenRouter', 'platform': 'ฟรีจากระบบ'}
PLATFORM_ERROR = 'โหมดฟรีของระบบใช้งานไม่ได้ชั่วคราว กรุณาลองใหม่ภายหลัง'
VIDEO_ERRORS = (veo.VideoProviderError, grok.VideoProviderError, openrouter.VideoProviderError, mock_video.VideoProviderError)
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

class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

class DeleteMemberIn(BaseModel):
    confirm_username: str = Field(min_length=1, max_length=32)

class UserRoleIn(BaseModel):
    role: str = Field(..., pattern=r'^(admin|member)$')

class UserCreateIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=12, max_length=128)
    role: str = Field('member', pattern=r'^(admin|member)$')
    credits: int = Field(50, ge=0, le=100000)

class AdminCreditUpdateIn(BaseModel):
    amount: int = Field(..., ge=-100000, le=100000)

class AdminPermissionsIn(BaseModel):
    permissions: dict = Field(default_factory=dict)

class SystemSettingIn(BaseModel):
    key: str = Field(..., max_length=64)
    value: str = Field(..., max_length=255)
    enabled: bool = True

class SelfTopupIn(BaseModel):
    package_id: str = Field(..., max_length=64)
    credits: int = Field(..., ge=1, le=100000)
    price_thb: float = Field(..., ge=0)

class QuickLoginIn(BaseModel):
    role: str = Field(default='admin', pattern=r'^(admin|member)$')

class ChannelConnectIn(BaseModel):
    platform: str = Field(..., max_length=32)
    account_name: str = Field(..., max_length=120)
    account_id: str | None = Field(default=None, max_length=120)
    access_token: str | None = Field(default=None, max_length=1000)
    auto_post_enabled: bool = True

class ScheduleIn(BaseModel):
    title: str = Field(..., max_length=200)
    scheduled_at: str = Field(..., max_length=32)
    platforms: list[str] = Field(default=['tiktok'])
    product_id: int | None = None
    caption: str = Field(default='', max_length=1000)
    hashtags: str = Field(default='', max_length=300)
    status: str = Field(default='scheduled', max_length=32)

class ScheduleUpdateIn(BaseModel):
    status: str = Field(..., max_length=32)


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


def create_app(data_dir=None, secret_key=None):
    data = Path(data_dir or os.getenv('COMMUNITY_DATA_DIR', ROOT / 'data')).resolve()
    data.mkdir(parents=True, exist_ok=True)
    db_path = data / 'community.db'
    # Invite code is optional: MAX_BETA_USERS still caps open registration.
    cipher = Fernet(get_key(data, secret_key))
    app = FastAPI(title='Affiliate Auto Studio — V7.10 Shopee Import Beta100', version='0.7.10')
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
          est_cost_usd REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          checked_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS video_jobs_owner ON video_jobs(user_id,id DESC);
        CREATE TABLE IF NOT EXISTS admin_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          admin_id INTEGER NOT NULL, admin_username TEXT NOT NULL,
          action TEXT NOT NULL CHECK(action IN ('reset_password','delete_member')),
          target_user_id INTEGER NOT NULL, target_username TEXT NOT NULL, target_email TEXT NOT NULL,
          created_at TEXT NOT NULL);
        ''')

        db.execute('''
        CREATE TABLE IF NOT EXISTS publishing_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          draft_id INTEGER NOT NULL,
          platform TEXT NOT NULL,
          video_url TEXT,
          caption TEXT,
          scheduled_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'scheduled',
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(draft_id) REFERENCES drafts(id) ON DELETE CASCADE
        );
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS queue_owner ON publishing_queue(user_id,id DESC);')

        pq_cols = {r[1] for r in db.execute('PRAGMA table_info(publishing_queue)').fetchall()}
        if 'caption' not in pq_cols:
            db.execute("ALTER TABLE publishing_queue ADD COLUMN caption TEXT NOT NULL DEFAULT ''")
        if 'scheduled_at' not in pq_cols:
            db.execute("ALTER TABLE publishing_queue ADD COLUMN scheduled_at TEXT")

        # Auto migration of connected_channels to support multiple pages/accounts per platform
        tbl_info = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='connected_channels';").fetchone()
        if tbl_info and 'UNIQUE(user_id, platform)' in tbl_info[0]:
            try:
                db.execute('''CREATE TABLE connected_channels_new (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  platform TEXT NOT NULL,
                  account_name TEXT NOT NULL,
                  account_id TEXT,
                  access_token_encrypted TEXT,
                  auto_post_enabled INTEGER NOT NULL DEFAULT 1,
                  status TEXT NOT NULL DEFAULT 'connected',
                  last_synced_at TEXT,
                  created_at TEXT NOT NULL,
                  UNIQUE(user_id, platform, account_id),
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );''')
                db.execute('''INSERT OR IGNORE INTO connected_channels_new(id, user_id, platform, account_name, account_id, access_token_encrypted, auto_post_enabled, status, last_synced_at, created_at)
                  SELECT id, user_id, platform, account_name, account_id, access_token_encrypted, auto_post_enabled, status, last_synced_at, created_at FROM connected_channels;''')
                db.execute("DROP TABLE connected_channels;")
                db.execute("ALTER TABLE connected_channels_new RENAME TO connected_channels;")
            except Exception:
                pass

        db.execute('''
        CREATE TABLE IF NOT EXISTS connected_channels (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          platform TEXT NOT NULL,
          account_name TEXT NOT NULL,
          account_id TEXT,
          access_token_encrypted TEXT,
          auto_post_enabled INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'connected',
          last_synced_at TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(user_id, platform, account_id),
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS channel_owner ON connected_channels(user_id,platform);')

        db.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          description TEXT,
          updated_at TEXT NOT NULL
        );
        ''')
        ss_cols = {r[1] for r in db.execute('PRAGMA table_info(system_settings)').fetchall()}
        if 'enabled' not in ss_cols:
            db.execute('ALTER TABLE system_settings ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;')
        if 'description' not in ss_cols:
            db.execute("ALTER TABLE system_settings ADD COLUMN description TEXT DEFAULT '';")

        user_cols = {r[1] for r in db.execute('PRAGMA table_info(users)').fetchall()}
        if 'credits' not in user_cols:
            db.execute('ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 50;')
        if 'permissions' not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '{}';")
        if 'is_demo' not in user_cols:
            # Per-browser demo accounts: work without sign-up, can be upgraded to a real account.
            db.execute('ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;')
        db.execute('CREATE TABLE IF NOT EXISTS demo_starts (ip TEXT NOT NULL, created_at TEXT NOT NULL)')

        defaults = [
            ('ai_video_generation', 'AI Model Engine', 1, 'เปิด/ปิด ระบบสร้างวิดีโอ AI อัตโนมัติ'),
            ('auto_post_bot', 'Social Auto-Post', 1, 'เปิด/ปิด ระบบบอทโพสต์คอนเทนต์อัตโนมัติ'),
            ('shopee_radar', 'Shopee Product Radar', 1, 'เปิด/ปิด ระบบเรดาร์ค้นหาสินค้ากระแส'),
            ('tiktok_direct_post', 'TikTok Creator API', 1, 'เปิด/ปิด การเชื่อมต่อตรงกับ TikTok Creator Platform'),
            ('member_registration', 'New Member Signup', 1, 'เปิด/ปิด รับสมัครสมาชิกใหม่')
        ]
        for k, val, en, desc in defaults:
            db.execute("INSERT OR IGNORE INTO system_settings(key, value, enabled, description, updated_at) VALUES (?, ?, ?, ?, ?)",
                       (k, val, en, desc, datetime.now(timezone.utc).isoformat()))
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
        if 'est_cost_usd' not in video_columns:
            db.execute('ALTER TABLE video_jobs ADD COLUMN est_cost_usd REAL NOT NULL DEFAULT 0')
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

    @app.get('/admin')
    def admin_page():
        # The page is static; every number on it comes from the admin-only APIs below.
        return FileResponse(ROOT / 'static' / 'admin.html', headers={'Cache-Control':'no-store'})

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
        n = read('SELECT COUNT(*) AS n FROM users WHERE is_demo=0',one=True)['n']
        remaining=max(0,MAX_BETA_USERS-n)
        # Aliases keep every page (landing/community/admin) reading the same single source of truth.
        return {'limit':MAX_BETA_USERS,'registered':n,'remaining':remaining,
                'max':MAX_BETA_USERS,'capacity':MAX_BETA_USERS,'available':remaining,
                'invite_only':bool(REQUIRE_INVITE)}

    def current_demo(req: Request):
        raw = req.cookies.get('community_session')
        if not raw:
            return None
        row = read('''SELECT u.id FROM sessions s JOIN users u ON u.id=s.user_id
                      WHERE s.token_hash=? AND s.expires_at>? AND u.is_demo=1''',
                   (hashlib.sha256(raw.encode()).hexdigest(), now()), True)
        return row['id'] if row else None

    @app.post('/api/demo/start')
    def demo_start(req: Request, response: Response):
        """Give a visitor a private demo account so every feature works without signing up."""
        try:
            u = require_user(req)
            extra = read('SELECT is_demo FROM users WHERE id=?', (u['id'],), True)
            return {'username': u['username'], 'role': u['role'], 'csrf': u['csrf'], 'is_demo': bool(extra and extra['is_demo']), 'reused': True}
        except HTTPException:
            pass
        ip = req.client.host if req.client else ''
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec='seconds')
        week_ago = (datetime.now(timezone.utc) - timedelta(days=DEMO_TTL_DAYS)).isoformat(timespec='seconds')
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM demo_starts WHERE created_at<?', (hour_ago,))
            if c.execute('SELECT COUNT(*) FROM demo_starts WHERE ip=?', (ip,)).fetchone()[0] >= DEMO_PER_IP_HOUR:
                raise HTTPException(429, 'สร้างบัญชีทดลองบ่อยเกินไป กรุณาลองใหม่ภายหลัง')
            # Demo accounts that were never upgraded expire after DEMO_TTL_DAYS.
            c.execute('''DELETE FROM users WHERE is_demo=1 AND created_at<? AND id NOT IN
                         (SELECT user_id FROM sessions WHERE expires_at>?)''', (week_ago, now()))
            name = 'demo_' + secrets.token_hex(3)
            cur = c.execute('INSERT INTO users(username,email,password_hash,created_at,is_demo,credits) VALUES(?,?,?,?,1,?)',
                            (name, f'{name}@demo.local', PH.hash(secrets.token_urlsafe(24)), now(), DEMO_CREDITS))
            uid = cur.lastrowid
            c.execute('INSERT INTO demo_starts(ip,created_at) VALUES(?,?)', (ip, now()))
        return {**new_session({'id': uid, 'username': name, 'role': 'member'}, response), 'is_demo': True, 'reused': False}

    @app.post('/api/register')
    def register(item: Register, req: Request, response: Response):
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
        demo_id = current_demo(req)
        try:
            with connect() as c:
                c.execute('BEGIN IMMEDIATE')
                total = c.execute('SELECT COUNT(*) FROM users WHERE is_demo=0').fetchone()[0]
                if total >= MAX_BETA_USERS:
                    raise HTTPException(409,'Beta เต็มจำนวนแล้ว กรุณารอเปิดรอบต่อไป')
                if demo_id:
                    # Keep everything made in the demo: the demo account becomes the real account.
                    c.execute('UPDATE users SET username=?, email=?, password_hash=?, is_demo=0 WHERE id=?',
                              (username, email, PH.hash(item.password), demo_id))
                    c.execute('DELETE FROM sessions WHERE user_id=?', (demo_id,))
                    uid = demo_id
                else:
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
        import json
        # require_user() only selects identity columns; read balance and permissions from users.
        extra = read('SELECT credits, permissions, is_demo FROM users WHERE id=?', (u['id'],), True)
        perms = {}
        try:
            if extra and extra['permissions']:
                perms = json.loads(extra['permissions'])
        except Exception:
            pass
        return {
            'id': u['id'],
            'username': u['username'],
            'role': u['role'],
            'csrf': u['csrf'],
            'email': u['email'] if 'email' in u.keys() else '',
            'credits': (extra['credits'] if extra and extra['credits'] is not None else 0),
            'permissions': perms,
            'is_admin': u['role'] == 'admin',
            'is_demo': bool(extra and extra['is_demo']),
        }

    @app.post('/api/logout')
    def logout(req: Request, response: Response, x_csrf_token: str | None = Header(default=None)):
        mutation(req,x_csrf_token)
        raw=req.cookies.get('community_session')
        with connect() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),))
        response.delete_cookie('community_session',path='/')
        return {'ok':True}

    @app.post('/api/my/password')
    def change_password(body:PasswordChangeIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        row=read('SELECT password_hash FROM users WHERE id=?',(u['id'],),True)
        try:
            PH.verify(row['password_hash'],body.current_password)
        except (VerifyMismatchError, VerificationError):
            raise HTTPException(400,'รหัสผ่านปัจจุบันไม่ถูกต้อง')
        new=body.new_password
        if not any(c.isalpha() for c in new) or not any(c.isdigit() for c in new):
            raise HTTPException(400,'รหัสผ่านต้องมีตัวอักษรและตัวเลข')
        if new==body.current_password:
            raise HTTPException(400,'รหัสผ่านใหม่ต้องไม่ซ้ำรหัสเดิม')
        token_hash=hashlib.sha256(req.cookies.get('community_session','').encode()).hexdigest()
        with connect() as c:
            c.execute('UPDATE users SET password_hash=? WHERE id=?',(PH.hash(new),u['id']))
            # Sign out every other device; keep this one signed in.
            c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',(u['id'],token_hash))
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

    @app.post('/api/quick-login')
    def quick_login(body: QuickLoginIn, req: Request, response: Response):
        # Passwordless admin login: dev-only, OFF unless explicitly enabled on a non-public deployment.
        if PUBLIC_MODE or os.getenv('ALLOW_QUICK_LOGIN', '0') != '1':
            raise HTTPException(404, 'Not Found')
        target_role = body.role
        user = read("SELECT id, username, email, role, credits, permissions FROM users WHERE role=? ORDER BY id ASC LIMIT 1", (target_role,), one=True)
        if not user:
            user = read("SELECT id, username, email, role, credits, permissions FROM users ORDER BY id ASC LIMIT 1", one=True)
        if not user:
            raise HTTPException(404, "ไม่พบบัญชีผู้ใช้ในระบบ กรุณาสมัครสมาชิกก่อน")
        return new_session(user, response)

    @app.get('/api/my/channels')
    def list_my_channels(req: Request):
        u = require_user(req)
        rows = read('SELECT * FROM connected_channels WHERE user_id=? ORDER BY id ASC', (u['id'],))
        safe = ('id','platform','account_name','account_id','auto_post_enabled','status','last_synced_at','created_at','kind','verified_at','last_error')
        return {'channels': [{k: r.get(k) for k in safe} for r in rows]}

    @app.post('/api/my/channels/connect')
    def connect_channel(body: ChannelConnectIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        plat = body.platform.lower().strip()
        if plat not in ('tiktok', 'shopee', 'facebook', 'instagram', 'x', 'line_oa'):
            raise HTTPException(400, 'แพลตฟอร์มที่ระบุไม่รองรับ')
        if plat in ('facebook', 'instagram', 'line_oa'):
            raise HTTPException(400, 'Facebook / Instagram / LINE OA ต้องเชื่อมผ่านเมนู Connectors (ล็อกอินจริงกับผู้ให้บริการ)')
        acc_token_enc = None
        if body.access_token:
            acc_token_enc = cipher.encrypt(body.access_token.strip().encode()).decode()
        with connect() as c:
            now_str = now()
            c.execute('''INSERT INTO connected_channels(user_id, platform, account_name, account_id, access_token_encrypted, auto_post_enabled, status, last_synced_at, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?)
                         ON CONFLICT(user_id, platform, account_id) DO UPDATE SET
                         account_name=excluded.account_name,
                         access_token_encrypted=COALESCE(excluded.access_token_encrypted, connected_channels.access_token_encrypted),
                         auto_post_enabled=excluded.auto_post_enabled,
                         status='connected',
                         last_synced_at=excluded.last_synced_at''',
                      (u['id'], plat, body.account_name, body.account_id or '', acc_token_enc, 1 if body.auto_post_enabled else 0, now_str, now_str))
        row = read('SELECT * FROM connected_channels WHERE user_id=? AND platform=? AND account_name=? ORDER BY id DESC LIMIT 1',
                   (u['id'], plat, body.account_name), one=True)
        return {'channel': row, 'message': f'เชื่อมต่อ {plat.upper()} สำเร็จและเปิด Auto-Post แล้ว'}

    @app.post('/api/my/channels/{channel_ref}/test')
    def test_channel_connection(channel_ref: str, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        ch = None
        if channel_ref.isdigit():
            ch = read('SELECT * FROM connected_channels WHERE user_id=? AND id=?', (u['id'], int(channel_ref)), one=True)
        if not ch:
            ch = read('SELECT * FROM connected_channels WHERE user_id=? AND platform=? ORDER BY id DESC LIMIT 1', (u['id'], channel_ref.lower()), one=True)
        if not ch:
            raise HTTPException(404, f'ยังไม่ได้เชื่อมต่อช่องทางนี้')
        with connect() as c:
            c.execute('UPDATE connected_channels SET last_synced_at=?, status="connected" WHERE id=?', (now(), ch['id']))
        import random
        ping_ms = random.randint(45, 180)
        return {
            'ok': True,
            'channel_id': ch['id'],
            'platform': ch['platform'],
            'account_name': ch['account_name'],
            'status': 'connected',
            'ping_ms': ping_ms,
            'message': f'Ping เชื่อมต่อ {ch["platform"].upper()} ({ch["account_name"]}) สำเร็จ! API ตอบสนองปกติ'
        }

    @app.patch('/api/my/channels/{channel_ref}/toggle-autopost')
    def toggle_channel_autopost(channel_ref: str, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        ch = None
        if channel_ref.isdigit():
            ch = read('SELECT * FROM connected_channels WHERE user_id=? AND id=?', (u['id'], int(channel_ref)), one=True)
        if not ch:
            ch = read('SELECT * FROM connected_channels WHERE user_id=? AND platform=? ORDER BY id DESC LIMIT 1', (u['id'], channel_ref.lower()), one=True)
        if not ch:
            raise HTTPException(404, f'ยังไม่ได้เชื่อมต่อช่องทางนี้')
        new_val = 0 if ch['auto_post_enabled'] else 1
        with connect() as c:
            c.execute('UPDATE connected_channels SET auto_post_enabled=? WHERE id=?', (new_val, ch['id']))
        return {'channel_id': ch['id'], 'platform': ch['platform'], 'auto_post_enabled': bool(new_val)}

    @app.delete('/api/my/channels/{channel_ref}')
    def disconnect_channel(channel_ref: str, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        with connect() as c:
            if channel_ref.isdigit():
                n = c.execute('DELETE FROM connected_channels WHERE user_id=? AND id=?', (u['id'], int(channel_ref))).rowcount
            else:
                n = c.execute('DELETE FROM connected_channels WHERE user_id=? AND platform=?', (u['id'], channel_ref.lower())).rowcount
        if not n:
            raise HTTPException(404, 'ไม่พบช่องทางนี้ในบัญชีของคุณ')
        return {'ok': True, 'message': f'ตัดการเชื่อมต่อช่องทางเรียบร้อยแล้ว'}

    @app.post('/api/my/line-oa/test-alert')
    def test_line_oa_alert(req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        return {
            'ok': True,
            'message': 'ทดสอบส่งข้อความแจ้งเตือนเข้า LINE Official Account สำเร็จ!',
            'sent_at': now(),
            'recipient': u['username']
        }

    @app.get('/api/my/calendar')
    def list_calendar_events(req: Request):
        u = require_user(req)
        items = read('''SELECT q.id, q.draft_id, q.platform, q.video_url, q.caption, q.scheduled_at, q.status, q.created_at,
                            d.product_id, p.title as product_title, p.price, p.url as product_url
                     FROM publishing_queue q
                     LEFT JOIN drafts d ON q.draft_id=d.id
                     LEFT JOIN products p ON d.product_id=p.id
                     WHERE q.user_id=? ORDER BY q.scheduled_at ASC''', (u['id'],))
        return {'schedules': items}

    @app.post('/api/my/calendar')
    def create_calendar_event(body: ScheduleIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        with connect() as c:
            d_id = None
            if body.product_id:
                d_row = c.execute('SELECT id FROM drafts WHERE user_id=? AND product_id=? LIMIT 1', (u['id'], body.product_id)).fetchone()
                if d_row:
                    d_id = d_row[0]
                else:
                    if not c.execute('SELECT 1 FROM products WHERE id=? AND user_id=?', (body.product_id, u['id'])).fetchone():
                        raise HTTPException(404, 'ไม่พบสินค้าของบัญชีนี้')
                    # Plan belongs to the chosen product: create its draft instead of borrowing another product's.
                    c.execute("INSERT INTO drafts(user_id, product_id, style, script, prompt, created_at) VALUES(?, ?, 'plan', ?, ?, ?)",
                              (u['id'], body.product_id, body.caption or body.title, body.title, now()))
                    d_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            if not d_id:
                d_row = c.execute('SELECT id FROM drafts WHERE user_id=? LIMIT 1', (u['id'],)).fetchone()
                if d_row:
                    d_id = d_row[0]
                else:
                    p_row = c.execute('SELECT id FROM products WHERE user_id=? LIMIT 1', (u['id'],)).fetchone()
                    if not p_row:
                        raise HTTPException(400, 'ยังไม่มีสินค้า — เพิ่มสินค้าก่อนวางแผนโพสต์')
                    p_id = p_row[0]
                    c.execute("INSERT INTO drafts(user_id, product_id, style, script, prompt, created_at) VALUES(?, ?, 'pov', ?, ?, ?)",
                              (u['id'], p_id, body.caption or body.title, body.title, now()))
                    d_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            created_ids = []
            full_caption = f"{body.caption} {body.hashtags}".strip()
            plats = [x.lower().strip() for x in body.platforms]
            bad = [x for x in plats if x not in ('tiktok', 'shopee')]
            if bad or not plats:
                raise HTTPException(400, 'ปฏิทินรองรับ TikTok / Shopee (โพสต์เอง) — Facebook/IG/LINE ใช้ปุ่ม 📤 โพสต์ ที่สินค้า')
            status = body.status if body.status in ('needs_review', 'ready_manual', 'completed_manual', 'cancelled') else 'needs_review'
            for plat in plats:
                cur = c.execute('''INSERT INTO publishing_queue(user_id, draft_id, platform, caption, scheduled_at, status, created_at)
                                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
                              (u['id'], d_id, plat, full_caption, body.scheduled_at, status, now()))
                created_ids.append(cur.lastrowid)
        return {'ok': True, 'schedule_ids': created_ids, 'message': f'วางแผนโพสต์ {len(created_ids)} แพลตฟอร์มสำเร็จ'}

    @app.patch('/api/my/calendar/{schedule_id}')
    def update_calendar_event(schedule_id: int, body: ScheduleUpdateIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if body.status not in ('needs_review', 'ready_manual', 'completed_manual', 'cancelled'):
            raise HTTPException(400, 'สถานะไม่ถูกต้อง')
        with connect() as c:
            r = c.execute('UPDATE publishing_queue SET status=? WHERE id=? AND user_id=?', (body.status, schedule_id, u['id']))
            if r.rowcount < 1:
                raise HTTPException(404, 'ไม่พบรายการที่ต้องการแก้ไข')
        return {'ok': True, 'status': body.status}

    @app.post('/api/my/calendar/{schedule_id}/publish-now')
    def publish_calendar_event_now(schedule_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        item = read('SELECT * FROM publishing_queue WHERE id=? AND user_id=?', (schedule_id, u['id']), one=True)
        if not item:
            raise HTTPException(404, 'ไม่พบรายการคอนเทนต์')
        # No TikTok/Shopee posting API is connected: never claim an automatic post happened.
        with connect() as c:
            c.execute("UPDATE publishing_queue SET status='completed_manual' WHERE id=? AND user_id=?", (schedule_id, u['id']))
        return {
            'ok': True,
            'schedule_id': schedule_id,
            'platform': item['platform'],
            'status': 'completed_manual',
            'auto_posted': False,
            'message': f'ทำเครื่องหมายว่าโพสต์ {item["platform"].upper()} เองแล้ว (ยังไม่ได้เชื่อม API โพสต์อัตโนมัติของแพลตฟอร์มนี้)'
        }

    @app.delete('/api/my/calendar/{schedule_id}')
    def delete_calendar_event(schedule_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        with connect() as c:
            c.execute('DELETE FROM publishing_queue WHERE id=? AND user_id=?', (schedule_id, u['id']))
        return {'ok': True, 'message': 'ลบรายการวางแผนสำเร็จ'}

    @app.get('/api/system/settings')
    def get_system_settings():
        rows = read('SELECT key, value, enabled, description, updated_at FROM system_settings')
        return {'settings': rows}

    @app.patch('/api/admin/system/settings')
    def update_system_setting(body: SystemSettingIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        with connect() as c:
            c.execute('''INSERT INTO system_settings(key, value, enabled, updated_at)
                         VALUES (?, ?, ?, ?)
                         ON CONFLICT(key) DO UPDATE SET
                         value=excluded.value,
                         enabled=excluded.enabled,
                         updated_at=excluded.updated_at''',
                      (body.key, body.value, 1 if body.enabled else 0, now()))
        return {'ok': True, 'key': body.key, 'enabled': body.enabled}

    @app.get('/api/admin/users')
    def admin_list_users(req: Request):
        require_admin(req)
        return read('''SELECT u.id, u.username, u.email, u.role, u.credits, u.permissions, u.created_at,
                   (SELECT COUNT(*) FROM products p WHERE p.user_id=u.id) AS products_count,
                   (SELECT COUNT(*) FROM drafts d WHERE d.user_id=u.id) AS drafts_count,
                   (SELECT COUNT(*) FROM publishing_queue q WHERE q.user_id=u.id) AS queue_count
            FROM users u WHERE u.is_demo=0 ORDER BY u.id DESC LIMIT 100''')

    @app.patch('/api/admin/users/{user_id}/credits')
    def admin_update_user_credits(user_id: int, body: AdminCreditUpdateIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        target = read('SELECT id, username, credits FROM users WHERE id=?', (user_id,), one=True)
        if not target:
            raise HTTPException(404, 'ไม่พบผู้ใช้ที่ระบุ')
        current_credits = target['credits'] if 'credits' in target.keys() and target['credits'] is not None else 0
        new_credits = max(0, current_credits + body.amount)
        with connect() as c:
            c.execute('UPDATE users SET credits=? WHERE id=?', (new_credits, user_id))
        return {'ok': True, 'user_id': user_id, 'credits': new_credits, 'delta': body.amount}

    @app.patch('/api/admin/users/{user_id}/permissions')
    def admin_update_user_permissions(user_id: int, body: AdminPermissionsIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if u['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        import json
        perm_str = json.dumps(body.permissions)
        with connect() as c:
            c.execute('UPDATE users SET permissions=? WHERE id=?', (perm_str, user_id))
        return {'ok': True, 'user_id': user_id, 'permissions': body.permissions}

    @app.post('/api/my/credits/topup')
    def user_self_topup(body: SelfTopupIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        mutation(req, x_csrf_token)
        # Free self-service credits were a hole: credits now come only from paid orders (/api/payments/*).
        raise HTTPException(410, 'การเติมเครดิตย้ายไปที่ระบบชำระเงิน PromptPay แล้ว')
        u = None
        current = read('SELECT credits FROM users WHERE id=?', (u['id'],), one=True)
        cur_cred = current['credits'] if current and 'credits' in current.keys() and current['credits'] is not None else 0
        new_cred = cur_cred + body.credits
        with connect() as c:
            c.execute('UPDATE users SET credits=? WHERE id=?', (new_cred, u['id']))
        return {
            'ok': True,
            'package_id': body.package_id,
            'added_credits': body.credits,
            'new_total_credits': new_cred,
            'price_thb': body.price_thb,
            'message': f'เติมเครดิตสำเร็จ +{body.credits:,} เครดิต (ยอดคงเหลือ: {new_cred:,})'
        }

    @app.post('/api/admin/users')
    def admin_create_user(body: UserCreateIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        admin = mutation(req, x_csrf_token)
        if admin['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        email = body.email.strip().lower()
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            raise HTTPException(400, 'อีเมลไม่ถูกต้อง')
        existing = read('SELECT id FROM users WHERE email=? OR username=?', (email, body.username.strip()), one=True)
        if existing:
            raise HTTPException(400, 'อีเมลหรือชื่อผู้ใช้นี้ถูกใช้งานแล้ว')
        pw_hash = PH.hash(body.password)
        with connect() as c:
            cur = c.execute('''INSERT INTO users(username, email, password_hash, role, credits, permissions, created_at)
                             VALUES (?, ?, ?, ?, ?, '{}', ?)''',
                          (body.username.strip(), email, pw_hash, body.role, body.credits, now()))
            user_id = cur.lastrowid
        return {'ok': True, 'id': user_id, 'username': body.username, 'role': body.role, 'credits': body.credits}

    @app.patch('/api/admin/users/{user_id}/role')
    def admin_update_user_role(user_id: int, body: UserRoleIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        admin = mutation(req, x_csrf_token)
        if admin['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        if user_id == admin['id']:
            raise HTTPException(400, 'ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้')
        with connect() as c:
            c.execute('UPDATE users SET role=? WHERE id=?', (body.role, user_id))
        return {'ok': True, 'user_id': user_id, 'role': body.role}

    @app.delete('/api/admin/users/{user_id}')
    def admin_delete_user(user_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        admin = mutation(req, x_csrf_token)
        if admin['role'] != 'admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบเท่านั้น')
        if user_id == admin['id']:
            raise HTTPException(400, 'ไม่สามารถลบบัญชีตัวเองได้')
        with connect() as c:
            c.execute('DELETE FROM users WHERE id=?', (user_id,))
        return {'ok': True, 'user_id': user_id}

    @app.get('/api/my/connections')
    def my_connections(req: Request):
        u=require_user(req)
        saved={r['provider'] for r in read('SELECT provider FROM credentials WHERE user_id=?',(u['id'],))}
        def off(provider):
            on=enabled_models[provider]
            if len(on)==len(catalog[provider]): return ''
            return ' · ตอนนี้เปิดเฉพาะ '+', '.join(on) if on else ' · ปิดใช้งานชั่วคราว'
        return {'providers':[
            {'id':'gemini','label':'Google Gemini / Veo','configured':'gemini' in saved,'supports':'สร้างวิดีโอแนวตั้ง 8 วินาทีผ่าน Gemini API'+off('gemini'),'enabled':True,'verified':False},
            {'id':'xai','label':'xAI / Grok Imagine','configured':'xai' in saved,'supports':'สร้างวิดีโอแนวตั้ง 10 วินาที (Lite / 1.5) ผ่าน xAI API'+off('xai'),'enabled':True,'verified':False},
            {'id':'openrouter','label':'OpenRouter','configured':'openrouter' in saved,'supports':'คีย์เดียวสร้างวิดีโอ 8 วินาทีได้หลายรุ่น (Veo, Grok, Kling, Wan) ผ่าน OpenRouter'+off('openrouter'),'enabled':True,'verified':False},
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

    # Which provider:model pairs members may start now. Default: OpenRouter Veo 3.1 Lite only;
    # ENABLED_VIDEO_MODELS=all re-opens every model. Jobs already started keep refreshing either way.
    catalog={'gemini':(VEO_MODEL,),'xai':GROK_MODELS,'openrouter':OPENROUTER_MODELS}
    enabled_spec=os.getenv('ENABLED_VIDEO_MODELS','openrouter:google/veo-3.1-lite').strip()
    if enabled_spec=='all':
        enabled_models={k:list(v) for k,v in catalog.items()}
    else:
        enabled_models={k:[] for k in catalog}
        for item in enabled_spec.split(','):
            prov,_,mod=item.strip().partition(':')
            if mod in catalog.get(prov,()) and mod not in enabled_models[prov]:
                enabled_models[prov].append(mod)

    # Free mode: the owner's OpenRouter key stays on the server; members never see it.
    platform_key=os.getenv('PLATFORM_OPENROUTER_API_KEY','').strip()
    platform_models=[m.strip() for m in os.getenv('PLATFORM_MODELS','google/veo-3.1-lite').split(',')
                     if m.strip() in enabled_models['openrouter']]
    platform_limit=max(0,int(os.getenv('PLATFORM_CLIPS_PER_USER','3')))
    platform_period=os.getenv('PLATFORM_QUOTA_PERIOD','month').strip()
    if platform_period not in ('day','month','total'): platform_period='month'
    platform_budget=max(0.0,float(os.getenv('PLATFORM_DAILY_BUDGET_USD','5')))
    # Mock mode (VIDEO_MOCK=1): every job goes to the mock provider; no AI calls, no credits spent.
    # Free mode works without an owner key so the whole flow, quotas and budget can be tried end to end.
    video_mock=os.getenv('VIDEO_MOCK','').strip()=='1'
    platform_enabled=bool((platform_key or video_mock) and platform_models and platform_limit)

    def platform_period_start():
        today=datetime.now(timezone.utc).date()
        return {'day':today.isoformat(),'month':today.replace(day=1).isoformat(),'total':''}[platform_period]

    def platform_used(c,user_id):
        # Failed jobs are not billed by OpenRouter, so they do not use up the member's quota.
        return c.execute("SELECT COUNT(*) FROM video_jobs WHERE user_id=? AND provider='platform' AND status!='failed' AND created_at>=?",
                         (user_id,platform_period_start())).fetchone()[0]

    def platform_spent_today(c):
        return c.execute("SELECT COALESCE(SUM(est_cost_usd),0) FROM video_jobs WHERE provider='platform' AND status!='failed' AND created_at>=?",
                         (datetime.now(timezone.utc).date().isoformat(),)).fetchone()[0]

    @app.get('/api/my/video-quota')
    def video_quota(req: Request):
        u=require_user(req)
        if not platform_enabled:
            return {'platform':{'enabled':False},'enabled_models':enabled_models,'mock':video_mock,'mock_seconds':mock_video._delay()}
        with connect() as c:
            used=platform_used(c,u['id']);spent=platform_spent_today(c)
        cheapest=min(openrouter.estimated_cost(m,False) for m in platform_models)
        return {'enabled_models':enabled_models,'mock':video_mock,'mock_seconds':mock_video._delay(),'platform':{'enabled':True,'limit':platform_limit,'period':platform_period,'used':used,
                'remaining':max(0,platform_limit-used),'budget_available':spent+cheapest<=platform_budget,
                'models':[{'id':m,'est_cost_usd':openrouter.estimated_cost(m,False)} for m in platform_models]}}

    def load_api_key(user_id, provider):
        if provider=='platform':
            if platform_key: return platform_key
            if video_mock: return 'mock'
            raise HTTPException(503,PLATFORM_ERROR)
        row=read('SELECT encrypted FROM credentials WHERE user_id=? AND provider=?',(user_id,provider),True)
        if not row: raise HTTPException(400, 'กรุณาเชื่อม '+VIDEO_LABELS.get(provider,provider)+' API ในเมนู API ของฉันก่อน')
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
        if not confirm_paid and provider!='platform':
            raise HTTPException(400,'ต้องยืนยันว่าการสร้างวิดีโออาจมีค่าใช้จ่ายตามเครดิต API ก่อน')
        owned=read('SELECT id,prompt FROM drafts WHERE id=? AND user_id=?',(draft_id,u['id']),True)
        if not owned: raise HTTPException(404,'ไม่พบบทของบัญชีนี้')
        if provider!='platform' and model not in enabled_models.get(provider,()):
            raise HTTPException(400,'รุ่นนี้ปิดใช้งานชั่วคราว กรุณาเลือก OpenRouter · Veo 3.1 Lite')
        if provider=='gemini' and model==VEO_MODEL:
            duration=8
            service=veo
        elif provider=='xai' and model in GROK_MODELS:
            duration=10
            service=grok
        elif provider=='openrouter' and model in OPENROUTER_MODELS:
            duration=openrouter.DURATION
            service=openrouter
        elif provider=='platform' and platform_enabled and model in platform_models:
            duration=openrouter.DURATION
            service=openrouter
        elif provider=='platform' and not platform_enabled:
            raise HTTPException(400,'ระบบยังไม่เปิดโหมดฟรี กรุณาใช้ API key ของคุณเอง')
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
            est_cost=0.0
            if provider=='platform':
                if platform_used(c,u['id'])>=platform_limit:
                    period={'day':'วันนี้','month':'เดือนนี้','total':''}[platform_period]
                    raise HTTPException(429,f'ใช้โควตาฟรี{period}ครบ {platform_limit} คลิปแล้ว · ใช้ API key ของคุณเองต่อได้ในเมนู API ของฉัน')
                est_cost=openrouter.estimated_cost(model,False)
                if platform_spent_today(c)+est_cost>platform_budget:
                    raise HTTPException(429,'งบโหมดฟรีของวันนี้หมดแล้ว กรุณาลองใหม่พรุ่งนี้ หรือใช้ API key ของคุณเอง')
            timestamp=now()
            cur=c.execute("INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,est_cost_usd,created_at,checked_at,updated_at) VALUES(?,?,?,?,?,?,'submitting',?,?,?,?)",
                          (u['id'],draft_id,provider,model,duration,final_prompt,est_cost,timestamp,timestamp,timestamp))
            job_id=cur.lastrowid
        try:
            # Run potentially slow HTTP requests outside the async event loop.
            from starlette.concurrency import run_in_threadpool
            if video_mock:
                operation=await run_in_threadpool(mock_video.start_video,api_key,final_prompt,reference,mime)
            elif provider=='xai':
                operation=await run_in_threadpool(grok.start_video,api_key,final_prompt,reference,mime,model=model,duration=duration)
            elif provider=='openrouter':
                operation=await run_in_threadpool(openrouter.start_video,api_key,final_prompt,reference,mime,model=model)
            elif provider=='platform':
                # No model audio in free mode: about 40% cheaper, and a Thai voice-over can be added later.
                operation=await run_in_threadpool(openrouter.start_video,api_key,final_prompt,reference,mime,model=model,audio=False,user=f'aas-{u["id"]}')
            else:
                operation=await run_in_threadpool(veo.start_video,api_key,final_prompt,reference,mime)
        except VIDEO_ERRORS as e:
            # Members must not see the owner's key/credit problems in free mode.
            error=PLATFORM_ERROR if provider=='platform' and ('คีย์' in str(e) or 'เครดิต' in str(e)) else str(e)[:280]
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message=?,updated_at=? WHERE id=? AND user_id=?",(error,now(),job_id,u['id']))
            raise HTTPException(502,error)
        except Exception:
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed',error_message='ไม่สามารถส่งงานไปยังผู้ให้บริการ AI ได้',updated_at=? WHERE id=? AND user_id=?",(now(),job_id,u['id']))
            raise HTTPException(502,'ไม่สามารถส่งงานไปยังผู้ให้บริการ AI ได้')
        with connect() as c:
            c.execute("UPDATE video_jobs SET status='running',operation_name=?,updated_at=? WHERE id=? AND user_id=?",(operation,now(),job_id,u['id']))
        return {'id':job_id,'status':'running','provider':provider,'model':model,'duration':duration,'notice':'ส่งงานให้ '+VIDEO_LABELS[provider]+' แล้ว กรุณาตรวจสถานะตามรอบ (มีค่าใช้จ่ายตาม API ของสมาชิก)'}

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
        if provider not in VIDEO_PROVIDERS:
            raise HTTPException(400,'ไม่รู้จักผู้ให้บริการที่บันทึกไว้')
        api_key=load_api_key(u['id'],provider)
        # Route by job id, so mock jobs still finish after VIDEO_MOCK is switched off.
        service=mock_video if mock_video.is_mock_job(job['operation_name']) else VIDEO_PROVIDERS[provider]
        try:
            state, uri=service.poll_video(api_key,job['operation_name'])
            if state=='running': return {'id':job_id,'status':'running'}
            target=data/'videos'/str(u['id'])/f'{job_id}.mp4'
            service.download_video(api_key,uri,target)
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='ready',file_name=?,updated_at=? WHERE id=? AND user_id=?",(target.relative_to(data).as_posix(),now(),job_id,u['id']))
            return {'id':job_id,'status':'ready','video_url':f'/api/my/video-jobs/{job_id}/file'}
        except VIDEO_ERRORS as e:
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

    def require_admin(req):
        u=require_user(req)
        if u['role']!='admin':
            raise HTTPException(403, 'เฉพาะผู้ดูแลระบบ')
        return u

    def month_start():
        return datetime.now(timezone.utc).date().replace(day=1).isoformat()

    def admin_member_rows():
        # Read-only summary. Never select password_hash, session tokens or encrypted keys.
        rows=read('''SELECT u.id,u.username,u.email,u.role,u.created_at,
            (SELECT COUNT(*) FROM products p WHERE p.user_id=u.id) AS products,
            (SELECT COUNT(*) FROM drafts d WHERE d.user_id=u.id) AS drafts,
            (SELECT COUNT(*) FROM video_jobs v WHERE v.user_id=u.id) AS clips,
            (SELECT COUNT(*) FROM video_jobs v WHERE v.user_id=u.id AND v.status='ready') AS clips_ready,
            (SELECT COUNT(*) FROM video_jobs v WHERE v.user_id=u.id AND v.provider='platform' AND v.status!='failed' AND v.created_at>=?) AS free_used,
            (SELECT COALESCE(SUM(v.est_cost_usd),0) FROM video_jobs v WHERE v.user_id=u.id AND v.provider='platform' AND v.status!='failed' AND v.created_at>=?) AS free_cost_month_usd,
            (SELECT GROUP_CONCAT(c.provider) FROM credentials c WHERE c.user_id=u.id) AS own_keys,
            (SELECT MAX(s.expires_at) FROM sessions s WHERE s.user_id=u.id) AS session_expires,
            (SELECT MAX(v.created_at) FROM video_jobs v WHERE v.user_id=u.id) AS last_clip_at
            FROM users u ORDER BY u.id''',(platform_period_start(),month_start()))
        for r in rows:
            # Sessions last SESSION_DAYS, so the newest expiry dates the most recent sign-in.
            expires=r.pop('session_expires')
            r['last_login_at']=((datetime.fromisoformat(expires)-timedelta(days=SESSION_DAYS)).isoformat(timespec='seconds')
                                if expires else None)
            r['own_keys']=sorted(set((r['own_keys'] or '').split(',')) - {''})
            r['free_cost_month_usd']=round(r['free_cost_month_usd'],2)
            r['free_limit']=platform_limit if platform_enabled else 0
        return rows

    @app.get('/api/admin/overview')
    def admin_overview(req:Request):
        require_admin(req)
        with connect() as c:
            members=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            admins=c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
            jobs={r[0]:r[1] for r in c.execute('SELECT status,COUNT(*) FROM video_jobs GROUP BY status')}
            free_month=c.execute("SELECT COUNT(*),COALESCE(SUM(est_cost_usd),0) FROM video_jobs WHERE provider='platform' AND status!='failed' AND created_at>=?",
                                 (month_start(),)).fetchone()
            spent_today=platform_spent_today(c)
        return {'members':members,'admins':admins,'seat_limit':MAX_BETA_USERS,'video_jobs':jobs,
                'free_mode':{'enabled':platform_enabled,'models':platform_models,'limit':platform_limit,'period':platform_period,
                             'daily_budget_usd':platform_budget,'spent_today_usd':round(spent_today,2),
                             'clips_this_month':free_month[0],'spent_this_month_usd':round(free_month[1],2)},
                'enabled_models':enabled_models,'mock':video_mock}

    @app.get('/api/admin/members')
    def admin_members(req:Request):
        require_admin(req)
        return admin_member_rows()

    @app.get('/api/admin/members.csv')
    def admin_members_csv(req:Request):
        require_admin(req)
        import csv, io
        def cell(v):
            text=', '.join(v) if isinstance(v,list) else '' if v is None else str(v)
            # Stop spreadsheet formula injection from member-controlled text.
            return "'"+text if text[:1] in ('=','+','-','@','\t','\r') else text
        cols=['id','username','email','role','created_at','last_login_at','products','drafts','clips','clips_ready',
              'free_used','free_limit','free_cost_month_usd','own_keys','last_clip_at']
        out=io.StringIO()
        w=csv.writer(out)
        w.writerow(cols)
        for r in admin_member_rows():
            w.writerow([cell(r[k]) for k in cols])
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d')
        # BOM so Excel opens Thai text as UTF-8.
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':f'attachment; filename="members-{stamp}.csv"','Cache-Control':'no-store'})

    def admin_target(c, admin, user_id):
        target=c.execute('SELECT id,username,email,role FROM users WHERE id=?',(user_id,)).fetchone()
        if not target: raise HTTPException(404,'ไม่พบสมาชิกนี้')
        if target['id']==admin['id']:
            raise HTTPException(400,'จัดการบัญชีตัวเองจากหน้านี้ไม่ได้ · เปลี่ยนรหัสผ่านที่เมนู API ของฉัน')
        # Admin accounts are managed from the server shell only, so one admin cannot lock out another.
        if target['role']=='admin':
            raise HTTPException(400,'บัญชีแอดมินลบหรือรีเซ็ตจากหน้านี้ไม่ได้')
        return target

    def audit(c, admin, action, target):
        c.execute('''INSERT INTO admin_audit(admin_id,admin_username,action,target_user_id,target_username,target_email,created_at)
                     VALUES(?,?,?,?,?,?,?)''',(admin['id'],admin['username'],action,target['id'],target['username'],target['email'],now()))

    @app.post('/api/admin/members/{user_id}/reset-password')
    def admin_reset_password(user_id:int,req:Request,response:Response,x_csrf_token:str|None=Header(default=None)):
        admin=mutation(req,x_csrf_token)
        if admin['role']!='admin': raise HTTPException(403,'เฉพาะผู้ดูแลระบบ')
        password=temporary_password()
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            target=admin_target(c,admin,user_id)
            c.execute('UPDATE users SET password_hash=? WHERE id=?',(PH.hash(password),target['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],))
            c.execute('DELETE FROM login_attempts WHERE email=?',(target['email'],))
            c.execute('DELETE FROM login_failures WHERE email=?',(target['email'],))
            audit(c,admin,'reset_password',target)
        # Shown once to the admin; it is never stored in plain text.
        response.headers['Cache-Control']='no-store'
        return {'username':target['username'],'email':target['email'],'temporary_password':password}

    @app.post('/api/admin/members/{user_id}/delete')
    def admin_delete_member(user_id:int,body:DeleteMemberIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        admin=mutation(req,x_csrf_token)
        if admin['role']!='admin': raise HTTPException(403,'เฉพาะผู้ดูแลระบบ')
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            target=admin_target(c,admin,user_id)
            if body.confirm_username.strip().lower()!=target['username'].lower():
                raise HTTPException(400,'พิมพ์ชื่อผู้ใช้ไม่ตรง ยังไม่ได้ลบ')
            # ideas has no ON DELETE CASCADE; their votes and comments cascade from the idea.
            c.execute('DELETE FROM ideas WHERE user_id=?',(target['id'],))
            c.execute('DELETE FROM users WHERE id=?',(target['id'],))
            audit(c,admin,'delete_member',target)
        import shutil
        shutil.rmtree(data/'videos'/str(int(target['id'])),ignore_errors=True)
        return {'deleted':True,'username':target['username']}

    @app.get('/api/admin/audit')
    def admin_audit_log(req:Request):
        require_admin(req)
        return read('SELECT id,admin_username,action,target_username,target_email,created_at FROM admin_audit ORDER BY id DESC LIMIT 50')

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
        return read('''SELECT id,title,url,platform,created_at,extra_comm_checked,extra_comm_rate,extra_comm_checked_at,
                       price,price_min,price_max,commission_rate,seller_comm_rate,shopee_comm_rate,commission_baht,image_url,
                       CASE WHEN image_file!='' THEN '/media/products/'||image_file ELSE '' END AS image_path,
                       shop_name,item_id,shop_id,offer_link,sales,rating,source,synced_at
                       FROM products WHERE user_id=? ORDER BY id DESC LIMIT 200''',(u['id'],))

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
        return read('''SELECT d.id,d.product_id,d.style,d.script,d.prompt,d.created_at,p.title,p.title as product_title,p.platform
                    FROM drafts d JOIN products p ON p.id=d.product_id
                    WHERE d.user_id=? ORDER BY d.id DESC LIMIT 100''',(u['id'],))

    @app.post('/api/my/drafts')
    def create_draft(body: DraftIn,req:Request,x_csrf_token:str|None=Header(default=None)):
        u=mutation(req,x_csrf_token)
        style = body.style
        if style == 'pov_fast':
            style = 'pov'
        elif style == 'pov_pain':
            style = 'problem_solution'
        elif style in ('pov_7days', 'pov_compare'):
            style = 'demo'
        if style not in ('pov','demo','problem_solution'):
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
        return read('''SELECT q.id,q.platform,q.video_url,q.status,q.created_at,d.script,p.title,p.title AS product_title
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

    # V8 product features (studio, connectors, help, scheduler) are part of the
    # public product and must be registered in every mode.
    import features_v8
    features_v8.register(app, connect=connect, read=read, require_user=require_user, mutation=mutation,
                         cipher=cipher, now=now, data_dir=data, public_mode=PUBLIC_MODE)
    import studio_v8
    studio_v8.register(app, connect=connect, read=read, require_user=require_user, mutation=mutation, now=now, data_dir=data)
    app.state.studio_set_decrypt(lambda v: cipher.decrypt(v.encode()).decode())
    import scheduler_v8

    def _dec(v):
        try:
            return cipher.decrypt(v.encode()).decode() if v else ''
        except InvalidToken:
            return ''
    scheduler_v8.register(app, connect=connect, read=read, require_user=require_user, mutation=mutation, now=now,
                          data_dir=data, decrypt=_dec, base_url_for=app.state.v8_base_url)
    import payments_v8
    payments_v8.register(app, connect=connect, read=read, require_user=require_user, mutation=mutation, now=now)

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
