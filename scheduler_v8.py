"""Auto-Post scheduler: publish a studio clip / product to connected Facebook, Instagram and LINE OA at a set time.

* Facebook: when the post time is 15 min – 29 days ahead, the post is handed to Facebook's own scheduler
  immediately (published=false + scheduled_publish_time) so it goes out even if this server is asleep.
* Instagram / LINE (and Facebook posts due sooner): published by this server's worker loop (every 20 s),
  or by POST /api/scheduler/tick from an external cron (for serverless hosting).
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from integrations import line_oa, meta

FB_NATIVE_MIN = timedelta(minutes=15)
FB_NATIVE_MAX = timedelta(days=29)
MAX_ATTEMPTS = 3


class ScheduleIn(BaseModel):
    product_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    channel_ids: list[int] = Field(min_length=1, max_length=20)
    caption: str = Field(default='', max_length=2000)
    scheduled_at: str | None = Field(default=None, max_length=40)   # ISO-8601; empty = now
    use_video: bool = True
    line_mode: str = Field(default='broadcast', pattern=r'^(push|broadcast)$')
    confirm_broadcast: bool = False


def parse_when(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(400, 'รูปแบบวันเวลาไม่ถูกต้อง')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))  # naive input = Asia/Bangkok
    return dt.astimezone(timezone.utc)


def register(app: FastAPI, *, connect, read, require_user, mutation, now, data_dir: Path, decrypt, base_url_for):
    public_dir = data_dir / 'media' / 'public'
    public_dir.mkdir(parents=True, exist_ok=True)

    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS scheduled_posts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          project_id INTEGER, caption TEXT NOT NULL DEFAULT '',
          media_file TEXT NOT NULL DEFAULT '', public_video TEXT NOT NULL DEFAULT '',
          line_mode TEXT NOT NULL DEFAULT 'broadcast',
          scheduled_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'scheduled'
            CHECK(status IN ('scheduled','posting','posted','partial','failed','cancelled')),
          channels_json TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          base_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS scheduled_due ON scheduled_posts(status, scheduled_at);
        CREATE INDEX IF NOT EXISTS scheduled_owner ON scheduled_posts(user_id, id DESC);
        ''')

    def iso(dt):
        return dt.astimezone(timezone.utc).isoformat(timespec='seconds')

    def project_video(user_id, project_id):
        """Best available clip of a studio project: AI clip (mp4) first, else the recorded preview."""
        if not project_id:
            return None
        p = read('SELECT * FROM studio_projects WHERE id=? AND user_id=?', (project_id, user_id), True)
        if not p:
            raise HTTPException(404, 'ไม่พบโปรเจกต์')
        job_id = p.get('ready_job_id')
        if not job_id and p.get('video_job_id'):
            j = read("SELECT id FROM video_jobs WHERE id=? AND status='ready'", (p['video_job_id'],), True)
            job_id = j and j['id']
        if job_id:
            f = data_dir / 'videos' / str(user_id) / f'{job_id}.mp4'
            if f.is_file():
                return f
        if p.get('preview_file'):
            f = data_dir / 'videos' / str(user_id) / p['preview_file']
            if f.is_file():
                return f
        return None

    def post_out(r):
        chans = json.loads(r['channels_json'])
        names = {c['id']: c for c in read(f"SELECT id,platform,account_name FROM connected_channels WHERE id IN ({','.join('?' * len(chans)) or 'NULL'})",
                                           tuple(int(k) for k in chans))} if chans else {}
        prod = read('SELECT title,image_url FROM products WHERE id=?', (r['product_id'],), True) or {}
        return {**{k: r[k] for k in ('id', 'product_id', 'project_id', 'caption', 'scheduled_at', 'status', 'attempts',
                                    'line_mode', 'created_at', 'updated_at')},
                'product_title': prod.get('title', ''), 'has_video': bool(r['media_file']),
                'channels': [{'channel_id': int(k), **v, 'platform': (names.get(int(k)) or {}).get('platform', '?'),
                              'account_name': (names.get(int(k)) or {}).get('account_name', '(ตัดการเชื่อมต่อแล้ว)')}
                             for k, v in chans.items()]}

    # ------------------------------------------------------------------ publishing core
    def publish_channel(post, ch, state, fb_native_ts=None):
        token = decrypt(ch['access_token_encrypted'])
        if not token:
            raise meta.MetaError('ช่องทางนี้ไม่มี token แล้ว — เชื่อมต่อใหม่')
        m = json.loads(ch.get('meta_json') or '{}')
        prod = read('SELECT * FROM products WHERE id=?', (post['product_id'],), True) or {}
        link = prod.get('offer_link') or prod.get('url') or ''
        img = prod.get('image_url') if (prod.get('image_url') or '').startswith('https://') else ''
        if not img and prod.get('image_file') and post['base_url'].startswith('https://'):
            img = f"{post['base_url']}/media/products/{prod['image_file']}"
        caption = post['caption'] or prod.get('title', '')
        video = data_dir / post['media_file'] if post['media_file'] else None
        if ch['platform'] == 'facebook':
            text = caption + (f'\n\n🛒 {link}' if link and link not in caption else '')
            if video and video.is_file():
                return meta.facebook_publish_video(ch['account_id'], token, str(video), text, fb_native_ts)
            return meta.facebook_publish_scheduled(ch['account_id'], token, caption, '' if link in caption else link, img, fb_native_ts)
        if ch['platform'] == 'instagram':
            via = m.get('via', 'instagram')
            if post['public_video'] and post['base_url'].startswith('https://'):
                return meta.instagram_publish_reel(ch['account_id'], token, caption, f"{post['base_url']}/media/public/{post['public_video']}", via)
            if not img:
                raise meta.MetaError('Instagram ต้องมีรูปหรือวิดีโอ MP4 จากลิงก์ https สาธารณะ (ตั้ง PUBLIC_BASE_URL เป็น https)')
            return meta.instagram_publish(ch['account_id'], token, caption, img, via)
        if ch['platform'] == 'line_oa':
            price = f"฿{prod['price']:,.0f}" if prod.get('price') else ''
            msg = line_oa.product_flex(prod.get('title', ''), price, img, link, caption.split('\n')[0][:200])
            if post['line_mode'] == 'broadcast':
                line_oa.broadcast(token, [msg])
                return {'post_id': '', 'kind': 'broadcast'}
            r = read('SELECT line_user_id FROM line_recipients WHERE channel_id=? ORDER BY last_seen DESC LIMIT 1', (ch['id'],), True)
            if not r:
                raise line_oa.LineError('ยังไม่มีผู้รับสำหรับ Push — แอดเพื่อน OA แล้วพิมพ์ข้อความ 1 ครั้ง')
            line_oa.push(token, r['line_user_id'], [msg])
            return {'post_id': '', 'kind': 'push'}
        raise meta.MetaError('ช่องทางนี้ยังไม่รองรับ Auto-Post')

    def log(user_id, ch, product_id, ok, ext, detail):
        with connect() as c:
            c.execute('''INSERT INTO publish_log(user_id, channel_id, platform, product_id, ok, external_id, detail, created_at)
                         VALUES (?,?,?,?,?,?,?,?)''', (user_id, ch['id'], ch['platform'], product_id, int(ok),
                                                       str(ext or '')[:120], ('[ตั้งเวลา] ' + str(detail))[:400], now()))

    def finalize(post_id, chans, attempts):
        states = [v['state'] for v in chans.values()]
        row = read('SELECT scheduled_at FROM scheduled_posts WHERE id=?', (post_id,), True)
        future = bool(row and row['scheduled_at'] > iso(datetime.now(timezone.utc)))
        if all(s in ('posted', 'fb_scheduled') for s in states):
            # Facebook-native posts wait on Facebook's side until their time.
            status = 'scheduled' if future and 'fb_scheduled' in states else 'posted'
        elif any(s == 'pending' for s in states):
            status = 'scheduled'
        elif any(s in ('posted', 'fb_scheduled') for s in states):
            status = 'partial'
        else:
            status = 'failed'
        with connect() as c:
            c.execute('UPDATE scheduled_posts SET channels_json=?, status=?, attempts=?, updated_at=? WHERE id=?',
                      (json.dumps(chans, ensure_ascii=False), status, attempts, now(), post_id))
        return status

    def run_post(post_id):
        """Publish every pending channel of one due post. Safe to call from the worker or the cron tick."""
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT * FROM scheduled_posts WHERE id=? AND status='scheduled' AND scheduled_at<=?",
                            (post_id, iso(datetime.now(timezone.utc)))).fetchone()
            if not row:
                return None
            c.execute("UPDATE scheduled_posts SET status='posting', updated_at=? WHERE id=?", (now(), post_id))
        post = dict(row)
        chans = json.loads(post['channels_json'])
        attempts = post['attempts'] + 1
        for key, st in chans.items():
            if st['state'] != 'pending':
                continue
            ch = read('SELECT * FROM connected_channels WHERE id=? AND user_id=?', (int(key), post['user_id']), True)
            if not ch:
                st.update(state='failed', error='ช่องทางถูกตัดการเชื่อมต่อแล้ว')
                continue
            try:
                r = publish_channel(post, ch, st)
                st.update(state='posted', external_id=r.get('post_id') or '', kind=r.get('kind'), error='', at=now())
                log(post['user_id'], ch, post['product_id'], True, r.get('post_id'), r.get('kind'))
            except (meta.MetaError, line_oa.LineError, HTTPException) as e:
                msg = getattr(e, 'detail', None) or str(e)
                transient = any(w in msg for w in ('เชื่อมต่อ', 'Timeout', 'ยังประมวลผล', 'HTTP 5', 'temporarily'))
                st.update(state='pending' if transient and attempts < MAX_ATTEMPTS else 'failed', error=msg[:300])
                log(post['user_id'], ch, post['product_id'], False, '', msg)
        status = finalize(post_id, chans, attempts)
        if status == 'scheduled':  # transient failure → retry in 2 minutes
            with connect() as c:
                c.execute('UPDATE scheduled_posts SET scheduled_at=? WHERE id=?',
                          (iso(datetime.now(timezone.utc) + timedelta(minutes=2)), post_id))
        return status

    def tick(user_id=None, limit=10):
        due = read(f"""SELECT id FROM scheduled_posts WHERE status='scheduled' AND scheduled_at<=? {'AND user_id=?' if user_id else ''}
                       ORDER BY scheduled_at LIMIT ?""", (iso(datetime.now(timezone.utc)),) + ((user_id,) if user_id else ()) + (limit,))
        done = []
        for r in due:
            st = run_post(r['id'])
            if st:
                done.append({'id': r['id'], 'status': st})
        # Recover rows stuck in 'posting' after a crash.
        cutoff = iso(datetime.now(timezone.utc) - timedelta(minutes=10))
        with connect() as c:
            c.execute("UPDATE scheduled_posts SET status='scheduled' WHERE status='posting' AND updated_at<?", (cutoff,))
        return done

    app.state.scheduler_tick = tick

    # ------------------------------------------------------------------ routes
    @app.post('/api/scheduled-posts')
    def create_post(body: ScheduleIn, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        prod = read('SELECT * FROM products WHERE id=? AND user_id=?', (body.product_id, u['id']), True)
        if not prod:
            raise HTTPException(404, 'ไม่พบสินค้าของบัญชีนี้')
        when = parse_when(body.scheduled_at)
        nowdt = datetime.now(timezone.utc)
        if when < nowdt - timedelta(minutes=2):
            raise HTTPException(400, 'เวลาที่ตั้งผ่านไปแล้ว — เลือกเวลาในอนาคต หรือเว้นว่างเพื่อโพสต์ทันที')
        if when > nowdt + timedelta(days=60):
            raise HTTPException(400, 'ตั้งเวลาล่วงหน้าได้ไม่เกิน 60 วัน')
        ids = list(dict.fromkeys(body.channel_ids))
        chans = read(f"SELECT * FROM connected_channels WHERE user_id=? AND id IN ({','.join('?' * len(ids))})", (u['id'], *ids))
        if len(chans) != len(ids):
            raise HTTPException(404, 'มีช่องทางที่ไม่พบในบัญชีของคุณ')
        bad = [c['account_name'] for c in chans if c['platform'] not in ('facebook', 'instagram', 'line_oa') or not c['access_token_encrypted']]
        if bad:
            raise HTTPException(400, 'ช่องทางเหล่านี้ยังไม่ได้เชื่อมต่อจริง: ' + ', '.join(bad))
        if any(c['platform'] == 'line_oa' for c in chans) and body.line_mode == 'broadcast' and not body.confirm_broadcast:
            raise HTTPException(400, 'LINE Broadcast ส่งหาเพื่อนทุกคนและนับโควต้า — ต้องยืนยันก่อน')
        media_file = public_video = ''
        if body.use_video and body.project_id:
            v = project_video(u['id'], body.project_id)
            if v:
                media_file = v.relative_to(data_dir).as_posix()
                if v.suffix == '.mp4' and any(c['platform'] == 'instagram' for c in chans):
                    public_video = secrets.token_urlsafe(18) + '.mp4'
                    shutil.copyfile(v, public_dir / public_video)
        elif body.project_id:
            project_video(u['id'], body.project_id)  # ownership check
        state = {str(c['id']): {'state': 'pending', 'error': '', 'external_id': ''} for c in chans}
        base = base_url_for(req)
        with connect() as c:
            cur = c.execute('''INSERT INTO scheduled_posts(user_id,product_id,project_id,caption,media_file,public_video,line_mode,
                               scheduled_at,status,channels_json,base_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'scheduled',?,?,?,?)''',
                            (u['id'], prod['id'], body.project_id, body.caption.strip()[:2000], media_file, public_video,
                             body.line_mode, iso(when), json.dumps(state), base, now(), now()))
            pid = cur.lastrowid
        post = read('SELECT * FROM scheduled_posts WHERE id=?', (pid,), True)
        # Hand Facebook posts to Facebook's native scheduler when allowed (reliable even if this server sleeps).
        lead = when - nowdt
        if FB_NATIVE_MIN <= lead <= FB_NATIVE_MAX:
            for ch in chans:
                if ch['platform'] != 'facebook':
                    continue
                st = state[str(ch['id'])]
                try:
                    r = publish_channel(post, ch, st, fb_native_ts=int(when.timestamp()))
                    st.update(state='fb_scheduled', external_id=r.get('post_id') or '', kind=r.get('kind'), error='')
                    log(u['id'], ch, prod['id'], True, r.get('post_id'), r.get('kind'))
                except (meta.MetaError, HTTPException) as e:
                    st.update(error='Facebook ไม่รับการตั้งเวลาล่วงหน้า จะโพสต์โดยระบบแทน: ' + (getattr(e, 'detail', None) or str(e))[:200])
            finalize(pid, state, 0)
        if lead <= timedelta(minutes=1):
            run_post(pid)
        out = post_out(read('SELECT * FROM scheduled_posts WHERE id=?', (pid,), True))
        when_local = when.astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')
        msg = 'โพสต์แล้ว' if out['status'] in ('posted', 'partial') and lead <= timedelta(minutes=1) else f'ตั้งเวลาโพสต์ {when_local} น. แล้ว'
        return {'post': out, 'message': msg}

    @app.get('/api/scheduled-posts')
    def list_posts(req: Request):
        u = require_user(req)
        try:
            tick(u['id'], 5)  # serverless-friendly: due posts also go out when the owner opens the page
        except Exception:
            pass
        return {'posts': [post_out(r) for r in read('SELECT * FROM scheduled_posts WHERE user_id=? ORDER BY scheduled_at DESC LIMIT 50', (u['id'],))],
                'worker': 'running' if getattr(app.state, 'scheduler_running', False) else 'cron'}

    @app.delete('/api/scheduled-posts/{post_id}')
    def cancel_post(post_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        r = read('SELECT * FROM scheduled_posts WHERE id=? AND user_id=?', (post_id, u['id']), True)
        if not r:
            raise HTTPException(404, 'ไม่พบโพสต์ที่ตั้งเวลา')
        if r['status'] not in ('scheduled', 'partial', 'failed') or r['status'] == 'posting':
            raise HTTPException(409, 'โพสต์นี้ส่งไปแล้วหรือกำลังส่ง ยกเลิกไม่ได้')
        chans = json.loads(r['channels_json'])
        notes = []
        for key, st in chans.items():
            if st['state'] == 'fb_scheduled' and st.get('external_id'):
                ch = read('SELECT * FROM connected_channels WHERE id=?', (int(key),), True)
                try:
                    if ch:
                        meta.delete_object(st['external_id'], decrypt(ch['access_token_encrypted']))
                    st['state'] = 'cancelled'
                except meta.MetaError as e:
                    notes.append(str(e))
            elif st['state'] == 'pending':
                st['state'] = 'cancelled'
        with connect() as c:
            c.execute("UPDATE scheduled_posts SET status='cancelled', channels_json=?, updated_at=? WHERE id=?",
                      (json.dumps(chans, ensure_ascii=False), now(), post_id))
        return {'ok': True, 'message': 'ยกเลิกแล้ว' + (' (' + '; '.join(notes) + ')' if notes else '')}

    @app.post('/api/scheduled-posts/{post_id}/retry')
    def retry_post(post_id: int, req: Request, x_csrf_token: str | None = Header(default=None)):
        u = mutation(req, x_csrf_token)
        r = read('SELECT * FROM scheduled_posts WHERE id=? AND user_id=?', (post_id, u['id']), True)
        if not r or r['status'] not in ('failed', 'partial'):
            raise HTTPException(409, 'ลองใหม่ได้เฉพาะโพสต์ที่ล้มเหลว')
        chans = json.loads(r['channels_json'])
        for st in chans.values():
            if st['state'] == 'failed':
                st.update(state='pending', error='')
        with connect() as c:
            c.execute("UPDATE scheduled_posts SET status='scheduled', attempts=0, channels_json=?, scheduled_at=?, updated_at=? WHERE id=?",
                      (json.dumps(chans), iso(datetime.now(timezone.utc)), now(), post_id))
        run_post(post_id)
        return {'post': post_out(read('SELECT * FROM scheduled_posts WHERE id=?', (post_id,), True))}

    @app.post('/api/scheduler/tick')
    def cron_tick(x_cron_secret: str | None = Header(default=None)):
        secret = os.getenv('SCHEDULER_SECRET', '')
        if not secret or not x_cron_secret or not secrets.compare_digest(secret, x_cron_secret):
            raise HTTPException(403, 'forbidden')
        return {'done': tick(None, 25)}

    @app.get('/media/public/{name}')
    def public_media(name: str):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_\-]{20,40}\.mp4', name):
            raise HTTPException(404, 'not found')
        path = public_dir / name
        if not path.is_file():
            raise HTTPException(404, 'not found')
        return FileResponse(path, media_type='video/mp4')

    async def worker():
        app.state.scheduler_running = True
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, tick)
            except Exception:
                pass
            await asyncio.sleep(int(os.getenv('SCHEDULER_INTERVAL', '20')))

    @app.on_event('startup')
    async def start_worker():
        if os.getenv('SCHEDULER_WORKER', '1') == '1':
            app.state.scheduler_task = asyncio.get_running_loop().create_task(worker())

    @app.on_event('shutdown')
    async def stop_worker():
        t = getattr(app.state, 'scheduler_task', None)
        if t:
            t.cancel()
