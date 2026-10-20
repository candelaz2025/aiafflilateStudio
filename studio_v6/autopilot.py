"""Conservative workflow: public trend -> candidate match -> sourced product -> script -> Veo -> approved posting queue.
No TikTok/Shopee passwords, no marketplace scraping. No fake video or sales.
"""
from __future__ import annotations
import json
import os
import secrets
import threading
import time
import datetime as dt
from pathlib import Path
from urllib.parse import urlparse
import requests
from fastapi import HTTPException
from pydantic import BaseModel, Field
from external_radar import research_candidates, fetch_trends
from video_veo import generate_veo

STATE_LOCK=threading.Lock()
STOP=threading.Event()
RUNNING=False

DEFAULTS={'enabled':False,'auto_discover':True,'auto_prepare':True,'auto_generate':False,
          'max_new_drafts_per_cycle':3,'max_videos_per_day':2,'scan_hours':12,
          'max_video_wait_minutes':15,'allow_without_reference':False}

class Settings(BaseModel):
    enabled: bool=False
    auto_discover:bool=True
    auto_prepare:bool=True
    auto_generate:bool=False
    max_new_drafts_per_cycle:int=Field(default=3,ge=1,le=10)
    max_videos_per_day:int=Field(default=2,ge=0,le=10)
    scan_hours:int=Field(default=12,ge=1,le=168)
    max_video_wait_minutes:int=Field(default=15,ge=5,le=30)
    allow_without_reference:bool=False


def mount_autopilot(app,connect,stamp,local_script,media_dir,safe_name):
    with connect() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS autopilot_settings(id INTEGER PRIMARY KEY CHECK(id=1),config TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS autopilot_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,kind TEXT NOT NULL,
            state TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS autopilot_video_attempts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,draft_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,finished_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS autopilot_possible_matches(
            candidate_id INTEGER NOT NULL,platform TEXT NOT NULL,url TEXT NOT NULL,
            checked_at TEXT NOT NULL,PRIMARY KEY(candidate_id,platform));
          INSERT OR IGNORE INTO autopilot_settings(id,config) VALUES(1,'{}');
        ''')

    def settings():
        with connect() as db:
            data=json.loads(db.execute('SELECT config FROM autopilot_settings WHERE id=1').fetchone()[0])
        return dict(DEFAULTS,**data)

    def log(kind,state,detail=''):
        with connect() as db:
            db.execute('INSERT INTO autopilot_runs(at,kind,state,detail) VALUES(?,?,?,?)',
                       (stamp(),kind,state,str(detail)[:1200]))

    def discover_public():
        """Actual public RSS retrieval; never interpret search traffic as sales."""
        items,details=research_candidates(fetch_trends_fn=fetch_trends)
        count=0
        with connect() as db:
            for item in items:
                db.execute('''INSERT INTO external_candidates(
                  title,source_name,source_url,category,trend_traffic,score,discovered_at)
                  VALUES(?,?,?,?,?,?,?) ON CONFLICT(title,source_name) DO UPDATE SET
                  source_url=excluded.source_url,trend_traffic=excluded.trend_traffic,
                  score=excluded.score,discovered_at=excluded.discovered_at''',
                  (item['title'],item['source_name'],item['source_url'],item['category'],
                   item.get('trend_traffic'),float(item.get('score',25.0)),stamp()))
                count+=1
            db.execute('INSERT INTO external_runs(at,source,found,message) VALUES(?,?,?,?)',
                       (stamp(),'Product Radar multi-source',count,details[:500]))
        return count

    def verify_listings(max_items=8):
        """Optional Brave web search: only finds possible indexed listings, not commission eligibility."""
        key=os.getenv('BRAVE_SEARCH_API_KEY','').strip()
        if not key:
            return {'searched':0,'found':0,'note':'ไม่มี BRAVE_SEARCH_API_KEY; ค้นหาสินค้าบนแพลตฟอร์มโดยอัตโนมัติยังไม่เปิด'}
        with connect() as db:
            candidates=[dict(x) for x in db.execute('''SELECT x.* FROM external_candidates x
              WHERE x.confirmed_tiktok=0 OR x.confirmed_shopee=0 ORDER BY discovered_at DESC LIMIT ?''',(max_items,))]
        found=0
        for r in candidates:
            for plat,domain in [('tiktok','shop.tiktok.com'),('shopee','shopee.co.th')]:
                try:
                    resp=requests.get('https://api.search.brave.com/res/v1/web/search',
                        params={'q':f'site:{domain} "{r["title"]}"','count':5},
                        headers={'X-Subscription-Token':key,'Accept':'application/json'},timeout=14)
                    resp.raise_for_status()
                    listings=resp.json().get('web',{}).get('results',[])
                    # Search results are UNVERIFIED leads, not proof of the same SKU.
                    for listing in listings:
                        url=listing.get('url','')
                        host=urlparse(url).hostname or ''
                        if url.startswith('https://') and (host==domain or host.endswith('.'+domain)):
                            with connect() as db:
                                db.execute('''INSERT INTO autopilot_possible_matches(candidate_id,platform,url,checked_at)
                                  VALUES(?,?,?,?) ON CONFLICT(candidate_id,platform) DO UPDATE SET
                                  url=excluded.url,checked_at=excluded.checked_at''',
                                  (r['id'],plat,url[:900],stamp()))
                            found+=1
                            break
                except (requests.RequestException,ValueError):
                    continue
        return {'searched':len(candidates),'found':found,
                'note':'เป็นเพียงลิงก์ที่พบในดัชนีเว็บ ยังไม่ยืนยันสินค้า/สิทธิ์ Affiliate'}

    def prepare(limit):
        count=0
        # Only verified items in authorized data feeds or manually confirmed marketplace listings.
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            candidates=[('radar',dict(r)) for r in db.execute('''SELECT * FROM radar_candidates
                WHERE draft_id IS NULL AND url <> '' AND score >= 20
                ORDER BY score DESC, id DESC LIMIT ?''',(limit,)).fetchall()]
            remaining=limit-len(candidates)
            if remaining:
                candidates += [('external',dict(r)) for r in db.execute('''SELECT * FROM external_candidates
                  WHERE draft_id IS NULL AND (confirmed_tiktok=1 OR confirmed_shopee=1)
                  ORDER BY score DESC,id DESC LIMIT ?''',(remaining,)).fetchall()]
            for typ,r in candidates:
                if typ=='radar':
                    pl=[r['platform']]
                    linkt=r['url'] if r['platform']=='tiktok' else ''
                    links=r['url'] if r['platform']=='shopee' else ''
                    price=str(r['price'])+' บาท' if r['price'] is not None else ''
                else:
                    pl=[p for p,b in [('tiktok','confirmed_tiktok'),('shopee','confirmed_shopee')] if r[b]]
                    linkt=r['tiktok_link'] if 'tiktok' in pl else ''
                    links=r['shopee_link'] if 'shopee' in pl else ''
                    price=''
                if not pl:continue
                product_id=r['product_id']
                if not product_id:
                    result=db.execute('''INSERT INTO products(title,price,features,audience,tiktok_link,shopee_link,created_at)
                      VALUES(?,?,?,?,?,?,?)''',(r['title'][:120],price,r['features'],r['audience'],linkt,links,stamp()))
                    product_id=result.lastrowid
                p=dict(db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone())
                s=local_script(p)
                result=db.execute('''INSERT INTO drafts(product_id,hook,voiceover,caption,onscreen,video_prompt,created_at)
                VALUES(?,?,?,?,?,?,?)''',(product_id,s['hook'],s['voiceover'],s['caption'],s['onscreen'],s['video_prompt'],stamp()))
                did=result.lastrowid
                for platform in pl:
                    db.execute('INSERT OR IGNORE INTO queue(draft_id,platform,created_at) VALUES(?,?,?)',
                               (did,platform,stamp()))
                table='radar_candidates' if typ=='radar' else 'external_candidates'
                db.execute(f'UPDATE {table} SET draft_id=?,product_id=? WHERE id=?',(did,product_id,r['id']))
                count+=1
        return count

    def generate_one(config):
        if not os.getenv('GEMINI_API_KEY','').strip():
            return {'generated':0,'note':'ไม่มี Gemini API key; ไม่ได้เสียเครดิต'}
        today=dt.datetime.now(dt.timezone.utc).date().isoformat()
        with connect() as db:
            total=db.execute('SELECT COUNT(*) FROM autopilot_video_attempts WHERE started_at >= ?', (today,)).fetchone()[0]
            if total>=config['max_videos_per_day']:
                return {'generated':0,'note':'ถึงเพดานงานวิดีโอรายวันแล้ว'}
            cond='' if config['allow_without_reference'] else "AND p.reference_filename <> ''"
            job=db.execute(f'''SELECT d.*,p.reference_filename FROM drafts d JOIN products p ON p.id=d.product_id
                WHERE d.video_filename='' AND NOT EXISTS(SELECT 1 FROM autopilot_video_attempts a WHERE a.draft_id=d.id)
                {cond} ORDER BY d.id LIMIT 1''').fetchone()
            if not job:
                return {'generated':0,'note':'ไม่มีบทที่มีภาพอ้างอิงตรงเงื่อนไขและยังไม่เคยเจน'}
            job=dict(job)
            attempt=db.execute('INSERT INTO autopilot_video_attempts(draft_id,started_at,status) VALUES(?,?,?)',
                               (job['id'],stamp(),'running')).lastrowid
        output=Path(media_dir)/safe_name('video','.mp4')
        try:
            ref=(Path(media_dir)/job['reference_filename']) if job['reference_filename'] else None
            op=generate_veo(job['video_prompt'],output,reference=ref,
                            max_wait_seconds=config['max_video_wait_minutes']*60)
            with connect() as db:
                db.execute('''UPDATE drafts SET video_filename=?,state='video_ready',google_interaction_id=? WHERE id=?''',
                           (output.name,op[:300],job['id']))
                db.execute("UPDATE queue SET status='ready_manual' WHERE draft_id=? AND status='pending_review'",(job['id'],))
                db.execute('''UPDATE autopilot_video_attempts SET finished_at=?,status='completed' WHERE id=?''',
                           (stamp(),attempt))
            return {'generated':1,'draft_id':job['id'],'filename':output.name}
        except Exception as e:
            output.unlink(missing_ok=True)
            with connect() as db:
                db.execute('''UPDATE autopilot_video_attempts SET finished_at=?,status='error',detail=? WHERE id=?''',
                           (stamp(),str(e)[:500],attempt))
            raise

    def tick(force_scan=False):
        global RUNNING
        if not STATE_LOCK.acquire(blocking=False):
            return {'state':'busy'}
        RUNNING=True
        result={}
        try:
            cfg=settings()
            if not cfg['enabled']:
                return {'state':'disabled'}
            last=last_scan_time()
            do_scan=cfg['auto_discover'] and (force_scan or last is None or
                     (dt.datetime.now(dt.timezone.utc)-last).total_seconds()>=cfg['scan_hours']*3600)
            if do_scan:
                try:
                    result['discovered']=discover_public()
                    result['marketplace_index']=verify_listings()
                    log('discovery','ok',json.dumps(result,ensure_ascii=False))
                except Exception as e:
                    log('discovery','error',str(e))
                    result['discovery_error']=str(e)[:140]
            if cfg['auto_prepare']:
                result['new_drafts']=prepare(cfg['max_new_drafts_per_cycle'])
                log('script','ok',f'created={result["new_drafts"]}')
            if cfg['auto_generate']:
                try:
                    result['video']=generate_one(cfg)
                    log('video','ok',json.dumps(result['video'],ensure_ascii=False))
                except Exception as e:
                    log('video','error',str(e))
                    result['video_error']=str(e)[:140]
            # TikTok/Shopee never auto-publish from this worker without approved API,
            # TikTok's per-post user consent and selection of privacy/post options.
            return {'state':'processed',**result}
        finally:
            RUNNING=False
            STATE_LOCK.release()

    def last_scan_time():
        with connect() as db:
            r=db.execute("SELECT at FROM autopilot_runs WHERE kind='discovery' ORDER BY id DESC LIMIT 1").fetchone()
        if not r:return None
        try:return dt.datetime.fromisoformat(r[0])
        except ValueError:return None

    @app.get('/api/autopilot/status')
    def get_status():
        cfg=settings()
        with connect() as db:
            logs=[dict(x) for x in db.execute('SELECT * FROM autopilot_runs ORDER BY id DESC LIMIT 20')]
            possible=[dict(x) for x in db.execute('''SELECT a.*,e.title FROM autopilot_possible_matches a
                 JOIN external_candidates e ON e.id=a.candidate_id ORDER BY a.checked_at DESC LIMIT 20''')]
            attempted=db.execute('SELECT COUNT(*) FROM autopilot_video_attempts').fetchone()[0]
        return {'config':cfg,'running':RUNNING,'logs':logs,'possible_matches':possible,
                'attempted_videos':attempted,'providers':{'google_veo':bool(os.getenv('GEMINI_API_KEY')),
                'brave_search':bool(os.getenv('BRAVE_SEARCH_API_KEY')),
                'tiktok_direct_post':'requires_approved_api_and_per_post_consent',
                'shopee_video':'manual_only_no_verified_official_video_publish_api'},
                'limits':'Google Trends measures searches, indexed shop results are unverified, not sales or affiliate entitlement.'}

    @app.put('/api/autopilot/settings')
    def change_settings(body:Settings):
        cfg=body.model_dump()
        if cfg['auto_generate'] and cfg['max_videos_per_day']>0 and not os.getenv('GEMINI_API_KEY',''):
            raise HTTPException(412,'ตั้ง GEMINI_API_KEY บนเซิร์ฟเวอร์ก่อนเปิดเสียเครดิตสร้างคลิป')
        with connect() as db:
            db.execute('UPDATE autopilot_settings SET config=? WHERE id=1',
                       (json.dumps(cfg,ensure_ascii=False),))
        log('control','ok','enabled='+str(cfg['enabled']))
        return {'config':cfg}

    @app.post('/api/autopilot/tick')
    def request_tick():
        if RUNNING:return {'state':'busy'}
        t=threading.Thread(target=tick,kwargs={'force_scan':True},daemon=True,name='autopilot-manual')
        t.start()
        return {'state':'started','note':'ตรวจสถานะและประวัติในแดชบอร์ด; ไม่หมายถึงโพสต์สำเร็จ'}

    def worker():
        while not STOP.wait(60):
            if settings()['enabled']:
                try:tick()
                except Exception as e:log('scheduler','error',str(e))

    @app.on_event('startup')
    def on_start():
        STOP.clear()
        threading.Thread(target=worker,daemon=True,name='studio-autopilot').start()

    @app.on_event('shutdown')
    def on_stop():
        STOP.set()
