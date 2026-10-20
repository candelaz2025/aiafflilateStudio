"""Attributable discovery of product *candidates*; no sales or affiliate claims.

Only calls fixed public search/RSS hosts; never requests user-supplied URLs.
A public marketplace search hit is NOT proof of a current listing or affiliation.
"""
from __future__ import annotations
import hashlib
import html
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode, urlsplit

import requests

MAX_BYTES = 850_000
CACHE_SECONDS = 120
_cache = {}
_lock = threading.Lock()
_gate = threading.BoundedSemaphore(4)
_ALLOWED_SOURCE_HOSTS = {'www.bing.com', 'news.google.com', 'api.search.brave.com', 'trends.google.com'}


def clean_url(raw):
    if not isinstance(raw, str) or len(raw) > 1800 or any(ord(c) < 32 for c in raw):
        return ''
    try:
        parts = urlsplit(raw.strip())
        host = (parts.hostname or '').lower().rstrip('.')
        if (parts.scheme != 'https' or not host or parts.username or parts.password
                or parts.port not in (None, 443) or host in ('localhost','127.0.0.1')):
            return ''
        return raw.strip()
    except ValueError:
        return ''


def platform_of(url):
    """Return candidate platform by official marketplace domains only."""
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    if host == 'shopee.co.th' or host.endswith('.shopee.co.th'):
        return 'shopee'
    if host == 'shop.tiktok.com' or host.endswith('.shop.tiktok.com'):
        return 'tiktok'
    if host in ('tiktok.com','www.tiktok.com') and ('/view/product/' in url or '/shop/' in url):
        return 'tiktok'
    return 'other'


def text_only(value, limit=220):
    return html.unescape(re.sub(r'<[^>]+>', ' ', value or '')).strip()[:limit]


def fetch(endpoint, params, token=None):
    host = (urlsplit(endpoint).hostname or '').lower()
    if host not in _ALLOWED_SOURCE_HOSTS or urlsplit(endpoint).scheme != 'https':
        raise ValueError('Source host not allowed')
    headers={'User-Agent':'AffiliateAutoStudio/7.5 (+product-research)','Accept':'application/rss+xml, application/json'}
    if token: headers['X-Subscription-Token']=token
    response=requests.get(endpoint,params=params,headers=headers,timeout=(3,6),allow_redirects=False,stream=True)
    try:
        if response.status_code != 200:
            raise ValueError('HTTP '+str(response.status_code))
        raw=bytearray()
        for chunk in response.iter_content(32768):
            raw.extend(chunk)
            if len(raw)>MAX_BYTES:
                raise ValueError('Source response too large')
        return bytes(raw)
    finally:
        response.close()


def _parse_rss(raw):
    if b'<!doctype' in raw.lower() or b'<!entity' in raw.lower():
        raise ValueError('Unsupported RSS DTD')
    root=ET.fromstring(raw)
    items=[]
    for item in root.findall('.//item')[:25]:
        title=text_only(item.findtext('title'),180)
        link=clean_url(item.findtext('link') or '')
        if title and link:
            items.append((title,link,text_only(item.findtext('description'),260)))
    return items


def _result(title,url,description,provider,kind=None):
    url=clean_url(url)
    if not url: return None
    platform=platform_of(url)
    kind=kind or ('marketplace_candidate' if platform != 'other' else 'article_lead')
    if kind == 'marketplace_candidate' and platform == 'other':
        kind='article_lead'
    mention = bool(re.search(r'extra[\s-]*comm|ค่าคอม(?:มิชชั่น)?พิเศษ', f'{title} {description}', re.I))
    return dict(title=text_only(title,180),url=url,description=text_only(description,240),
                platform=platform,kind=kind,source=provider,sales_verified=False,
                affiliate_verified=False,extra_comm_mentioned=(platform == 'shopee' and mention),
                extra_comm_verified=False,price=None,commission=None)


def search_public(query, extra_comm_only=False):
    """Public RSS; source might block requests. Always report failures, never synthesize hits."""
    items=[];sources=[]
    try:
        terms = f'{query} Extra Comm site:shopee.co.th' if extra_comm_only else f'{query} (site:shopee.co.th OR site:shop.tiktok.com)'
        raw=fetch('https://www.bing.com/search',{'format':'rss','q':terms,'setlang':'th-TH'})
        hits=_parse_rss(raw)
        for title,url,description in hits:
            candidate=_result(title,url,description,'Bing RSS · ค้นเว็บสาธารณะ')
            if candidate and candidate['platform']!='other' and (not extra_comm_only or candidate['extra_comm_mentioned']):items.append(candidate)
        sources.append({'name':'Bing RSS','status':'ok','found':len(items)})
    except (requests.RequestException,ValueError,ET.ParseError) as ex:
        sources.append({'name':'Bing RSS','status':'unavailable','message':str(ex)[:70]})
    if extra_comm_only:
        return items,sources
    try:
        raw=fetch('https://news.google.com/rss/search',
                  {'q':f'"{query}" รีวิว OR สินค้า','hl':'th','gl':'TH','ceid':'TH:th'})
        hits=_parse_rss(raw)
        n=0
        for title,url,description in hits:
            candidate=_result(title,url,description,'Google News · ข่าว/รีวิว')
            if candidate:
                candidate['kind']='article_lead'  # never use news articles as listing proof
                items.append(candidate);n+=1
        sources.append({'name':'Google News RSS','status':'ok','found':n})
    except (requests.RequestException,ValueError,ET.ParseError) as ex:
        sources.append({'name':'Google News RSS','status':'unavailable','message':str(ex)[:70]})
    return items,sources


def search_brave(query,token,extra_comm_only=False):
    if not token: return [],[]
    try:
        terms = f'{query} Extra Comm site:shopee.co.th' if extra_comm_only else f'{query} (site:shopee.co.th OR site:shop.tiktok.com OR site:thai.tiktok.com)'
        raw=fetch('https://api.search.brave.com/res/v1/web/search',
                  {'q':terms,
                   'country':'TH','search_lang':'th','count':15},token)
        import json
        data=json.loads(raw)
        items=[]
        for hit in data.get('web',{}).get('results',[])[:20]:
            if not isinstance(hit,dict):continue
            item=_result(hit.get('title',''),hit.get('url',''),hit.get('description',''),'Brave Search API')
            if item and item['platform']!='other' and (not extra_comm_only or item['extra_comm_mentioned']):items.append(item)
        return items,[{'name':'Brave Search API','status':'ok','found':len(items)}]
    except (requests.RequestException,ValueError,KeyError) as ex:
        return [],[{'name':'Brave Search API','status':'unavailable','message':str(ex)[:70]}]


def discover(query, token=None, extra_comm_only=False):
    query=re.sub(r'\s+',' ',query).strip()
    if len(query)<2 or len(query)>80 or any(ord(c)<32 for c in query):
        raise ValueError('กรอกชื่อสินค้าหรือคำค้น 2–80 ตัวอักษร')
    fingerprint=hashlib.sha256((token or '').encode()).hexdigest()[:12]
    key=(query.casefold(),fingerprint,bool(extra_comm_only))
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0] < CACHE_SECONDS:
            return dict(cached[1],cached=True)
        if len(_cache)>150:
            _cache.clear()
    if not _gate.acquire(blocking=False):
        raise RuntimeError('ระบบค้นหากำลังมีงานจำนวนมาก โปรดลองใหม่อีกครั้ง')
    try:
        brave,brave_sources=search_brave(query,token,extra_comm_only=extra_comm_only)
        public,public_sources=search_public(query,extra_comm_only=extra_comm_only)
        unique={}
        for hit in brave+public:
            if hit['url'] not in unique:
                unique[hit['url']]=hit
        items=list(unique.values())
        items.sort(key=lambda i: 0 if i['kind']=='marketplace_candidate' else 1)
        output={'query':query,'items':items[:35], 'sources':brave_sources+public_sources,
                'listing_candidates':sum(i['kind']=='marketplace_candidate' for i in items[:35]),
                'note':'ผลจากเว็บเป็นเพียงลิงก์สินค้าอาจตรงรุ่น/ข่าวรีวิว ไม่ยืนยันยอดขาย ราคา ค่าคอม หรือสิทธิ์ Affiliate',
                'has_brave_key':bool(token),'cached':False, 'extra_comm_mode':bool(extra_comm_only),
                'extra_comm_note':'ผลเว็บที่กล่าวถึง EXTRA COMM เป็นเพียงเบาะแส ไม่ยืนยันเรทหรือสิทธิ์ ต้องเช็กผ่าน Shopee Affiliate ของบัญชีตัวเอง',
                'official_guide':'https://help.shopee.co.th/portal/10/article/123905',
                'search_links':{
                   'shopee':'https://shopee.co.th/search?'+urlencode({'keyword':query}),
                   'tiktok':'https://www.google.com/search?'+urlencode({'q':'site:shop.tiktok.com '+query})}}
        with _lock:_cache[key]=(time.monotonic(),output)
        return output
    finally:
        _gate.release()

# Terms indicate broad product categories only, not brands, listings, or sales.
PRODUCT_HINTS = ('พัดลม','แก้ว','หูฟัง','หม้อทอด','กระเป๋า','ครีม','กันแดด','เครื่องฟอก',
                 'ดูดฝุ่น','สมาร์ท','มือถือ','เครื่องชงกาแฟ','โต๊ะ','เก้าอี้','รองเท้า',
                 'เครื่องสำอาง','กล้อง','ชาร์จ','ของใช้','อุปกรณ์ครัว','น้ำหอม',
                 'air fryer','power bank','headphone','vacuum','sunscreen')


def trending_topics():
    """Find actual product-related search topics, never assume a product is selling."""
    topics=[];sources=[];seen=set()
    feeds=[('Google Trends Thailand','https://trends.google.com/trending/rss',{'geo':'TH'}),
           ('Google News สินค้า','https://news.google.com/rss/search',
             {'q':'สินค้าใหม่ รีวิวแก็ดเจ็ต เครื่องใช้ในบ้าน','hl':'th','gl':'TH','ceid':'TH:th'})]
    for source,endpoint,params in feeds:
        try:
            raw=fetch(endpoint,params)
            entries=_parse_rss(raw)
            added=0
            for title,url,desc in entries:
                lower=title.casefold()
                term=next((w for w in PRODUCT_HINTS if w in lower),None)
                if not term:continue
                label=title if source.startswith('Google Trends') else term
                normalized=label.casefold()
                if normalized in seen:continue
                seen.add(normalized)
                topics.append({'keyword':label[:80], 'source':source,'url':url,
                               'kind':'trend_keyword' if source.startswith('Google Trends') else 'news_topic',
                               'sales_verified':False})
                added+=1
                if len(topics)>=24:break
            sources.append({'name':source,'status':'ok','found':added})
        except (requests.RequestException,ValueError,ET.ParseError) as exc:
            sources.append({'name':source,'status':'unavailable','message':str(exc)[:70]})
    return {'topics':topics[:24],'sources':sources,'note':'คำค้นที่พบจากกระแสหรือข่าว ไม่ใช่ยอดขาย และยังไม่ใช่รายการสินค้าของร้านค้า'}
