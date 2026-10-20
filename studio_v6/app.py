"""Affiliate Auto Studio: local-first MVP. No social network autoposting without approval."""
from __future__ import annotations
import json
import base64
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve()
MEDIA = DATA / 'media'
MEDIA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'studio.db'
app = FastAPI(title='Affiliate Auto Studio — PC V6', version='0.6.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
LOCK = threading.Lock()


def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    return c


def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL, price TEXT NOT NULL DEFAULT '',
          features TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '',
          tiktok_link TEXT NOT NULL DEFAULT '', shopee_link TEXT NOT NULL DEFAULT '',
          reference_filename TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drafts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
          hook TEXT NOT NULL, voiceover TEXT NOT NULL, caption TEXT NOT NULL,
          onscreen TEXT NOT NULL, video_prompt TEXT NOT NULL,
          source_filename TEXT NOT NULL DEFAULT '', voice_filename TEXT NOT NULL DEFAULT '',
          video_filename TEXT NOT NULL DEFAULT '', google_interaction_id TEXT NOT NULL DEFAULT '',
          state TEXT NOT NULL DEFAULT 'script_ready', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS queue(
          id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INTEGER NOT NULL REFERENCES drafts(id),
          platform TEXT NOT NULL CHECK(platform IN ('tiktok','shopee')),
          status TEXT NOT NULL DEFAULT 'pending_review',
          scheduled_at TEXT NOT NULL DEFAULT '', post_url TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, UNIQUE(draft_id, platform)
        );
        ''')


init_db()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def rows(sql, params=()):
    with connect() as db:
        return [dict(x) for x in db.execute(sql, params).fetchall()]


def one(sql, params=()):
    rr = rows(sql, params)
    if not rr:
        raise HTTPException(404, 'ไม่พบข้อมูล')
    return rr[0]


def safe_name(prefix, extension):
    return f'{prefix}_{secrets.token_hex(12)}{extension}'


async def save_upload(file: UploadFile, kind: str):
    allowed = {'image': {'.jpg', '.jpeg', '.png', '.webp'}, 'video': {'.mp4', '.mov', '.webm'}}[kind]
    ext = Path(file.filename or '').suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f'ไฟล์ {kind} ไม่รองรับ (รองรับ {", ".join(sorted(allowed))})')
    max_bytes = 12 * 1024 * 1024 if kind == 'image' else 120 * 1024 * 1024
    name = safe_name(kind, ext)
    output = MEDIA / name
    total = 0
    try:
        with open(output, 'wb') as fp:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, 'ไฟล์ใหญ่เกินขนาดที่กำหนด')
                fp.write(chunk)
        if kind == 'image':
            with Image.open(output) as img:
                img.verify()
        else:
            if shutil.which('ffprobe'):
                check = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_type', '-of', 'default=noprint_wrappers=1', str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
                if check.returncode != 0 or b'video' not in check.stdout:
                    raise HTTPException(400, 'ไฟล์วิดีโอเสียหรือไม่ใช่วิดีโอ')
        return name
    except Exception:
        output.unlink(missing_ok=True)
        raise


def asset(filename):
    if not re.fullmatch(r'[a-z]+_[0-9a-f]{24}\.(?:mp4|mov|webm|mp3|jpg|jpeg|png|webp)', filename):
        raise HTTPException(404, 'ไม่พบไฟล์')
    p = MEDIA / filename
    if not p.is_file():
        raise HTTPException(404, 'ไม่พบไฟล์')
    return p


@app.get('/')
def home():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/status')
def status():
    return {
        'mode': 'self-hosted + Google Flow manual handoff + optional official Veo API', 'text_ai': bool(os.getenv('OPENAI_API_KEY')),
        'flow_handoff': True, 'google_omni_api': bool(os.getenv('GEMINI_API_KEY')), 'google_veo_api': bool(os.getenv('GEMINI_API_KEY')),
        'ffmpeg': bool(shutil.which('ffmpeg')),
        'tiktok_posting': 'not_connected_requires_oauth_approved_scope',
        'shopee_video_posting': 'manual_only_unverified_official_api',
        'basket_linking': 'manual_in_platform',
        'counts': {
            'products': rows('SELECT COUNT(*) n FROM products')[0]['n'],
            'radar': rows('SELECT COUNT(*) n FROM radar_candidates')[0]['n'],
            'drafts': rows('SELECT COUNT(*) n FROM drafts')[0]['n'],
            'videos': rows("SELECT COUNT(*) n FROM drafts WHERE video_filename <> ''")[0]['n'],
            'queue': rows("SELECT COUNT(*) n FROM queue WHERE status <> 'posted'")[0]['n'],
        }
    }


class ProductNew(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    price: str = Field(default='', max_length=80)
    features: str = Field(default='', max_length=1000)
    audience: str = Field(default='', max_length=300)
    tiktok_link: str = Field(default='', max_length=800)
    shopee_link: str = Field(default='', max_length=800)


@app.get('/api/products')
def products():
    return rows('SELECT * FROM products ORDER BY id DESC')


@app.post('/api/products')
def add_product(p: ProductNew):
    for url in (p.tiktok_link, p.shopee_link):
        if url and urlparse(url).scheme not in ('http', 'https'):
            raise HTTPException(400, 'ลิงก์สินค้าไม่ถูกต้อง')
    with connect() as db:
        c = db.execute('INSERT INTO products(title,price,features,audience,tiktok_link,shopee_link,created_at) VALUES (?,?,?,?,?,?,?)',
            (p.title.strip(), p.price.strip(), p.features.strip(), p.audience.strip(), p.tiktok_link.strip(), p.shopee_link.strip(), stamp()))
        item_id = c.lastrowid
    return one('SELECT * FROM products WHERE id=?', (item_id,))


@app.post('/api/products/{pid}/reference')
async def add_reference(pid: int, file: UploadFile = File(...)):
    p = one('SELECT * FROM products WHERE id=?', (pid,))
    filename = await save_upload(file, 'image')
    with connect() as db:
        db.execute('UPDATE products SET reference_filename=? WHERE id=?', (filename, pid))
    # Clean old reference only if not referenced elsewhere (one asset per product)
    if p['reference_filename']:
        (MEDIA / p['reference_filename']).unlink(missing_ok=True)
    return {'filename': filename}


@app.get('/api/assets/{filename}')
def get_asset(filename: str):
    return FileResponse(asset(filename))


BASE_BANNED = 'No listing screenshots, no static advertising frame, no uploaded product image as thumbnail, first frame, background or overlay, no face reveal, no logos invented, no false claims.'


def local_script(p):
    features = p['features'].strip().splitlines()[0][:45] if p['features'].strip() else 'เห็นวิธีใช้งานชัด ๆ'
    hook = f'ของชิ้นนี้ใช้งานยังไง? มาดู!' if len(p['title']) > 30 else f'{p["title"]} ใช้จริงเป็นยังไง?'
    voice = f'ลอง {p["title"][:26]} กันค่ะ {features} ดูรายละเอียดสินค้าในตะกร้าได้เลย'
    caption = f'ลองดู {p["title"]} แบบใกล้ ๆ 🔎 ดูรายละเอียดสินค้าก่อนตัดสินใจ #รีวิวสินค้า #ของใช้ดีบอกต่อ #ป้ายยา'
    return {'hook': hook, 'voiceover': voice, 'caption': caption[:240],
            'onscreen': f'{p["title"][:35]} • ดูก่อนตัดสินใจ',
            'video_prompt': (f'8-second vertical 9:16 authentic Thai UGC product review using Veo API (or adapt to Google Flow manually). First-person POV camera, only natural hands visible. '
                             f'Show a real-looking person physically picking up, using and demonstrating a product described as {p["title"]}. '
                             f'Product facts: {p["features"] or "no verified specs"}. Natural daylight, everyday home, handheld movements. '
                             'Scene 0–2s hands pick up item, 2–6s demonstrate actual use, 6–8s show result without exaggerated claims. '
                             f'Thai voiceover exactly: \"{voice}\". Spoken Thai when supported. Treat uploaded image as <IMAGE_REF_0> subject reference only, not a first frame. {BASE_BANNED}')}


def ai_script(p):
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        return local_script(p), 'template'
    system = ('Return strictly JSON object with keys hook, voiceover, caption, onscreen, video_prompt. '
        'All spoken/caption text in Thai; video_prompt in English. 8 seconds, vertical 9:16, POV hands using real product. '
        'Only repeat verified product specs provided by the user; never invent benefits, prices, reviews, outcomes or performance. '
        'Write a short voiceover suitable for 10 seconds (25-35 Thai spoken syllables preferably). '
        'Avoid prohibited content. Video prompt must explicitly forbid using reference/listing image as opening, thumb, background or overlay.')
    try:
        r = requests.post('https://api.openai.com/v1/chat/completions', timeout=55,
            headers={'Authorization': f'Bearer {key}'}, json={
                'model': os.getenv('OPENAI_TEXT_MODEL', 'gpt-4.1-mini'),
                'temperature': 0.65, 'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': system},
                             {'role': 'user', 'content': json.dumps({k:p[k] for k in ('title','price','features','audience')}, ensure_ascii=False)}]})
        r.raise_for_status()
        out = json.loads(r.json()['choices'][0]['message']['content'])
        for x in ('hook','voiceover','caption','onscreen','video_prompt'):
            if not isinstance(out.get(x), str) or not out[x].strip():
                raise ValueError(f'missing {x}')
        out['video_prompt'] += '\n' + BASE_BANNED
        return {k: out[k][:3000] for k in ('hook','voiceover','caption','onscreen','video_prompt')}, 'openai'
    except (requests.RequestException, KeyError, IndexError, ValueError, json.JSONDecodeError):
        return local_script(p), 'template_fallback'


class DraftNew(BaseModel):
    product_id: int
    platforms: list[str] = Field(default_factory=lambda: ['tiktok', 'shopee'])


@app.post('/api/drafts')
def create_draft(body: DraftNew):
    p = one('SELECT * FROM products WHERE id=?', (body.product_id,))
    platforms = set(body.platforms)
    if not platforms or not platforms.issubset({'tiktok', 'shopee'}):
        raise HTTPException(400, 'แพลตฟอร์มไม่ถูกต้อง')
    fields, how = ai_script(p)
    with connect() as db:
        c = db.execute('INSERT INTO drafts(product_id,hook,voiceover,caption,onscreen,video_prompt,created_at) VALUES (?,?,?,?,?,?,?)',
            (p['id'], fields['hook'], fields['voiceover'], fields['caption'], fields['onscreen'], fields['video_prompt'], stamp()))
        did = c.lastrowid
        for platform in sorted(platforms):
            db.execute('INSERT INTO queue(draft_id,platform,created_at) VALUES (?,?,?)', (did, platform, stamp()))
    return {'draft': one('SELECT * FROM drafts WHERE id=?', (did,)), 'method': how}


@app.get('/api/drafts')
def drafts():
    return rows('''SELECT d.*,p.title product_title,p.reference_filename reference_filename,
        (SELECT GROUP_CONCAT(platform,',') FROM queue q WHERE q.draft_id=d.id) platforms
        FROM drafts d JOIN products p ON d.product_id=p.id ORDER BY d.id DESC''')


class DraftEdit(BaseModel):
    hook: str = Field(min_length=1, max_length=200)
    voiceover: str = Field(min_length=1, max_length=2000)
    caption: str = Field(min_length=1, max_length=2200)
    onscreen: str = Field(min_length=1, max_length=200)
    video_prompt: str = Field(min_length=10, max_length=4000)


@app.patch('/api/drafts/{did}')
def edit_draft(did: int, body: DraftEdit):
    one('SELECT * FROM drafts WHERE id=?', (did,))
    with connect() as db:
        db.execute('''UPDATE drafts SET hook=?, voiceover=?, caption=?, onscreen=?, video_prompt=? WHERE id=?''',
            (body.hook, body.voiceover, body.caption, body.onscreen, body.video_prompt, did))
    return one('SELECT * FROM drafts WHERE id=?', (did,))


@app.post('/api/drafts/{did}/import_flow')
async def import_flow_video(did: int, file: UploadFile = File(...)):
    """Bring an MP4 generated in Google Flow back into the dashboard."""
    d = one('SELECT * FROM drafts WHERE id=?', (did,))
    filename = await save_upload(file, 'video')
    with connect() as db:
        db.execute("UPDATE drafts SET video_filename=?,state='video_ready' WHERE id=?",(filename,did))
        db.execute("UPDATE queue SET status='ready_manual' WHERE draft_id=? AND status='pending_review'",(did,))
    if d['video_filename']:
        (MEDIA/d['video_filename']).unlink(missing_ok=True)
    return {'video_filename':filename,'status':'video_ready'}


@app.post('/api/drafts/{did}/footage')
async def upload_footage(did: int, file: UploadFile = File(...)):
    one('SELECT * FROM drafts WHERE id=?', (did,))
    fn = await save_upload(file, 'video')
    with connect() as db:
        db.execute('UPDATE drafts SET source_filename=? WHERE id=?', (fn, did))
    return {'source_filename': fn}


def font_path():
    # Works on Linux/macOS/Windows; fallback for local machines.
    for x in [os.getenv('THAI_FONT', ''), '/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf',
              '/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf',
              '/System/Library/Fonts/Supplemental/Thonburi.ttc',
              'C:/Windows/Fonts/tahoma.ttf']:
        if x and Path(x).is_file(): return x
    try:
        result = subprocess.check_output(['fc-match','-f','%{file}','Noto Sans Thai'], timeout=5).decode()
        if Path(result).is_file(): return result
    except Exception:
        pass
    return None


def wrap_text(draw, text, font, max_width):
    result=[]; line=''
    # Thai doesn't have spaces between all words; wrap by character width.
    for char in text.strip():
        proposed=line+char
        if line and draw.textbbox((0,0),proposed,font=font)[2] > max_width:
            result.append(line); line=char
        else: line=proposed
    if line: result.append(line)
    return result[:3]


def overlay_img(d, png):
    layer=Image.new('RGBA', (720,1280), (0,0,0,0)); paint=ImageDraw.Draw(layer)
    fp=font_path()
    f1=ImageFont.truetype(fp, 43) if fp else ImageFont.load_default()
    f2=ImageFont.truetype(fp, 30) if fp else ImageFont.load_default()
    paint.rounded_rectangle((35,78,685,242), radius=25, fill=(8,13,31,199))
    paint.rounded_rectangle((35,1075,685,1215), radius=25, fill=(8,13,31,205))
    paint.rounded_rectangle((42,85,115,92), radius=3, fill=(56,218,181,255))
    paint.text((55,101), 'POV REVIEW', font=f2, fill=(76,240,202,255))
    for i,line in enumerate(wrap_text(paint,d['hook'],f1,600)[:2]):
        paint.text((54,145+i*51),line,font=f1,fill=(255,255,255,255))
    paint.text((55,1097),'ดูก่อนตัดสินใจ', font=f1, fill=(255,255,255,255))
    paint.text((55,1160),'สินค้าจริง • รายละเอียดในแอป',font=f2,fill=(190,204,221,255))
    layer.save(png)


def render_video(d):
    if not shutil.which('ffmpeg'):
        raise HTTPException(412, 'ต้องติดตั้ง FFmpeg ก่อน')
    if not d['source_filename']:
        raise HTTPException(412, 'กรุณาอัปโหลดวิดีโอ POV ที่ถ่ายเองก่อน (ภาพหน้าร้านไม่ใช้เป็นคลิป)')
    source=asset(d['source_filename'])
    outfile=safe_name('video','.mp4')
    with tempfile.TemporaryDirectory() as td:
        over=Path(td)/'overlay.png'; overlay_img(d,over)
        args=['ffmpeg','-hide_banner','-loglevel','error','-y','-stream_loop','-1','-i',str(source),'-loop','1','-i',str(over)]
        voice=d['voice_filename']
        if voice: args.extend(['-i',str(asset(voice))])
        args.extend(['-filter_complex','[0:v]fps=24,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[v];[v][1:v]overlay=0:0:shortest=1[vout]',
            '-map','[vout]'])
        if voice:
            args.extend(['-map','2:a:0','-c:a','aac','-b:a','128k'])
        else:
            args.extend(['-map','0:a?','-c:a','aac','-b:a','128k'])
        args.extend(['-t','10','-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart',str(MEDIA/outfile)])
        proc = subprocess.run(args, timeout=160, capture_output=True, text=True)
        if proc.returncode != 0:
            (MEDIA/outfile).unlink(missing_ok=True)
            raise HTTPException(500, 'FFmpeg สร้างวิดีโอไม่สำเร็จ: ' + proc.stderr[-450:])
    return outfile


@app.post('/api/drafts/{did}/render')
def render(did: int):
    d=one('SELECT * FROM drafts WHERE id=?',(did,))
    name=render_video(d)
    with connect() as db:
        db.execute("UPDATE drafts SET video_filename=?, state='video_ready' WHERE id=?",(name,did))
        db.execute("UPDATE queue SET status='ready_manual' WHERE draft_id=? AND status='pending_review'",(did,))
    return {'video_filename':name}


@app.post('/api/drafts/{did}/voice')
def create_voice(did: int):
    d=one('SELECT * FROM drafts WHERE id=?',(did,))
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:
        raise HTTPException(412,'ต้องใส่ OPENAI_API_KEY ในไฟล์ .env ก่อน')
    r=requests.post('https://api.openai.com/v1/audio/speech', timeout=85,
        headers={'Authorization':f'Bearer {key}'},json={'model':'gpt-4o-mini-tts','voice':'coral',
        'input':d['voiceover'][:1600],'instructions':'Speak naturally in Thai, clear friendly product demonstration, moderately brisk pace',
        'response_format':'mp3'})
    if not r.ok: raise HTTPException(502,'บริการเสียงตอบกลับผิดพลาด: '+r.text[:220])
    name=safe_name('voice','.mp3')
    (MEDIA/name).write_bytes(r.content)
    with connect() as db: db.execute('UPDATE drafts SET voice_filename=? WHERE id=?',(name,did))
    return {'voice_filename':name}


@app.get('/api/flow')
def flow_info():
    return {
      'url': 'https://labs.google/fx/tools/flow',
      'mode': 'handoff_only',
      'manual_steps': ['คัดลอกพรอมต์','เปิด Google Flow','อัปโหลดภาพเป็นภาพอ้างอิง','สร้างคลิปและดาวน์โหลด MP4','อัปโหลด MP4 กลับเข้าระบบ'],
      'models': [{'name':'Veo 3.1 via Gemini API','seconds':8}],
      'direct_flow_api': False,
      'optional_gemini_api': bool(os.getenv('GEMINI_API_KEY')),
    }


@app.post('/api/drafts/{did}/omni')
def generate_with_google_veo(did: int):
    """Manual one-click Veo generation via official Gemini API (billable), not Flow site."""
    d = one("SELECT d.*,p.reference_filename FROM drafts d JOIN products p ON p.id=d.product_id WHERE d.id=?",(did,))
    if not os.getenv('GEMINI_API_KEY', '').strip():
        raise HTTPException(412,'ยังไม่ตั้ง GEMINI_API_KEY')
    if d['video_filename']:
        raise HTTPException(409,'มีวิดีโอแล้ว จะไม่สั่งสร้างซ้ำ')
    if not LOCK.acquire(blocking=False):
        raise HTTPException(429,'กำลังสร้างคลิปอื่นอยู่')
    from video_veo import generate_veo
    filename=safe_name('video','.mp4')
    output=MEDIA/filename
    try:
        try:
            ref=MEDIA/d['reference_filename'] if d['reference_filename'] else None
            op_id=generate_veo(d['video_prompt'],output,reference=ref)
        except Exception as e:
            output.unlink(missing_ok=True)
            raise HTTPException(502,'Veo API สร้างคลิปไม่สำเร็จ: '+str(e)[:230])
        with connect() as db:
            db.execute("UPDATE drafts SET video_filename=?,google_interaction_id=?,state='video_ready' WHERE id=?",
                       (filename,op_id[:300],did))
            db.execute("UPDATE queue SET status='ready_manual' WHERE draft_id=? AND status='pending_review'",(did,))
        return {'video_filename':filename,'status':'video_ready','engine':'veo_gemini_api_not_flow_site'}
    finally:
        LOCK.release()

@app.get('/api/queue')
def get_queue():
    return rows('''SELECT q.*,d.caption,d.video_filename,p.title product_title,
       CASE WHEN q.platform='tiktok' THEN p.tiktok_link ELSE p.shopee_link END product_link
       FROM queue q JOIN drafts d ON q.draft_id=d.id JOIN products p ON d.product_id=p.id
       ORDER BY CASE q.status WHEN 'pending_review' THEN 1 WHEN 'ready_manual' THEN 2 ELSE 3 END, q.id DESC''')


class QueueEdit(BaseModel):
    status: str
    scheduled_at: str = ''
    post_url: str = ''


@app.patch('/api/queue/{qid}')
def update_queue(qid: int, q: QueueEdit):
    old=one('SELECT * FROM queue WHERE id=?',(qid,))
    if q.status not in ('pending_review','ready_manual','posted'):
        raise HTTPException(400,'สถานะไม่ถูกต้อง')
    if q.status=='posted':
        if not q.post_url or urlparse(q.post_url).scheme not in ('http','https'):
            raise HTTPException(400,'กรุณาใส่ลิงก์โพสต์จริงก่อนเลือกโพสต์แล้ว')
    with connect() as db:
        db.execute('UPDATE queue SET status=?,scheduled_at=?,post_url=? WHERE id=?',
           (q.status,q.scheduled_at[:60],q.post_url[:1000],qid))
    return one('SELECT * FROM queue WHERE id=?',(qid,))


@app.get('/health')
def health():
    return {'ok':True}


# Product Radar routes and opt-in background polling
from radar import mount_radar
mount_radar(app, connect, stamp, local_script)

# External discovery for products; independent of TikTok / Shopee APIs.
from external_radar import mount_external
mount_external(app, connect, stamp, local_script)

# V4: workflow controller and official TikTok adapter (never attaches affiliate basket)
from autopilot import mount_autopilot
mount_autopilot(app,connect,stamp,local_script,MEDIA,safe_name)
from tiktok_publish import mount_tiktok
mount_tiktok(app,connect,stamp,MEDIA,DATA)

# Optional HTTP Basic for self-hosting. Always use HTTPS and set these for public hosting.
import base64 as _b64, hmac as _hmac
from fastapi.responses import Response as _Response
@app.middleware('http')
async def studio_auth(request,call_next):
    expected_user=os.getenv('STUDIO_USERNAME','')
    expected_pass=os.getenv('STUDIO_PASSWORD','')
    if expected_user and expected_pass and request.url.path not in ('/health','/api/tiktok/auth/callback'):
        auth=request.headers.get('authorization','')
        try:
            scheme,encoded=auth.split(' ',1)
            decoded=_b64.b64decode(encoded,validate=True).decode('utf-8')
            user,pw=decoded.split(':',1)
            good=(scheme.lower()=='basic' and _hmac.compare_digest(user,expected_user)
                  and _hmac.compare_digest(pw,expected_pass))
        except (ValueError,UnicodeError):good=False
        if not good:return _Response('Authorization required',status_code=401,
                headers={'WWW-Authenticate':'Basic realm="Affiliate Auto Studio"'})
    return await call_next(request)


# PC setup: API keys are stored locally in .env; never sent to the browser after saving.
from fastapi import Request
from dotenv import set_key

class SetupKeys(BaseModel):
    gemini_api_key: str = Field(default='',max_length=500)
    brave_search_api_key: str = Field(default='',max_length=500)
    openai_api_key: str = Field(default='',max_length=500)

def _local_request(request:Request):
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'ตั้งค่าคีย์จากเครื่องคอมพิวเตอร์ที่รันโปรแกรมเท่านั้น')

@app.get('/api/setup')
def setup_status():
    return {'gemini_api_key':bool(os.getenv('GEMINI_API_KEY')),
            'brave_search_api_key':bool(os.getenv('BRAVE_SEARCH_API_KEY')),
            'openai_api_key':bool(os.getenv('OPENAI_API_KEY')),
            'tiktok_developer':bool(os.getenv('TIKTOK_CLIENT_KEY') and os.getenv('TIKTOK_CLIENT_SECRET')),
            'notice':'Google Flow เว็บไซต์ไม่ได้เชื่อมกับ Gemini API key โดยอัตโนมัติ'}

@app.post('/api/setup/keys')
def setup_keys(data:SetupKeys,request:Request):
    _local_request(request)
    envfile=ROOT/'.env'
    envfile.touch(exist_ok=True)
    changed=[]
    for field,name in [('gemini_api_key','GEMINI_API_KEY'),('brave_search_api_key','BRAVE_SEARCH_API_KEY'),('openai_api_key','OPENAI_API_KEY')]:
        val=getattr(data,field).strip()
        if not val:continue
        if any(c in val for c in '\n\r\x00'):
            raise HTTPException(400,'รูปแบบ API key ไม่ถูกต้อง')
        set_key(str(envfile),name,val,quote_mode='always')
        os.environ[name]=val
        changed.append(field)
    return {'saved':changed,'notice':'คีย์ถูกเก็บใน .env บนเครื่องนี้ ไม่ต้องส่งให้ผู้ช่วย'}
