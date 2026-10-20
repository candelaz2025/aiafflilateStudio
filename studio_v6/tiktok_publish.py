"""TikTok official Login Kit and Content Posting API only.
Posting requires per-video approval and platform privacy selection.
This does not attach TikTok Shop affiliate baskets.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlencode, urlparse
import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

ENDPOINT='https://open.tiktokapis.com'
PUBLISH_LOCK=threading.Lock()

class Approval(BaseModel):
    privacy_level:str=Field(min_length=4,max_length=60)
    scheduled_at:str=Field(min_length=10,max_length=60)
    caption:str=Field(min_length=1,max_length=2200)
    acknowledge_no_basket:bool=False
    acknowledge_aigc_and_rights:bool=False


def mount_tiktok(app,connect,stamp,media_dir,data_dir):
    token_path=Path(data_dir)/'tiktok_authorization.json'
    state_path=Path(data_dir)/'tiktok_oauth_state.json'
    with connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS tiktok_publish(
          queue_id INTEGER PRIMARY KEY REFERENCES queue(id),
          approved_at TEXT NOT NULL, privacy_level TEXT NOT NULL,
          scheduled_utc TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'approved',
          publish_id TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
          posted_url TEXT NOT NULL DEFAULT '', processed_at TEXT NOT NULL DEFAULT '',
          approved_caption TEXT NOT NULL DEFAULT '',approved_sha256 TEXT NOT NULL DEFAULT '');''')
        existing={r[1] for r in db.execute('PRAGMA table_info(tiktok_publish)')}
        if 'approved_caption' not in existing:
            db.execute("ALTER TABLE tiktok_publish ADD COLUMN approved_caption TEXT NOT NULL DEFAULT ''")
        if 'approved_sha256' not in existing:
            db.execute("ALTER TABLE tiktok_publish ADD COLUMN approved_sha256 TEXT NOT NULL DEFAULT ''")

    def file_sha256(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''):
                h.update(block)
        return h.hexdigest()

    def creds():
        return (os.getenv('TIKTOK_CLIENT_KEY','').strip(),os.getenv('TIKTOK_CLIENT_SECRET','').strip(),
                os.getenv('TIKTOK_REDIRECT_URI','').strip())

    def read_json(path):
        try:return json.loads(path.read_text('utf-8'))
        except (ValueError,OSError):return {}

    def save_json(path,d):
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(d),encoding='utf-8')
        try:tmp.chmod(0o600)
        except OSError:pass
        tmp.replace(path)

    def tokens():
        d=read_json(token_path)
        if not d.get('access_token'):raise HTTPException(412,'กรุณาเชื่อม TikTok ด้วย Login Kit')
        if 'video.publish' not in d.get('scope','').split(','):
            raise HTTPException(412,'แอปยังไม่ได้รับอนุญาต video.publish')
        if dt.datetime.now(dt.timezone.utc).timestamp() > d.get('expires_at',0)-300:
            key,secret,uri=creds()
            if not all([key,secret,d.get('refresh_token')]):
                raise HTTPException(412,'Token หมดอายุและยังไม่สามารถรีเฟรชได้')
            try:
                res=requests.post(ENDPOINT+'/v2/oauth/token/',data={
                    'client_key':key,'client_secret':secret,'grant_type':'refresh_token',
                    'refresh_token':d['refresh_token']},timeout=18)
                res.raise_for_status(); new=res.json()
            except (requests.RequestException,ValueError) as exc:
                raise HTTPException(502,'รีเฟรช TikTok token ไม่สำเร็จ') from exc
            if not new.get('access_token'):raise HTTPException(502,'TikTok ไม่คืน token ใหม่')
            new['expires_at']=dt.datetime.now(dt.timezone.utc).timestamp()+int(new['expires_in'])
            save_json(token_path,new);d=new
        return d

    def request_api(path,body=None):
        try:
            r=requests.post(ENDPOINT+path,json=body or {},headers={
                'Authorization':'Bearer '+tokens()['access_token'],
                'Content-Type':'application/json; charset=UTF-8'},timeout=25)
            r.raise_for_status(); payload=r.json()
        except (requests.RequestException,ValueError) as exc:
            raise HTTPException(502,'TikTok API ไม่ตอบสนอง') from exc
        err=payload.get('error',{})
        if err.get('code') not in (None,'ok'):
            raise HTTPException(502,'TikTok: '+str(err.get('code','error'))[:120])
        return payload.get('data',{})

    @app.get('/api/tiktok/status')
    def status():
        key,sec,uri=creds()
        d=read_json(token_path)
        return {'app_configured':bool(key and sec and uri),'connected':bool(d.get('refresh_token')),
                'publish_scope':('video.publish' in d.get('scope','').split(',')),
                'username':'(ตรวจชื่อบัญชีที่หน้าอนุมัติก่อนโพสต์)',
                'posting':'requires_video_publish_approval_and_per_video_consent',
                'basket':'not_supported_by_Content_Posting_API'}

    @app.get('/api/tiktok/auth/start')
    def start_auth():
        key,secret,uri=creds()
        if not (key and secret and uri and urlparse(uri).scheme=='https'):
            raise HTTPException(412,'ตั้ง TIKTOK_CLIENT_KEY, CLIENT_SECRET และ HTTPS REDIRECT_URI ก่อน')
        nonce=secrets.token_urlsafe(32)
        save_json(state_path,{'state':nonce,'until':dt.datetime.now(dt.timezone.utc).timestamp()+600})
        query=urlencode({'client_key':key,'response_type':'code','scope':'video.publish',
            'redirect_uri':uri,'state':nonce})
        return RedirectResponse('https://www.tiktok.com/v2/auth/authorize/?'+query)

    @app.get('/api/tiktok/auth/callback')
    def finish_auth(code:str='',state:str='',error:str=''):
        saved=read_json(state_path)
        state_path.unlink(missing_ok=True)
        if (not saved or not state or not hmac.compare_digest(saved.get('state',''),state)
            or dt.datetime.now(dt.timezone.utc).timestamp()>saved.get('until',0)):
            raise HTTPException(400,'OAuth state ไม่ตรงหรือหมดอายุ')
        if error or not code:raise HTTPException(400,'TikTok ปฏิเสธสิทธิ์หรือไม่ได้ส่ง code')
        key,secret,uri=creds()
        try:
            r=requests.post(ENDPOINT+'/v2/oauth/token/',data={'client_key':key,'client_secret':secret,
                'grant_type':'authorization_code','code':code,'redirect_uri':uri},timeout=25)
            r.raise_for_status();data=r.json()
        except (requests.RequestException,ValueError) as exc:
            raise HTTPException(502,'ยืนยันบัญชี TikTok ไม่สำเร็จ') from exc
        if not data.get('refresh_token') or 'video.publish' not in data.get('scope','').split(','):
            raise HTTPException(412,'บัญชียังไม่ได้อนุมัติ video.publish')
        data['expires_at']=dt.datetime.now(dt.timezone.utc).timestamp()+int(data['expires_in'])
        save_json(token_path,data)
        return RedirectResponse('/?tiktok_connected=1')

    @app.get('/api/tiktok/creator')
    def creator():
        return request_api('/v2/post/publish/creator_info/query/')

    @app.get('/api/tiktok/jobs')
    def jobs():
        with connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM tiktok_publish ORDER BY queue_id DESC LIMIT 70')]

    @app.post('/api/tiktok/queue/{qid}/approve')
    def approve(qid:int,body:Approval):
        if not body.acknowledge_no_basket or not body.acknowledge_aigc_and_rights:
            raise HTTPException(400,'ต้องยืนยันว่าคลิปยังไม่ปักตะกร้าและตรวจสิทธิ์/ป้าย AI แล้ว')
        with connect() as db:
            r=db.execute('''SELECT q.*,d.video_filename FROM queue q
                JOIN drafts d ON d.id=q.draft_id WHERE q.id=?''',(qid,)).fetchone()
        if not r or r['platform']!='tiktok' or not r['video_filename']:
            raise HTTPException(412,'ต้องเป็นคิว TikTok ที่มีคลิป MP4 แล้ว')
        if not (Path(media_dir)/r['video_filename']).is_file():
            raise HTTPException(412,'ไม่พบไฟล์คลิป')
        info=creator()
        options=info.get('privacy_level_options',[])
        if body.privacy_level not in options:
            raise HTTPException(400,'Privacy ไม่ใช่สิทธิ์ที่บัญชีอนุญาต')
        try:
            scheduled=dt.datetime.fromisoformat(body.scheduled_at.replace('Z','+00:00'))
            if scheduled.tzinfo is None:raise ValueError('timezone missing')
        except ValueError:raise HTTPException(400,'เวลาต้องเป็น ISO8601 พร้อม timezone')
        when=scheduled.astimezone(dt.timezone.utc).isoformat()
        fingerprint=file_sha256(Path(media_dir)/r['video_filename'])
        with connect() as db:
            old=db.execute('SELECT state FROM tiktok_publish WHERE queue_id=?',(qid,)).fetchone()
            if old and old[0] not in ('approved','error'):
                raise HTTPException(409,'คิวนี้ถูกส่งขึ้น TikTok แล้ว ไม่ส่งซ้ำ')
            db.execute('''INSERT INTO tiktok_publish(queue_id,approved_at,privacy_level,scheduled_utc,state,approved_caption,approved_sha256)
              VALUES(?,?,?,?,'approved',?,?) ON CONFLICT(queue_id) DO UPDATE SET
              approved_at=excluded.approved_at,privacy_level=excluded.privacy_level,
              scheduled_utc=excluded.scheduled_utc,state='approved',
              approved_caption=excluded.approved_caption,approved_sha256=excluded.approved_sha256,detail='' ''',
              (qid,stamp(),body.privacy_level,when,body.caption,fingerprint))
        return {'state':'approved','scheduled_utc':when,'creator_username':info.get('creator_username','')}

    def push(job):
        # API supports video posting, not product attachment/basket creation.
        filename=Path(media_dir)/job['video_filename']
        if filename.suffix.lower()!='.mp4' or not filename.exists():
            raise ValueError('TikTok ต้องการคลิป MP4 ที่ยังอยู่ในเครื่อง')
        if not job['approved_sha256'] or file_sha256(filename)!=job['approved_sha256']:
            raise ValueError('คลิปเปลี่ยนไปหลังอนุมัติ กรุณาตรวจและอนุมัติคลิปใหม่')
        size=filename.stat().st_size
        if size<1000 or size>120*1024*1024:raise ValueError('ขนาดคลิปไม่รองรับ')
        count=max(1,size//(10*1024*1024))
        chunk_size=size if count==1 else 10*1024*1024
        # TikTok creator settings may have changed since the per-video approval; fail closed.
        info=request_api('/v2/post/publish/creator_info/query/')
        if job['privacy_level'] not in info.get('privacy_level_options',[]):
            raise ValueError('Privacy ของบัญชีเปลี่ยน กรุณายืนยันอีกครั้ง')
        body={'post_info':{'title':job['approved_caption'][:2200],
                  'privacy_level':job['privacy_level'],
                  'disable_comment':bool(info.get('comment_disabled')),
                  'disable_duet':bool(info.get('duet_disabled')),
                  'disable_stitch':bool(info.get('stitch_disabled')),
                  'is_aigc':True,'brand_content_toggle':True},
              'source_info':{'source':'FILE_UPLOAD','video_size':size,
                  'chunk_size':chunk_size,'total_chunk_count':count}}
        result=request_api('/v2/post/publish/video/init/',body)
        upload_url=result.get('upload_url','')
        host=urlparse(upload_url).hostname or ''
        if not (upload_url.startswith('https://') and (host=='open-upload.tiktokapis.com'
                   or host.endswith('.tiktokapis.com')) and result.get('publish_id')):
            raise RuntimeError('TikTok ไม่ส่ง upload URL ที่ถูกต้อง')
        # Only send binary to TikTok-owned upload URL returned by official API.
        with filename.open('rb') as fp:
            for i in range(count):
                length=chunk_size if i<count-1 else size-fp.tell()
                start=fp.tell(); binary=fp.read(length)
                headers={'Content-Type':'video/mp4','Content-Length':str(len(binary)),
                         'Content-Range':f'bytes {start}-{start+len(binary)-1}/{size}'}
                resp=requests.put(upload_url,data=binary,headers=headers,
                                  timeout=(10,100),allow_redirects=False)
                if resp.status_code not in (201,206):
                    raise RuntimeError('TikTok อัปโหลดไม่สำเร็จ HTTP '+str(resp.status_code))
        return result['publish_id']

    def publish_due():
        if not PUBLISH_LOCK.acquire(blocking=False):return
        try:
            with connect() as db:
                job=db.execute('''SELECT t.*,q.draft_id,d.video_filename,d.caption
                  FROM tiktok_publish t JOIN queue q ON q.id=t.queue_id
                  JOIN drafts d ON q.draft_id=d.id
                  WHERE t.state='approved' AND t.scheduled_utc<=?
                  ORDER BY t.scheduled_utc ASC LIMIT 1''',
                  (dt.datetime.now(dt.timezone.utc).isoformat(),)).fetchone()
                if not job:return
                job=dict(job)
                # Mark in-progress BEFORE outgoing network request; retries are not automatic.
                db.execute("UPDATE tiktok_publish SET state='uploading',processed_at=? WHERE queue_id=?",
                           (stamp(),job['queue_id']))
            try:
                publish_id=push(job)
                with connect() as db:
                    db.execute("UPDATE tiktok_publish SET state='submitted',publish_id=?,processed_at=? WHERE queue_id=?",
                               (publish_id,stamp(),job['queue_id']))
            except Exception as e:
                with connect() as db:
                    db.execute("UPDATE tiktok_publish SET state='error',detail=?,processed_at=? WHERE queue_id=?",
                               (str(e)[:350],stamp(),job['queue_id']))
        finally:PUBLISH_LOCK.release()

    @app.post('/api/tiktok/jobs/{qid}/check')
    def check(qid:int):
        with connect() as db:
            r=db.execute('SELECT * FROM tiktok_publish WHERE queue_id=?',(qid,)).fetchone()
        if not r or not r['publish_id']:
            raise HTTPException(412,'ยังไม่มีงานส่งไป TikTok')
        obj=request_api('/v2/post/publish/status/fetch/',{'publish_id':r['publish_id']})
        state=str(obj.get('status','UNKNOWN'))[:80]
        ids=obj.get('publicaly_available_post_id') or []
        url=''  # public URL needs actual username; never invent it
        with connect() as db:
            db.execute('UPDATE tiktok_publish SET state=?,detail=?,posted_url=?,processed_at=? WHERE queue_id=?',
                       ('complete' if state=='PUBLISH_COMPLETE' else ('error' if state=='FAILED' else 'processing'),
                       str(obj.get('fail_reason',''))[:280],url,stamp(),qid))
            if state=='PUBLISH_COMPLETE':
                db.execute("UPDATE queue SET status='posted' WHERE id=?",(qid,))
        return {'tiktok_status':state,'video_ids':ids,'url':url,'reason':obj.get('fail_reason','')}

    def tick_loop():
        while not stop.wait(45):
            try:publish_due()
            except Exception:pass  # errors are saved against the queue; never auto-retry a submitted task

    stop=threading.Event()
    @app.on_event('startup')
    def run_loop():
        stop.clear();threading.Thread(target=tick_loop,daemon=True,name='tiktok-posts').start()
    @app.on_event('shutdown')
    def stop_loop():stop.set()
