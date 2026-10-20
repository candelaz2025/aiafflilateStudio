"""Product Radar: rank sourced affiliate offers; never fabricate sales or scrape marketplaces.

The provider side is a *licensed/approved HTTPS JSON feed* controlled by the operator.
It is intentionally not a login/password scraper or an unofficial TikTok/Shopee API client.
"""
from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel, Field

class PrepareTop(BaseModel):
    platform: str = 'all'
    limit: int = Field(default=3,ge=1,le=10)
    min_sales: int = Field(default=100,ge=0)
    min_commission: float = Field(default=5,ge=0,le=100)


MAX_FEED_BYTES = 2_000_000
MAX_PRODUCTS_PER_SCAN = 1500
SYNC_LOCK = threading.Lock()


def _num(value, default=None):
    if value is None or value == '':
        return default
    try:
        val = float(str(value).replace(',', '').replace('%', '').replace('฿', '').strip())
        return val if math.isfinite(val) and val >= 0 else default
    except (TypeError, ValueError):
        return default


def _value(d, *keys):
    for key in keys:
        v = d.get(key)
        if v is not None and str(v).strip() != '':
            return v
    return None


def _url(u):
    u = str(u or '').strip()
    if not u:
        return ''
    p = urlparse(u)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        return ''
    return u[:800]


def _score(price, commission, sales, rating, reviews):
    """An explainable *prioritization* score, not a predicted sales number."""
    a = min(40, math.log10(sales + 1) / 5 * 40) if sales is not None else 0
    b = min(25, commission / 30 * 25) if commission is not None else 0
    c = min(15, max(0, (rating - 3) / 2 * 15)) if rating is not None else 0
    d = min(10, math.log10(reviews + 1) / 4 * 10) if reviews is not None else 0
    e = (10 if 79 <= price <= 499 else 5) if price is not None else 0
    return round(a + b + c + d + e, 1)


def _normalize(record, platform, source):
    if not isinstance(record, dict):
        return None
    name = str(_value(record, 'title', 'name', 'product_name', 'ชื่อสินค้า') or '').strip()[:120]
    if len(name) < 2:
        return None
    price = _num(_value(record, 'price_thb', 'price', 'ราคา'))
    commission = _num(_value(record, 'commission_pct', 'commission_percent', 'commission_rate', 'ค่าคอมเปอร์เซ็นต์', 'ค่าคอม'))
    sales = _num(_value(record, 'units_sold_30d', 'sales_30d', 'units_sold', 'sold_count', 'ยอดขาย30วัน', 'ยอดขาย'))
    reviews = _num(_value(record, 'reviews', 'review_count', 'รีวิว'))
    rating = _num(_value(record, 'rating', 'rating_average', 'คะแนน'))
    if price is not None and price > 5_000_000: price = None
    if commission is not None and commission > 100: commission = None
    if rating is not None and rating > 5: rating = None
    if sales is not None and sales > 100_000_000: sales = None
    if reviews is not None and reviews > 100_000_000: reviews = None
    link = _url(_value(record, 'url', 'product_url', 'link', 'ลิงก์'))
    external_id = str(_value(record, 'external_id', 'product_id', 'รหัสสินค้า') or '').strip()[:150]
    if not external_id:
        basis = link if link else name.casefold()
        external_id = 'derived_' + hashlib.sha256(f'{platform}|{basis}'.encode()).hexdigest()[:25]
    category = str(_value(record, 'category', 'หมวดหมู่') or '').strip()[:100]
    details = str(_value(record, 'features', 'details', 'จุดเด่น') or '').strip()[:750]
    audience = str(_value(record, 'audience', 'กลุ่มเป้าหมาย') or '').strip()[:200]
    period = '30d' if _value(record, 'units_sold_30d', 'sales_30d', 'ยอดขาย30วัน') is not None else ('unspecified' if sales is not None else 'missing')
    return dict(platform=platform, external_id=external_id, title=name, price=price,
        commission_pct=commission, units_sold=sales, sales_period=period, rating=rating,
        reviews=reviews, url=link, category=category, features=details, audience=audience,
        source_type=source, score=_score(price, commission, sales, rating, reviews))


def _feed_url(platform):
    return os.getenv('RADAR_TIKTOK_FEED_URL' if platform == 'tiktok' else 'RADAR_SHOPEE_FEED_URL', '').strip()


def _feed_token(platform):
    return os.getenv('RADAR_TIKTOK_FEED_TOKEN' if platform == 'tiktok' else 'RADAR_SHOPEE_FEED_TOKEN', '').strip()


def _guard_feed_url(url):
    p = urlparse(url)
    allowed = {x.strip().lower() for x in os.getenv('RADAR_ALLOWED_FEED_HOSTS', '').split(',') if x.strip()}
    if p.scheme != 'https' or not p.hostname or p.port not in (None, 443) or p.username or p.password:
        raise ValueError('ฟีดต้องเป็น HTTPS ปกติ (ไม่อนุญาต user:pass หรือพอร์ตพิเศษ)')
    host = p.hostname.lower()
    if host not in allowed:
        raise ValueError('ยังไม่ได้เพิ่มโดเมนผู้ให้บริการใน RADAR_ALLOWED_FEED_HOSTS')
    try:
        ipaddress.ip_address(host)
        raise ValueError('ไม่อนุญาตฟีดที่ระบุ IP โดยตรง')
    except ValueError as exc:
        if 'ไม่อนุญาตฟีด' in str(exc):
            raise
    if host in {'localhost', 'localhost.localdomain'} or host.endswith('.local'):
        raise ValueError('ไม่อนุญาต localhost หรือโดเมนภายใน')


def _download_json_feed(platform):
    url = _feed_url(platform)
    if not url:
        return None
    _guard_feed_url(url)
    headers = {'Accept': 'application/json', 'User-Agent':'AffiliateAutoStudioRadar/1.0'}
    if _feed_token(platform):
        headers['Authorization'] = f'Bearer {_feed_token(platform)}'
    response = requests.get(url, headers=headers, timeout=(5, 20), allow_redirects=False, stream=True)
    try:
        if 300 <= response.status_code < 400:
            raise ValueError('ฟีดมีการ redirect ซึ่งไม่ได้รับอนุญาต')
        response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_content(32_768):
            payload.extend(chunk)
            if len(payload) > MAX_FEED_BYTES:
                raise ValueError('ขนาดฟีดใหญ่เกิน 2 MB')
        document = json.loads(payload.decode('utf-8-sig'))
        if isinstance(document, dict):
            document = document.get('products', document.get('items'))
        if not isinstance(document, list):
            raise ValueError('ฟีดต้องเป็น JSON array หรือ {"products": [...]}')
        if len(document) > MAX_PRODUCTS_PER_SCAN:
            raise ValueError('ฟีดมีสินค้ามากเกิน 1,500 รายการต่อครั้ง')
        return document
    finally:
        response.close()


def mount_radar(app, connect, stamp, local_script):
    with connect() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS radar_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL CHECK (platform IN ('tiktok','shopee')),
            external_id TEXT NOT NULL, title TEXT NOT NULL,
            price REAL, commission_pct REAL, units_sold REAL, sales_period TEXT NOT NULL,
            rating REAL, reviews REAL, url TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '', features TEXT NOT NULL DEFAULT '',
            audience TEXT NOT NULL DEFAULT '', score REAL NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL, fetched_at TEXT NOT NULL,
            product_id INTEGER, draft_id INTEGER,
            UNIQUE(platform,external_id)
          );
          CREATE TABLE IF NOT EXISTS radar_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT NOT NULL,
            source TEXT NOT NULL, imported INTEGER NOT NULL,
            errors TEXT NOT NULL DEFAULT ''
          );
        ''')

    def put_products(items, platform, source):
        good = 0
        with connect() as db:
            for record in items:
                normalized = _normalize(record, platform, source)
                if not normalized:
                    continue
                keys = list(normalized)
                db.execute(f'''INSERT INTO radar_candidates({','.join(keys)},fetched_at)
                   VALUES ({','.join('?' for _ in keys)},?)
                   ON CONFLICT(platform,external_id) DO UPDATE SET
                   title=excluded.title,price=excluded.price,commission_pct=excluded.commission_pct,
                   units_sold=excluded.units_sold,sales_period=excluded.sales_period,
                   rating=excluded.rating,reviews=excluded.reviews,url=excluded.url,
                   category=excluded.category,features=excluded.features,audience=excluded.audience,
                   score=excluded.score,source_type=excluded.source_type,fetched_at=excluded.fetched_at''',
                   [normalized[k] for k in keys] + [stamp()])
                good += 1
        return good

    def log_run(source, count, errors=''):
        with connect() as db:
            db.execute('INSERT INTO radar_runs(ran_at,source,imported,errors) VALUES (?,?,?,?)',
                (stamp(),source,count,errors[:1000]))

    def sync_sources():
        if not SYNC_LOCK.acquire(blocking=False):
            raise HTTPException(409, 'เรดาร์กำลังสแกนข้อมูลอยู่')
        try:
            count = 0
            results = {}
            for platform in ('tiktok', 'shopee'):
                if not _feed_url(platform):
                    results[platform] = {'state':'not_connected', 'count':0}
                    continue
                try:
                    records = _download_json_feed(platform)
                    imported = put_products(records, platform, 'authorized_feed')
                    count += imported
                    results[platform] = {'state':'ok', 'count':imported}
                    log_run(platform, imported)
                except (ValueError, requests.RequestException, UnicodeError) as exc:
                    msg = str(exc)[:250]
                    results[platform] = {'state':'error', 'message':msg, 'count':0}
                    log_run(platform, 0, msg)
            return {'count':count,'sources':results}
        finally:
            SYNC_LOCK.release()

    def _promote(cid):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            c = db.execute('SELECT * FROM radar_candidates WHERE id=?',(cid,)).fetchone()
            if not c:
                raise HTTPException(404, 'ไม่พบสินค้าจากเรดาร์')
            c = dict(c)
            if c['product_id']:
                pid = c['product_id']
            else:
                pr = str(round(c['price'],2))+' บาท' if c['price'] is not None else ''
                link_t = c['url'] if c['platform']=='tiktok' else ''
                link_s = c['url'] if c['platform']=='shopee' else ''
                cur = db.execute('INSERT INTO products(title,price,features,audience,tiktok_link,shopee_link,created_at) VALUES(?,?,?,?,?,?,?)',
                    (c['title'],pr,c['features'],c['audience'],link_t,link_s,stamp()))
                pid = cur.lastrowid
                db.execute('UPDATE radar_candidates SET product_id=? WHERE id=?',(pid,cid))
            return pid, c

    def prepare_candidate(cid):
        pid,c = _promote(cid)
        with connect() as db:
            row = db.execute('SELECT draft_id FROM radar_candidates WHERE id=?',(cid,)).fetchone()
            if row['draft_id']:
                return {'product_id':pid,'draft_id':row['draft_id'],'created':False}
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT draft_id FROM radar_candidates WHERE id=?',(cid,)).fetchone()
            if row['draft_id']:
                return {'product_id':pid,'draft_id':row['draft_id'],'created':False}
            pr = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
            script = local_script(dict(pr))  # No billable AI calls during automatic preparation
            r = db.execute('INSERT INTO drafts(product_id,hook,voiceover,caption,onscreen,video_prompt,created_at) VALUES(?,?,?,?,?,?,?)',
                 (pid,script['hook'],script['voiceover'],script['caption'],script['onscreen'],script['video_prompt'],stamp()))
            did = r.lastrowid
            db.execute('INSERT INTO queue(draft_id,platform,created_at) VALUES(?,?,?)',(did,c['platform'],stamp()))
            db.execute('UPDATE radar_candidates SET draft_id=? WHERE id=?',(did,cid))
        return {'product_id':pid,'draft_id':did,'created':True}

    @app.get('/api/radar/status')
    def radar_status():
        with connect() as db:
            n = db.execute('SELECT COUNT(*) FROM radar_candidates').fetchone()[0]
            latest = db.execute('SELECT * FROM radar_runs ORDER BY id DESC LIMIT 1').fetchone()
        feeds = {platform: bool(_feed_url(platform)) for platform in ('tiktok','shopee')}
        try:
            mins = int(os.getenv('RADAR_AUTO_SYNC_MINUTES','0') or 0)
        except ValueError:
            mins = 0
        return {'count':n,'feeds_configured':feeds,'auto_sync_enabled':mins>=15 and any(feeds.values()),
                'interval_minutes':mins if mins>=15 else 0,
                'last_scan':dict(latest) if latest else None,
                'disclaimer':'สถิติจากไฟล์/ผู้ให้บริการที่เชื่อมไว้ ไม่ได้ยืนยันยอดขายกับแพลตฟอร์มโดยอิสระ'}

    @app.get('/api/radar')
    def list_radar(platform: str='all', query: str='', min_sales: int=0, min_commission: float=0, limit: int=120):
        if platform not in ('all','tiktok','shopee'):
            raise HTTPException(400,'แพลตฟอร์มไม่ถูกต้อง')
        if min_sales<0 or min_commission<0 or min_commission>100:
            raise HTTPException(400,'ตัวกรองไม่ถูกต้อง')
        limit = min(max(limit,1),500)
        query = query.strip()[:100]
        sql = 'SELECT * FROM radar_candidates WHERE 1=1'
        params=[]
        if platform!='all':
            sql += ' AND platform=?';params.append(platform)
        if query:
            sql += ' AND (title LIKE ? OR category LIKE ?)';params.extend([f'%{query}%',f'%{query}%'])
        if min_sales:
            sql += ' AND units_sold>=?';params.append(min_sales)
        if min_commission:
            sql += ' AND commission_pct>=?';params.append(min_commission)
        sql += ' ORDER BY CASE WHEN units_sold IS NULL THEN 1 ELSE 0 END, score DESC, id DESC LIMIT ?'
        params.append(limit)
        with connect() as db:
            return [dict(row) for row in db.execute(sql,params).fetchall()]

    @app.post('/api/radar/import')
    async def import_csv(file: UploadFile=File(...), platform: str='tiktok'):
        if platform not in ('tiktok','shopee'):
            raise HTTPException(400,'ต้องระบุแพลตฟอร์ม TikTok หรือ Shopee')
        if not file.filename or not file.filename.lower().endswith('.csv'):
            raise HTTPException(400,'กรุณาเลือกไฟล์ .csv')
        data=await file.read(MAX_FEED_BYTES+1)
        if len(data)>MAX_FEED_BYTES:
            raise HTTPException(413,'ไฟล์ต้องไม่เกิน 2 MB')
        try:
            content=data.decode('utf-8-sig')
            csv_data=csv.DictReader(io.StringIO(content))
            if not csv_data.fieldnames:
                raise ValueError('ไม่มีหัวตาราง')
            records=[]
            for r in csv_data:
                records.append(r)
                if len(records)>MAX_PRODUCTS_PER_SCAN:
                    raise ValueError('ข้อมูลเกิน 1,500 รายการ')
        except (UnicodeError, csv.Error, ValueError) as e:
            raise HTTPException(400,'ไฟล์ CSV ไม่ถูกต้อง: '+str(e))
        good = put_products(records,platform,'user_csv')
        log_run('csv_'+platform,good)
        return {'count':good,'platform':platform,'skipped':len(records)-good}

    @app.post('/api/radar/sync')
    def manual_sync():
        if not (_feed_url('tiktok') or _feed_url('shopee')):
            raise HTTPException(412,'ยังไม่ได้เชื่อมฟีดข้อมูลสินค้า — ตั้งค่า URL ผู้ให้บริการที่ได้รับอนุญาตใน .env ก่อน')
        return sync_sources()

    @app.post('/api/radar/{cid}/prepare')
    def prepare_one(cid:int):
        return prepare_candidate(cid)

    @app.post('/api/radar/prepare-top')
    def prepare_top(body: PrepareTop):
        if body.platform not in ('all','tiktok','shopee'):
            raise HTTPException(400,'แพลตฟอร์มไม่ถูกต้อง')
        q = '''SELECT id FROM radar_candidates WHERE draft_id IS NULL
                AND units_sold IS NOT NULL AND units_sold>=? AND commission_pct>=?'''
        params=[body.min_sales,body.min_commission]
        if body.platform!='all':
            q += ' AND platform=?';params.append(body.platform)
        q += ' ORDER BY score DESC,id DESC LIMIT ?';params.append(body.limit)
        with connect() as db:
            ids=[r['id'] for r in db.execute(q,params).fetchall()]
        done=[prepare_candidate(cid) for cid in ids]
        return {'prepared':len([d for d in done if d['created']]),'results':done}

    # Poll only configured feeds, and only when running as an app server.
    # Without credentials: the radar stays honest rather than pretending to have live products.
    stop = threading.Event()
    worker = {'thread':None}

    def auto_loop(minutes):
        while not stop.is_set():
            try:
                result=sync_sources()
                top_n = max(0,min(10,int(os.getenv('RADAR_AUTO_PREPARE_TOP','0') or 0)))
                if result['count'] and top_n:
                    with connect() as db:
                        ids=[r['id'] for r in db.execute('''SELECT id FROM radar_candidates WHERE draft_id IS NULL
                              AND source_type='authorized_feed' AND units_sold>=100 AND commission_pct>=5
                              ORDER BY score DESC LIMIT ?''',(top_n,)).fetchall()]
                    for cid in ids:
                        prepare_candidate(cid)
            except Exception as e:
                log_run('auto',0,str(e))
            if stop.wait(minutes*60):
                break

    @app.on_event('startup')
    def start_radar_polling():
        try:
            minutes=int(os.getenv('RADAR_AUTO_SYNC_MINUTES','0') or 0)
        except ValueError:
            minutes=0
        if minutes>=15 and (_feed_url('tiktok') or _feed_url('shopee')):
            stop.clear()
            thread=threading.Thread(target=auto_loop,args=(minutes,),name='radar-auto-sync',daemon=True)
            worker['thread']=thread
            thread.start()

    @app.on_event('shutdown')
    def stop_radar_polling():
        stop.set()
        if worker['thread']:
            worker['thread'].join(timeout=2)
