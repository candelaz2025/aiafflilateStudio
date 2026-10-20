"""Independent product discovery, using a public opt-in RSS trend source and attributed CSV.

Important: Google Trends 'search volume' is NOT sales. This module never reads private
marketplace pages, signs in, creates affiliate links or assumes shop availability.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
from urllib.parse import quote_plus
import threading
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from fastapi import File, UploadFile, HTTPException
from pydantic import BaseModel, Field

TRENDS_RSS = 'https://trends.google.com/trending/rss?geo=TH'
MAX_BYTES = 1_500_000
MAX_RECORDS = 300
STOP_WORDS = ('ผลบอล','หวย','คริปโต','บาคาร่า','สล็อต','หวย','ข่าว','บุหรี่','กัญชา','ลอตเตอรี่','ราคาเงิน','ราคาทอง')
PRODUCT_WORDS = (
    'เครื่องดูดฝุ่น','หุ่นยนต์ดูดฝุ่น','หม้อทอด','พัดลม','เครื่องฟอกอากาศ',
    'เครื่องชงกาแฟ','กระติกน้ำ','แก้วเก็บความเย็น','กระบอกน้ำ','ขวดน้ำ',
    'เครื่องสำอาง','ครีมกันแดด','ลิปสติก','เซรั่ม','สกินแคร์','กันแดด','รองพื้น','น้ำหอม',
    'หูฟัง','ลำโพง','คีย์บอร์ด','เมาส์ไร้สาย','สายชาร์จ','แบตสำรอง','power bank',
    'รองเท้า','กระเป๋า','เสื้อกันฝน','เครื่องนอน','ผ้าห่ม','หมอน','ไฟฉาย',
    'กล่องเก็บของ','อุปกรณ์ครัว','มีดทำครัว','แปรงสีฟัน','ไมโครเวฟ','เครื่องซักผ้า',
    'เครื่องพ่น','โต๊ะพับ','เก้าอี้','จอคอม','ที่วางโทรศัพท์','ปลอกหมอน',
    'เครื่องรีดผ้า','เครื่องไล่ยุง','ที่ดูดฝุ่น','น้ำยาล้าง','กระบอกฉีด','ของเล่นแมว',
)
LOCK = threading.Lock()

# Generic investigation topics, not claims of best-selling products, and not SKU records.
# Used only when public feeds have no item that passes the consumer-product filter.
SEED_RESEARCH_TOPICS = (
    ('พัดลมพกพา','เครื่องใช้ไฟฟ้าขนาดเล็ก'),
    ('เครื่องดูดฝุ่นไร้สาย','เครื่องใช้ในบ้าน'),
    ('กล่องเก็บของอเนกประสงค์','จัดระเบียบบ้าน'),
    ('แก้วเก็บความเย็น','ของใช้ประจำวัน'),
    ('ที่วางโทรศัพท์','อุปกรณ์มือถือ'),
    ('สายชาร์จ USB-C','อุปกรณ์มือถือ'),
    ('หูฟังไร้สาย','อุปกรณ์ไอที'),
    ('โคมไฟตั้งโต๊ะ','ของแต่งบ้าน'),
    ('หม้อทอดไร้น้ำมัน','เครื่องใช้ในครัว'),
    ('กระเป๋าสะพายข้าง','แฟชั่น'),
    ('หมอนรองคอ','ของใช้ในบ้าน'),
    ('ไม้ถูพื้นแบบรีดน้ำ','เครื่องมือทำความสะอาด'),
    ('เครื่องชั่งครัวดิจิทัล','เครื่องใช้ในครัว'),
    ('กระบอกน้ำพกพา','ของใช้ประจำวัน'),
    ('ของเล่นแมว','ของใช้สัตว์เลี้ยง'),
    ('ไฟฉายชาร์จไฟได้','อุปกรณ์กลางแจ้ง'),
)

def research_topics():
    """Research starting points only. Neither data source nor source URL proves sales."""
    return [dict(title=title, category='หัวข้อค้นคว้า / '+category,
                 source_name='ไอเดียเริ่มต้น (ไม่ใช่ยอดขาย)',
                 source_url='https://www.google.com/search?q='+quote_plus(title+' รีวิว ราคา'),
                 trend_traffic=None, score=5.0) for title,category in SEED_RESEARCH_TOPICS]


def fetch_product_news():
    """Public product-related news as leads, not SKU or sales proof."""
    from urllib.parse import quote
    q=quote('รีวิวสินค้า OR สินค้าใหม่ เครื่องใช้ในบ้าน OR อุปกรณ์ไอที')
    url=f'https://news.google.com/rss/search?q={q}&hl=th&gl=TH&ceid=TH:th'
    r=requests.get(url,headers={'User-Agent':'AffiliateAutoStudio/6.0','Accept':'application/rss+xml'},
                   timeout=(5,9),allow_redirects=False,stream=True)
    try:
        if r.status_code!=200: raise ValueError('Google News RSS HTTP '+str(r.status_code))
        raw=bytearray()
        for chunk in r.iter_content(32768):
            raw.extend(chunk)
            if len(raw)>MAX_BYTES: raise ValueError('RSS ใหญ่เกิน 1.5 MB')
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('ไม่รับ DOCTYPE/ENTITY')
        root=ET.fromstring(raw)
        out=[]
        for item in root.findall('.//item'):
            title=(item.findtext('title') or '').strip()[:150]
            if not title or not _relevance(title):continue
            link=_href(item.findtext('link') or '')
            if not link:continue
            out.append({'title':title,'source_name':'บทความจาก Google News RSS (ไม่ใช่ยอดขาย)',
                        'source_url':link,'category':'หัวข้อข่าวสินค้า / ต้องตรวจสอบรุ่น',
                        'trend_traffic':None,'score':15.0})
            if len(out)>=20:break
        return out
    finally:r.close()


def research_candidates(fetch_trends_fn=None):
    """Try live signals, then seed safely labeled research topics; never report them as sales."""
    sources=[]
    items=[]
    try:
        trends=(fetch_trends_fn or fetch_trends)()
        sources.append(f'Google Trends {len(trends)}')
        items.extend(trends)
    except (requests.RequestException, ET.ParseError, ValueError) as e:
        sources.append('Google Trends ติดต่อไม่ได้: '+str(e)[:100])
    if not items:
        try:
            news=fetch_product_news()
            sources.append(f'Google News {len(news)}')
            items.extend(news)
        except (requests.RequestException,ET.ParseError,ValueError) as e:
            sources.append('Google News ติดต่อไม่ได้: '+str(e)[:100])
    if not items:
        items=research_topics()
        sources.append('แสดงไอเดียสินค้าเริ่มต้นแทน; ไม่มีหลักฐานยอดขาย')
    return items, ' | '.join(sources)


def _href(url, platform='external'):
    u = str(url or '').strip()[:900]
    p = urlparse(u)
    if not u or p.scheme != 'https' or not p.hostname or p.username or p.password:
        return ''
    host = p.hostname.lower()
    if platform == 'tiktok' and not (host=='tiktok.com' or host.endswith('.tiktok.com')):
        return ''
    if platform == 'shopee' and not (host=='shopee.co.th' or host.endswith('.shopee.co.th')):
        return ''
    if platform == 'external' and (host in ('localhost','localhost.localdomain') or host.endswith('.local')):
        return ''
    return u


def _traffic(raw):
    s = str(raw or '').replace(',','').replace('+','').strip().upper()
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMB]?)$', s)
    if not match:
        return None
    n = float(match.group(1))*{'':1,'K':1_000,'M':1_000_000,'B':1_000_000_000}[match.group(2)]
    return int(n) if n<1_000_000_000_000 else None


def _relevance(title):
    title = title.casefold()
    if any(x in title for x in STOP_WORDS):
        return False
    return any(x in title for x in PRODUCT_WORDS)


def _rank(traffic):
    if traffic is None:
        return 20.0
    return round(min(95, 20 + 15*math.log10(traffic+1)), 1)


def parse_google_trends(xml_bytes):
    if b'<!DOCTYPE' in xml_bytes.upper() or b'<!ENTITY' in xml_bytes.upper():
        raise ValueError('RSS ไม่รองรับ DOCTYPE/ENTITY')
    root = ET.fromstring(xml_bytes)
    result=[]
    for item in root.findall('.//item'):
        title=(item.findtext('title') or '').strip()[:150]
        if not _relevance(title):
            continue
        traffic = None
        for elem in item:
            if elem.tag.endswith('approx_traffic'):
                traffic = _traffic(elem.text)
        link=(item.findtext('link') or '').strip()
        result.append({'title':title,'source_name':'Google Trends Thailand (RSS)',
                       'source_url':_href(link) or 'https://trends.google.com/trending?geo=TH',
                       'trend_traffic':traffic,'category':'คำค้นสินค้าที่กำลังเป็นกระแส'})
    return result[:MAX_RECORDS]


def fetch_trends():
    # Fixed, public source: no arbitrary URLs / cookies / account credentials.
    r = requests.get(TRENDS_RSS, headers={'User-Agent':'AffiliateAutoStudio/3.0','Accept':'application/rss+xml,application/xml'},
                     timeout=(5, 18), allow_redirects=False, stream=True)
    try:
        if r.status_code != 200:
            raise ValueError(f'Google Trends ตอบ HTTP {r.status_code}')
        raw = bytearray()
        for chunk in r.iter_content(32768):
            raw.extend(chunk)
            if len(raw)>MAX_BYTES:
                raise ValueError('RSS ขนาดเกิน 1.5 MB')
        return parse_google_trends(bytes(raw))
    finally:
        r.close()


class Match(BaseModel):
    tiktok_link: str = Field(default='',max_length=900)
    shopee_link: str = Field(default='',max_length=900)
    confirmed_tiktok: bool = False
    confirmed_shopee: bool = False
    features: str = Field(default='',max_length=700)
    audience: str = Field(default='',max_length=200)


class ExternalNew(BaseModel):
    title: str = Field(min_length=2,max_length=150)
    source_name: str = Field(default='เว็บภายนอกที่ผู้ใช้เลือก',max_length=140)
    source_url: str = Field(min_length=10,max_length=900)
    category: str = Field(default='',max_length=130)


def mount_external(app, connect, stamp, local_script):
    with connect() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS external_candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            trend_traffic INTEGER,
            score REAL NOT NULL,
            discovered_at TEXT NOT NULL,
            tiktok_link TEXT NOT NULL DEFAULT '',
            shopee_link TEXT NOT NULL DEFAULT '',
            confirmed_tiktok INTEGER NOT NULL DEFAULT 0,
            confirmed_shopee INTEGER NOT NULL DEFAULT 0,
            features TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '',
            product_id INTEGER, draft_id INTEGER,
            UNIQUE(title,source_name)
          );
          CREATE TABLE IF NOT EXISTS external_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,source TEXT NOT NULL,
            found INTEGER NOT NULL,message TEXT NOT NULL DEFAULT ''
          );
        ''')

    def put(items):
        count=0
        with connect() as db:
            for item in items[:MAX_RECORDS]:
                title=str(item.get('title','')).strip()[:150]
                src=str(item.get('source_name','')).strip()[:140]
                url=_href(item.get('source_url'))
                if len(title)<2 or not src or not url:
                    continue
                tr=item.get('trend_traffic')
                if tr is not None and (not isinstance(tr,int) or tr<0):
                    tr=None
                db.execute('''INSERT INTO external_candidates(title,source_name,source_url,category,trend_traffic,score,discovered_at)
                  VALUES (?,?,?,?,?,?,?) ON CONFLICT(title,source_name) DO UPDATE SET
                  source_url=excluded.source_url,category=excluded.category,
                  trend_traffic=excluded.trend_traffic,score=excluded.score,discovered_at=excluded.discovered_at''',
                  (title,src,url,str(item.get('category',''))[:130],tr,float(item.get('score',_rank(tr))),stamp()))
                count+=1
        return count

    def log(source,found,message=''):
        with connect() as db:
            db.execute('INSERT INTO external_runs(at,source,found,message) VALUES (?,?,?,?)',
                       (stamp(),source,found,str(message)[:500]))

    def scan():
        if not LOCK.acquire(blocking=False):
            raise HTTPException(409,'กำลังค้นหาอยู่ รอสักครู่')
        try:
            try:
                items, details=research_candidates()
                count=put(items)
                log('Product Radar / multiple sources',count,details)
                return {'imported':count,'fetched':len(items),'source':'Product Radar / multi-source',
                        'note':'ข่าว, กระแส หรือไอเดียสินค้า ไม่ใช่ยอดขายหรือสิทธิ์ Affiliate',
                        'details':details}
            except (requests.RequestException, ET.ParseError, ValueError) as e:
                log('Google Trends RSS',0,str(e))
                raise HTTPException(502,'ดึงข้อมูล Google Trends ไม่สำเร็จ: '+str(e)[:180])
        finally:
            LOCK.release()

    @app.get('/api/external/status')
    def status():
        with connect() as db:
            total=db.execute('SELECT COUNT(*) FROM external_candidates').fetchone()[0]
            latest=db.execute('SELECT * FROM external_runs ORDER BY id DESC LIMIT 1').fetchone()
        return {'count':total,'latest':dict(latest) if latest else None,
                'automatic_source':'Google Trends → Google News → ไอเดียสำรอง (ไม่ใช่ยอดขาย)','affiliates_connected':False,
                'marketplace_verification':'manual_only',
                'warning':'ยอดค้นหาใน Google ไม่ใช่ยอดขาย และลิงก์ที่ยืนยันเป็นข้อมูลที่ผู้ใช้ตรวจเอง'}

    @app.get('/api/external')
    def entries(query:str='',state:str='all',limit:int=100):
        if state not in ('all','unreviewed','matched'):
            raise HTTPException(400,'สถานะไม่ถูกต้อง')
        sql='SELECT * FROM external_candidates WHERE 1=1'; params=[]
        if query.strip():
            sql+=' AND (title LIKE ? OR category LIKE ?)'
            params += [f'%{query.strip()[:100]}%']*2
        if state=='unreviewed':
            sql+=' AND confirmed_tiktok=0 AND confirmed_shopee=0'
        if state=='matched':
            sql+=' AND (confirmed_tiktok=1 OR confirmed_shopee=1)'
        sql+=' ORDER BY score DESC, id DESC LIMIT ?'; params.append(max(1,min(300,limit)))
        with connect() as db:
            return [dict(row) for row in db.execute(sql,params).fetchall()]

    @app.post('/api/external/scan')
    def scan_now():
        return scan()

    @app.post('/api/external/manual')
    def add_one(body: ExternalNew):
        u=_href(body.source_url)
        if not u:
            raise HTTPException(400,'ลิงก์แหล่งข้อมูลต้องเป็น HTTPS ที่ถูกต้อง')
        count=put([{'title':body.title,'source_name':body.source_name or 'เว็บภายนอก',
                    'source_url':u,'category':body.category}])
        log('manual_external',count)
        return {'count':count}

    @app.post('/api/external/import')
    async def import_csv(file:UploadFile=File(...)):
        if not file.filename or not file.filename.lower().endswith('.csv'):
            raise HTTPException(400,'รับเฉพาะไฟล์ CSV')
        raw=await file.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise HTTPException(413,'ไฟล์ CSV ใหญ่เกินไป')
        try:
            parsed=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            if len(parsed)>MAX_RECORDS:
                raise ValueError('ได้ไม่เกิน 300 รายการต่อไฟล์')
            items=[{'title':r.get('title') or r.get('ชื่อสินค้า'),
                    'source_name':r.get('source_name') or 'รายการสินค้าจากเว็บภายนอก',
                    'source_url':r.get('source_url') or '',
                    'category':r.get('category') or ''} for r in parsed]
        except (UnicodeError,csv.Error,ValueError) as e:
            raise HTTPException(400,'อ่าน CSV ไม่ได้: '+str(e))
        count=put(items)
        log('manual_csv',count)
        return {'imported':count,'skipped':len(parsed)-count}

    @app.patch('/api/external/{eid}/match')
    def match(eid:int,body:Match):
        tt=_href(body.tiktok_link,'tiktok') if body.tiktok_link else ''
        sp=_href(body.shopee_link,'shopee') if body.shopee_link else ''
        if body.tiktok_link and not tt:
            raise HTTPException(400,'TikTok ต้องเป็นลิงก์ HTTPS บนโดเมน tiktok.com')
        if body.shopee_link and not sp:
            raise HTTPException(400,'Shopee ต้องเป็นลิงก์ HTTPS บนโดเมน shopee.co.th')
        if (body.confirmed_tiktok and not tt) or (body.confirmed_shopee and not sp):
            raise HTTPException(400,'ต้องมีลิงก์สินค้าของแพลตฟอร์มก่อนกดยืนยัน')
        with connect() as db:
            old=db.execute('SELECT id,product_id FROM external_candidates WHERE id=?',(eid,)).fetchone()
            if not old:
                raise HTTPException(404,'ไม่พบรายการ')
            db.execute('''UPDATE external_candidates SET tiktok_link=?,shopee_link=?,
                        confirmed_tiktok=?,confirmed_shopee=?,features=?,audience=? WHERE id=?''',
                       (tt,sp,int(body.confirmed_tiktok),int(body.confirmed_shopee),body.features.strip(),body.audience.strip(),eid))
            if old['product_id']:
                db.execute('UPDATE products SET tiktok_link=?,shopee_link=?,features=?,audience=? WHERE id=?',
                           (tt if body.confirmed_tiktok else '',sp if body.confirmed_shopee else '',
                            body.features.strip(),body.audience.strip(),old['product_id']))
        return {'ok':True,'matched_platforms':[p for p,v in [('tiktok',body.confirmed_tiktok),('shopee',body.confirmed_shopee)] if v]}

    @app.post('/api/external/{eid}/prepare')
    def prepare(eid:int):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute('SELECT * FROM external_candidates WHERE id=?',(eid,)).fetchone()
            if not r:
                raise HTTPException(404,'ไม่พบสินค้า')
            r=dict(r)
            platforms=[platform for platform,col in [('tiktok','confirmed_tiktok'),('shopee','confirmed_shopee')] if r[col]]
            if not platforms:
                raise HTTPException(412,'ต้องตรวจสอบสินค้าบน TikTok หรือ Shopee และบันทึกลิงก์ก่อน')
            if r['draft_id']:
                return {'created':False,'product_id':r['product_id'],'draft_id':r['draft_id']}
            if r['product_id']:
                pid=r['product_id']
            else:
                cur=db.execute('''INSERT INTO products(title,price,features,audience,tiktok_link,shopee_link,created_at)
                                  VALUES (?,?,?,?,?,?,?)''',
                               (r['title'],'',r['features'],r['audience'],r['tiktok_link'] if r['confirmed_tiktok'] else '',
                                r['shopee_link'] if r['confirmed_shopee'] else '',stamp()))
                pid=cur.lastrowid
            p=dict(db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone())
            script=local_script(p)
            cur=db.execute('''INSERT INTO drafts(product_id,hook,voiceover,caption,onscreen,video_prompt,created_at)
                              VALUES (?,?,?,?,?,?,?)''',
                            (pid,script['hook'],script['voiceover'],script['caption'],script['onscreen'],script['video_prompt'],stamp()))
            did=cur.lastrowid
            for platform in platforms:
                db.execute('INSERT INTO queue(draft_id,platform,created_at) VALUES (?,?,?)',(did,platform,stamp()))
            db.execute('UPDATE external_candidates SET product_id=?,draft_id=? WHERE id=?',(pid,did,eid))
        return {'created':True,'product_id':pid,'draft_id':did,'platforms':platforms}

    # Automatic RSS polling is strictly opt-in, while this local server is running.
    stop=threading.Event()
    def loop(minutes):
        while not stop.is_set():
            try:
                scan()
            except HTTPException:
                pass
            if stop.wait(minutes*60): break

    @app.on_event('startup')
    def begin():
        # The app opens with clearly marked starter *ideas*, not made-up top sellers.
        with connect() as db:
            count=db.execute('SELECT COUNT(*) FROM external_candidates').fetchone()[0]
        if count==0:
            put(research_topics())
            log('starter_ideas',len(SEED_RESEARCH_TOPICS),'หัวข้อค้นคว้าสำรอง ไม่ใช่สินค้าขายดี')
        def first_scan():
            try:scan()
            except HTTPException:pass
        threading.Thread(target=first_scan,daemon=True,name='initial-product-radar-scan').start()
        try: minutes=int(os.getenv('EXTERNAL_AUTO_SCAN_MINUTES','240') or 0)
        except ValueError: minutes=240
        if minutes>=60:
            stop.clear()
            # Wait one interval before next scan, since first_scan has run already.
            def periodic():
                while not stop.wait(minutes*60):
                    try:scan()
                    except HTTPException:pass
            threading.Thread(target=periodic,daemon=True,name='external-radar').start()

    @app.on_event('shutdown')
    def end():
        stop.set()
