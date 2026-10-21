"""Phase 1 guided Studio: product → UGC script → preview clip → save/download → post.

One platform (TikTok, manual post) and one AI engine (Google Veo 3.1 Lite via OpenRouter).
Every step has an explicit status; AI clips show credit cost up front, charge on submit and
refund automatically on failure.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from integrations import ugc
from studio_v6 import mock_video_service as mock_video
from studio_v6 import openrouter_service as openrouter

ENGINE_MODEL = 'google/veo-3.1-lite'
ENGINE_LABEL = 'Google Veo 3.1 Lite (ผ่าน OpenRouter)'
MAX_PREVIEW_BYTES = 40 * 1024 * 1024
IMAGE_PROXY_HOSTS = ('cf.shopee.co.th', 'down-th.img.susercontent.com', 'img.susercontent.com', 'down-ws-th.img.susercontent.com')
STATUS_LABELS = {
    'script_ready': 'บทพร้อมแล้ว',
    'preview_ready': 'คลิปตัวอย่างพร้อม',
    'clip_running': 'กำลังสร้างคลิป AI',
    'clip_ready': 'คลิป AI พร้อม',
    'clip_failed': 'สร้างคลิปไม่สำเร็จ (คืนเครดิตแล้ว)',
    'saved': 'บันทึกแล้ว',
    'queued_tiktok': 'อยู่ในคิว TikTok (โพสต์เอง)',
}


class ProjectIn(BaseModel):
    product_id: int = Field(gt=0)
    style: str = Field(pattern=r'^ugc_[a-z0-9_]{2,20}$')


class ProjectPatch(BaseModel):
    script: dict | None = None
    caption: str | None = Field(default=None, max_length=600)
    style: str | None = Field(default=None, pattern=r'^ugc_[a-z0-9_]{2,20}$')
    regenerate: bool = False


class QuickProductIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    platform: str = Field(default='other', pattern=r'^(shopee|tiktok|other)$')
    url: str = Field(default='', max_length=1000)
    source: str = Field(default='manual', pattern=r'^(manual|radar)$')


def register(app: FastAPI, *, connect, read, require_user, mutation, now, data_dir: Path):
    sample_img = '/static/samples/sample-fan.svg'

    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS studio_projects (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
          style TEXT NOT NULL, script_json TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'script_ready',
          preview_file TEXT NOT NULL DEFAULT '', video_job_id INTEGER, engine_mode TEXT NOT NULL DEFAULT '',
          credits_charged INTEGER NOT NULL DEFAULT 0, credits_refunded INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '', is_sample INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS studio_projects_owner ON studio_projects(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS credit_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          delta INTEGER NOT NULL, reason TEXT NOT NULL, project_id INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS studio_seeded (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE);
        ''')
        cols = {r[1] for r in db.execute('PRAGMA table_info(studio_projects)')}
        if 'ready_job_id' not in cols:
            db.execute('ALTER TABLE studio_projects ADD COLUMN ready_job_id INTEGER')

    # ------------------------------------------------------------------ engine
    def engine_for(user_id):
        cost = max(0, int(os.getenv('STUDIO_CLIP_CREDITS', '10') or 10))
        if os.getenv('VIDEO_MOCK', '').strip() == '1':
            return {'mode': 'simulate', 'label': ENGINE_LABEL + ' — โหมดจำลอง (VIDEO_MOCK)', 'cost_credits': cost,
                    'note': 'จำลองการสร้างคลิป AI ทั้งขั้นตอน (หักเครดิต/คืนเครดิตจริง แต่ไม่เรียก AI) ใส่คำว่า MOCK_FAIL ในบทเพื่อทดสอบกรณีล้มเหลว',
                    'seconds': mock_video._delay()}
        if os.getenv('PLATFORM_OPENROUTER_API_KEY', '').strip():
            return {'mode': 'ai_platform', 'label': ENGINE_LABEL, 'cost_credits': cost,
                    'note': 'ใช้เครดิตของระบบ หากล้มเหลวจะคืนเครดิตอัตโนมัติ', 'seconds': 90}
        if read("SELECT 1 FROM credentials WHERE user_id=? AND provider='openrouter'", (user_id,), True):
            est = openrouter.estimated_cost(ENGINE_MODEL, False)
            return {'mode': 'ai_own_key', 'label': ENGINE_LABEL + ' — คีย์ OpenRouter ของคุณ', 'cost_credits': 0,
                    'note': f'ไม่ใช้เครดิตระบบ · ค่าใช้จ่ายประมาณ ${est:.2f}/คลิป คิดกับบัญชี OpenRouter ของคุณ', 'seconds': 90}
        return {'mode': 'sample', 'label': 'คลิปตัวอย่าง (ยังไม่ได้เชื่อม AI)', 'cost_credits': 0,
                'note': 'ยังไม่มีเอนจิน AI ที่ใช้งานได้ — ใช้ "คลิปพรีวิว" ที่สร้างในเบราว์เซอร์ได้ฟรี หรือบันทึกคีย์ OpenRouter ในเมนู API Keys',
                'seconds': 0}

    def credits_of(user_id):
        r = read('SELECT credits FROM users WHERE id=?', (user_id,), True)
        return int((r or {}).get('credits') or 0)

    # ------------------------------------------------------------------ helpers
    def own_project(user_id, pid):
        p = read('SELECT * FROM studio_projects WHERE id=? AND user_id=?', (pid, user_id), True)
        if not p:
            raise HTTPException(404, 'ไม่พบโปรเจกต์นี้')
        return p

    def project_out(p):
        prod = read('''SELECT id,title,price,commission_rate,commission_baht,image_url,image_file,offer_link,url,source,rating,sales
                       FROM products WHERE id=?''', (p['product_id'],), True) or {}
        img = prod.get('image_url') or (f"/media/products/{prod['image_file']}" if prod.get('image_file') else '')
        if prod.get('source') == 'sample' and not img:
            img = sample_img
        job = None
        if p.get('video_job_id'):
            job = read('SELECT id,status,error_message,provider,model FROM video_jobs WHERE id=?', (p['video_job_id'],), True)
        # The last successful (paid) clip stays available even if a later attempt fails.
        ready_id = p.get('ready_job_id') or (job['id'] if job and job['status'] == 'ready' else None)
        return {**{k: p[k] for k in ('id', 'product_id', 'draft_id', 'style', 'caption', 'status', 'engine_mode',
                                    'credits_charged', 'credits_refunded', 'error', 'is_sample', 'created_at', 'updated_at')},
                'status_label': STATUS_LABELS.get(p['status'], p['status']),
                'script': json.loads(p['script_json']),
                'product': {**{k: prod.get(k) for k in ('id', 'title', 'price', 'commission_rate', 'commission_baht', 'source', 'rating', 'sales')},
                            'image': img, 'link': prod.get('offer_link') or prod.get('url') or ''},
                'preview_url': f"/api/studio/projects/{p['id']}/preview" if p['preview_file'] else '',
                'clip_url': f"/api/my/video-jobs/{ready_id}/file" if ready_id else '',
                'job': job}

    def set_status(pid, status, **extra):
        cols = ', '.join(f'{k}=?' for k in extra)
        with connect() as c:
            c.execute(f'UPDATE studio_projects SET status=?, updated_at=?{", " + cols if cols else ""} WHERE id=?',
                      (status, now(), *extra.values(), pid))

    def make_draft(c, user_id, product_id, style, script):
        number = c.execute('SELECT COUNT(*) FROM product_use_events WHERE user_id=? AND product_id=?',
                           (user_id, product_id)).fetchone()[0] + 1
        created = now()
        cur = c.execute('INSERT INTO drafts(user_id,product_id,style,script,prompt,created_at) VALUES(?,?,?,?,?,?)',
                        (user_id, product_id, style, ugc.to_text(script), ugc.to_prompt(script), created))
        c.execute('INSERT INTO product_use_events(user_id,product_id,draft_id,use_number,created_at) VALUES(?,?,?,?,?)',
                  (user_id, product_id, cur.lastrowid, number, created))
        return cur.lastrowid

    def seed_if_new(user_id):
        """Give a brand-new member a sample product + ready script so the flow is usable immediately."""
        if read('SELECT 1 FROM studio_seeded WHERE user_id=?', (user_id,), True):
            return
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM studio_seeded WHERE user_id=?', (user_id,)).fetchone():
                return
            c.execute('INSERT INTO studio_seeded(user_id) VALUES(?)', (user_id,))
            if c.execute('SELECT COUNT(*) FROM products WHERE user_id=?', (user_id,)).fetchone()[0]:
                return
            cur = c.execute('''INSERT INTO products(user_id,title,url,platform,created_at,price,commission_rate,commission_baht,
                               source,rating,sales) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                            (user_id, 'พัดลมพกพาไร้ใบพัด ชาร์จ USB (สินค้าตัวอย่าง)', '', 'other', now(), 199, 10, 19.9,
                             'sample', None, None))
            # No invented rating/sales: the sample only carries an example price/commission and is labelled as a sample.
            product = {'title': 'พัดลมพกพาไร้ใบพัด ชาร์จ USB', 'price': 199}
            script = ugc.generate(product, 'ugc_pov')
            draft_id = make_draft(c, user_id, cur.lastrowid, 'ugc_pov', script)
            c.execute('''INSERT INTO studio_projects(user_id,product_id,draft_id,style,script_json,caption,status,is_sample,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,'script_ready',1,?,?)''',
                      (user_id, cur.lastrowid, draft_id, 'ugc_pov', json.dumps(script, ensure_ascii=False),
                       script['caption'] + '\n' + script['hashtags'], now(), now()))

    # ------------------------------------------------------------------ routes
    @app.get('/api/studio/bootstrap')
    def bootstrap(req: Request):
        u = require_user(req)
        seed_if_new(u['id'])
        products = read('''SELECT id,title,price,commission_rate,commission_baht,image_url,image_file,source,platform,offer_link,url
                           FROM products WHERE user_id=? AND COALESCE(active,1)=1 ORDER BY id DESC LIMIT 100''', (u['id'],))
        for p in products:
            p['image'] = p['image_url'] or (f"/media/products/{p['image_file']}" if p['image_file'] else (sample_img if p['source'] == 'sample' else ''))
        projects = [project_out(p) for p in read('SELECT * FROM studio_projects WHERE user_id=? ORDER BY id DESC LIMIT 20', (u['id'],))]
        chans = read("""SELECT id,platform,account_name FROM connected_channels WHERE user_id=? AND platform IN ('facebook','instagram','line_oa')
                        AND access_token_encrypted IS NOT NULL AND access_token_encrypted!=''""", (u['id'],))
        return {'styles': ugc.STYLES, 'products': products, 'projects': projects, 'engine': engine_for(u['id']),
                'credits': credits_of(u['id']), 'channels': chans,
                'platforms': {'tiktok': {'connected': False, 'mode': 'manual',
                                         'note': 'ยังไม่เชื่อมต่อ TikTok API — ดาวน์โหลดคลิป + คัดลอกแคปชั่น แล้วอัปโหลดเองที่ tiktok.com/upload'}}}

    @app.post('/api/studio/quick-product')
    def quick_product(body: QuickProductIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        """Radar → Studio shortcut: create (or reuse) a product from a title."""
        u = mutation(req, x_csrf_token)
        url = body.url.strip()
        if url and not url.startswith('https://'):
            url = ''
        existing = read('SELECT id FROM products WHERE user_id=? AND title=?', (u['id'], body.title.strip()), True)
        if existing:
            return {'id': existing['id'], 'reused': True}
        with connect() as c:
            cur = c.execute("INSERT INTO products(user_id,title,url,platform,created_at,source) VALUES(?,?,?,?,?,?)",
                            (u['id'], body.title.strip(), url, body.platform, now(), body.source))
        return {'id': cur.lastrowid, 'reused': False}

    @app.post('/api/studio/projects')
    def create_project(body: ProjectIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        if body.style not in ugc.STYLE_IDS:
            raise HTTPException(400, 'สไตล์ UGC ไม่ถูกต้อง')
        prod = read('SELECT * FROM products WHERE id=? AND user_id=?', (body.product_id, u['id']), True)
        if not prod:
            raise HTTPException(404, 'ไม่พบสินค้าในบัญชีของคุณ')
        script = ugc.generate(prod, body.style)
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            draft_id = make_draft(c, u['id'], prod['id'], body.style, script)
            cur = c.execute('''INSERT INTO studio_projects(user_id,product_id,draft_id,style,script_json,caption,status,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,'script_ready',?,?)''',
                            (u['id'], prod['id'], draft_id, body.style, json.dumps(script, ensure_ascii=False),
                             script['caption'] + '\n' + script['hashtags'], now(), now()))
            pid = cur.lastrowid
        return {'project': project_out(own_project(u['id'], pid)), 'message': 'สร้างบท UGC สำเร็จ — แก้ไขได้ก่อนทำคลิป'}

    @app.get('/api/studio/projects')
    def list_projects(req: Request):
        u = require_user(req)
        return {'projects': [project_out(p) for p in read('SELECT * FROM studio_projects WHERE user_id=? ORDER BY id DESC LIMIT 50', (u['id'],))]}

    @app.get('/api/studio/projects/{pid}')
    def get_project(pid: int, req: Request):
        u = require_user(req)
        return {'project': project_out(own_project(u['id'], pid)), 'credits': credits_of(u['id']), 'engine': engine_for(u['id'])}

    @app.patch('/api/studio/projects/{pid}')
    def patch_project(pid: int, body: ProjectPatch, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        if p['status'] == 'clip_running':
            raise HTTPException(409, 'กำลังสร้างคลิปอยู่ แก้บทไม่ได้จนกว่าจะเสร็จ')
        script = json.loads(p['script_json'])
        style = body.style or p['style']
        if body.regenerate or (body.style and body.style != p['style']):
            if style not in ugc.STYLE_IDS:
                raise HTTPException(400, 'สไตล์ UGC ไม่ถูกต้อง')
            prod = read('SELECT * FROM products WHERE id=?', (p['product_id'],), True)
            variant = (secrets.randbelow(1000) + 1) if body.regenerate else 0
            script = ugc.generate(prod, style, variant)
            caption = script['caption'] + '\n' + script['hashtags']
        else:
            caption = p['caption']
        if body.script is not None:
            scenes = body.script.get('scenes')
            if not isinstance(scenes, list) or not 2 <= len(scenes) <= 8:
                raise HTTPException(400, 'บทต้องมี 2–8 ฉาก')
            clean = []
            for s in scenes:
                if not isinstance(s, dict):
                    raise HTTPException(400, 'รูปแบบฉากไม่ถูกต้อง')
                clean.append({k: str(s.get(k, ''))[:200] for k in ('t', 'visual', 'text', 'voice')})
            script['scenes'] = clean
            script['hook'] = clean[0]['text']
        if body.caption is not None:
            caption = body.caption.strip()
        with connect() as c:
            c.execute('''UPDATE studio_projects SET script_json=?, caption=?, style=?, status=CASE WHEN status IN ('clip_running') THEN status ELSE 'script_ready' END,
                         preview_file='', updated_at=? WHERE id=?''', (json.dumps(script, ensure_ascii=False), caption, style, now(), pid))
            if p['draft_id']:
                c.execute('UPDATE drafts SET script=?, prompt=?, style=? WHERE id=? AND user_id=?',
                          (ugc.to_text(script), ugc.to_prompt(script), style, p['draft_id'], u['id']))
        return {'project': project_out(own_project(u['id'], pid)), 'message': 'บันทึกบทแล้ว'}

    @app.post('/api/studio/projects/{pid}/preview')
    async def upload_preview(pid: int, req: Request, file: UploadFile = File(...), x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        ctype = (file.content_type or '').split(';')[0]
        ext = {'video/webm': '.webm', 'video/mp4': '.mp4'}.get(ctype)
        if not ext:
            raise HTTPException(400, 'รองรับไฟล์ WebM หรือ MP4 เท่านั้น')
        data = await file.read(MAX_PREVIEW_BYTES + 1)
        if not data or len(data) > MAX_PREVIEW_BYTES:
            raise HTTPException(400, 'ไฟล์คลิปต้องไม่เกิน 40 MB')
        if not (data[:4] == b'\x1aE\xdf\xa3' or data[4:8] == b'ftyp'):
            raise HTTPException(400, 'ไฟล์ไม่ใช่วิดีโอที่ถูกต้อง')
        folder = data_dir / 'videos' / str(u['id'])
        folder.mkdir(parents=True, exist_ok=True)
        name = f'studio_{pid}{ext}'
        for old in folder.glob(f'studio_{pid}.*'):
            old.unlink(missing_ok=True)
        (folder / name).write_bytes(data)
        new_status = p['status'] if p['status'] in ('clip_ready', 'saved', 'queued_tiktok', 'clip_running') else 'preview_ready'
        set_status(pid, new_status, preview_file=name)
        return {'project': project_out(own_project(u['id'], pid)), 'message': 'บันทึกคลิปพรีวิวลงคลังแล้ว'}

    @app.get('/api/studio/projects/{pid}/preview')
    def get_preview(pid: int, req: Request):
        u = require_user(req)
        p = own_project(u['id'], pid)
        if not re.fullmatch(r'studio_\d+\.(webm|mp4)', p['preview_file'] or ''):
            raise HTTPException(404, 'ยังไม่มีคลิปพรีวิว')
        path = data_dir / 'videos' / str(u['id']) / p['preview_file']
        if not path.is_file():
            raise HTTPException(404, 'ไม่พบไฟล์')
        media = 'video/webm' if path.suffix == '.webm' else 'video/mp4'
        return FileResponse(path, media_type=media, filename=f'ugc_tiktok_{pid}{path.suffix}',
                            headers={'Cache-Control': 'private, no-store'})

    # ---------------- AI clip with credits
    def refund(user_id, p, reason):
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT credits_charged, credits_refunded FROM studio_projects WHERE id=?', (p['id'],)).fetchone()
            if row and row['credits_charged'] and not row['credits_refunded']:
                c.execute('UPDATE users SET credits=credits+? WHERE id=?', (row['credits_charged'], user_id))
                c.execute('UPDATE studio_projects SET credits_refunded=1 WHERE id=?', (p['id'],))
                c.execute('INSERT INTO credit_ledger(user_id,delta,reason,project_id,created_at) VALUES(?,?,?,?,?)',
                          (user_id, row['credits_charged'], 'refund: ' + reason[:120], p['id'], now()))

    @app.post('/api/studio/projects/{pid}/ai-clip')
    async def start_ai_clip(pid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        eng = engine_for(u['id'])
        if eng['mode'] == 'sample':
            raise HTTPException(409, eng['note'])
        if p['status'] == 'clip_running':
            raise HTTPException(409, 'คลิปนี้กำลังสร้างอยู่')
        cost = eng['cost_credits']
        script = json.loads(p['script_json'])
        prompt = ugc.to_prompt(script)
        if 'MOCK_FAIL' in p['script_json']:
            prompt += ' MOCK_FAIL'
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            busy = c.execute("SELECT COUNT(*) FROM video_jobs WHERE user_id=? AND status IN ('submitting','running')", (u['id'],)).fetchone()[0]
            if busy:
                raise HTTPException(409, 'มีงานสร้างวิดีโออื่นกำลังทำอยู่ กรุณารอให้เสร็จก่อน')
            if cost:
                ok = c.execute('UPDATE users SET credits=credits-? WHERE id=? AND credits>=?', (cost, u['id'], cost)).rowcount
                if not ok:
                    raise HTTPException(402, f'เครดิตไม่พอ: ต้องใช้ {cost} เครดิต (คงเหลือ {credits_of(u["id"])}) — กด "เติมเครดิต" ที่แถบบน')
                c.execute('INSERT INTO credit_ledger(user_id,delta,reason,project_id,created_at) VALUES(?,?,?,?,?)',
                          (u['id'], -cost, 'AI clip ' + ENGINE_MODEL, pid, now()))
            ts = now()
            provider = 'openrouter' if eng['mode'] == 'ai_own_key' else 'platform'
            cur = c.execute('''INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,est_cost_usd,created_at,checked_at,updated_at)
                               VALUES(?,?,?,?,?,?,'submitting',?,?,?,?)''',
                            (u['id'], p['draft_id'], provider, ENGINE_MODEL, openrouter.DURATION, prompt,
                             openrouter.estimated_cost(ENGINE_MODEL, False), ts, ts, ts))
            job_id = cur.lastrowid
            c.execute('''UPDATE studio_projects SET status='clip_running', video_job_id=?, engine_mode=?, credits_charged=?,
                         credits_refunded=0, error='', updated_at=? WHERE id=?''', (job_id, eng['mode'], cost, ts, pid))
        from starlette.concurrency import run_in_threadpool
        try:
            if eng['mode'] == 'simulate':
                op = await run_in_threadpool(mock_video.start_video, 'mock', prompt, None, None)
            else:
                key = os.getenv('PLATFORM_OPENROUTER_API_KEY', '').strip() if eng['mode'] == 'ai_platform' else _own_key(u['id'])
                op = await run_in_threadpool(openrouter.start_video, key, prompt, None, None, model=ENGINE_MODEL, audio=False,
                                             user=f'aas-{u["id"]}')
        except Exception as e:  # provider rejected the job → fail + refund
            err = str(e)[:280] or 'ส่งงานไม่สำเร็จ'
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed', error_message=?, updated_at=? WHERE id=?", (err, now(), job_id))
            set_status(pid, 'clip_failed', error=err)
            refund(u['id'], own_project(u['id'], pid), err)
            raise HTTPException(502, f'สร้างคลิปไม่สำเร็จ: {err} — คืน {cost} เครดิตแล้ว กด "ลองใหม่" ได้')
        with connect() as c:
            c.execute("UPDATE video_jobs SET status='running', operation_name=?, updated_at=? WHERE id=?", (op, now(), job_id))
        return {'project': project_out(own_project(u['id'], pid)), 'credits': credits_of(u['id']),
                'message': f'ส่งงานแล้ว (ใช้ {cost} เครดิต) — ระบบจะตรวจสถานะให้อัตโนมัติ'}

    cipher_holder = {}

    def _own_key(user_id):
        dec = cipher_holder.get('dec')
        row = read("SELECT encrypted FROM credentials WHERE user_id=? AND provider='openrouter'", (user_id,), True)
        if not row or not dec:
            raise HTTPException(400, 'ไม่พบคีย์ OpenRouter')
        return dec(row['encrypted'])

    app.state.studio_set_decrypt = lambda fn: cipher_holder.__setitem__('dec', fn)

    @app.post('/api/studio/projects/{pid}/ai-clip/refresh')
    async def refresh_ai_clip(pid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        if p['status'] != 'clip_running' or not p['video_job_id']:
            return {'project': project_out(p), 'credits': credits_of(u['id'])}
        job = read('SELECT * FROM video_jobs WHERE id=? AND user_id=?', (p['video_job_id'], u['id']), True)
        from starlette.concurrency import run_in_threadpool
        service = mock_video if mock_video.is_mock_job(job['operation_name']) else openrouter
        try:
            key = 'mock' if service is mock_video else (os.getenv('PLATFORM_OPENROUTER_API_KEY', '').strip()
                                                        if p['engine_mode'] == 'ai_platform' else _own_key(u['id']))
            state, uri = await run_in_threadpool(service.poll_video, key, job['operation_name'])
            if state == 'running':
                return {'project': project_out(p), 'credits': credits_of(u['id'])}
            target = data_dir / 'videos' / str(u['id']) / f"{job['id']}.mp4"
            await run_in_threadpool(service.download_video, key, uri, target)
        except Exception as e:
            err = str(e)[:280] or 'สร้างคลิปไม่สำเร็จ'
            if any(w in err for w in ('เชื่อมต่อ', 'ขัดข้อง', 'timeout', 'Timeout')):
                return {'project': project_out(p), 'credits': credits_of(u['id']), 'notice': err + ' — จะลองตรวจอีกครั้ง'}
            with connect() as c:
                c.execute("UPDATE video_jobs SET status='failed', error_message=?, updated_at=? WHERE id=?", (err, now(), job['id']))
            set_status(pid, 'clip_failed', error=err)
            refund(u['id'], p, err)
            return {'project': project_out(own_project(u['id'], pid)), 'credits': credits_of(u['id'])}
        with connect() as c:
            c.execute("UPDATE video_jobs SET status='ready', file_name=?, updated_at=? WHERE id=?",
                      (target.relative_to(data_dir).as_posix(), now(), job['id']))
        set_status(pid, 'clip_ready', ready_job_id=job['id'])
        return {'project': project_out(own_project(u['id'], pid)), 'credits': credits_of(u['id'])}

    @app.post('/api/studio/projects/{pid}/save')
    def save_project(pid: int, req: Request, target: str = 'library', x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        if target not in ('library', 'tiktok_queue'):
            raise HTTPException(400, 'ปลายทางไม่ถูกต้อง')
        out = project_out(p)
        if not (out['preview_url'] or out['clip_url']):
            raise HTTPException(409, 'ยังไม่มีคลิป — สร้างคลิปพรีวิวหรือคลิป AI ก่อน')
        if target == 'library':
            set_status(pid, 'saved')
            return {'project': project_out(own_project(u['id'], pid)), 'message': 'บันทึกโปรเจกต์ลงคลังแล้ว'}
        if not p['draft_id']:
            raise HTTPException(409, 'โปรเจกต์นี้ไม่มีบทที่ผูกไว้')
        video_url = out['clip_url'] or out['preview_url']
        with connect() as c:
            dup = c.execute("SELECT id FROM publishing_queue WHERE user_id=? AND draft_id=? AND platform='tiktok' AND status!='cancelled'",
                            (u['id'], p['draft_id'])).fetchone()
            if not dup:
                c.execute('''INSERT INTO publishing_queue(user_id,draft_id,platform,video_url,status,created_at,caption)
                             VALUES(?,?,'tiktok',?,'ready_manual',?,?)''', (u['id'], p['draft_id'], video_url, now(), p['caption'][:1000]))
        set_status(pid, 'queued_tiktok')
        return {'project': project_out(own_project(u['id'], pid)),
                'message': 'เพิ่มเข้าคิว TikTok แล้ว (โพสต์เอง: ดาวน์โหลดคลิป + คัดลอกแคปชั่น แล้วอัปโหลดที่ tiktok.com/upload)'}

    @app.delete('/api/studio/projects/{pid}')
    def delete_project(pid: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        p = own_project(u['id'], pid)
        if p['status'] == 'clip_running':
            raise HTTPException(409, 'กำลังสร้างคลิปอยู่ ลบไม่ได้')
        with connect() as c:
            if p['draft_id']:
                # Do not leave queue items pointing at a deleted project's clip.
                c.execute("UPDATE publishing_queue SET status='cancelled' WHERE user_id=? AND draft_id=? AND status IN ('needs_review','ready_manual')",
                          (u['id'], p['draft_id']))
            c.execute('DELETE FROM studio_projects WHERE id=? AND user_id=?', (pid, u['id']))
        for f in (data_dir / 'videos' / str(u['id'])).glob(f'studio_{pid}.*'):
            f.unlink(missing_ok=True)
        return {'ok': True}

    @app.get('/api/studio/credits')
    def credit_history(req: Request):
        u = require_user(req)
        return {'credits': credits_of(u['id']),
                'ledger': read('SELECT delta,reason,project_id,created_at FROM credit_ledger WHERE user_id=? ORDER BY id DESC LIMIT 30', (u['id'],))}

    @app.get('/api/studio/image')
    def image_proxy(req: Request, url: str):
        """Same-origin copy of Shopee CDN images so the browser can record the canvas preview."""
        require_user(req)
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        if parts.scheme != 'https' or (parts.hostname or '') not in IMAGE_PROXY_HOSTS or parts.port not in (None, 443):
            raise HTTPException(400, 'ไม่อนุญาตโดเมนรูปนี้')
        try:
            r = requests.get(url, timeout=10, stream=True, allow_redirects=False)
            ctype = r.headers.get('content-type', '').split(';')[0]
            if r.status_code != 200 or ctype not in ('image/jpeg', 'image/png', 'image/webp'):
                raise HTTPException(502, 'ดึงรูปไม่สำเร็จ')
            body = r.raw.read(5 * 1024 * 1024 + 1, decode_content=True)
        except requests.RequestException:
            raise HTTPException(502, 'ดึงรูปไม่สำเร็จ')
        if len(body) > 5 * 1024 * 1024:
            raise HTTPException(413, 'รูปใหญ่เกินไป')
        return Response(body, media_type=ctype, headers={'Cache-Control': 'private, max-age=3600'})
