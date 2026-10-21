"""Shopee Affiliate Open API (Thailand) client — official, signed GraphQL.

Auth: Authorization: SHA256 Credential={AppId}, Timestamp={ts}, Signature={sha256(AppId+ts+payload+Secret)}
Endpoint: https://open-api.affiliate.shopee.co.th/graphql
Members obtain AppID/Secret themselves at affiliate.shopee.co.th → Open API. No scraping, no login.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from urllib.parse import urlsplit

import requests

TIMEOUT = 20
SHOPEE_HOSTS = {'shopee.co.th', 'www.shopee.co.th', 's.shopee.co.th', 'shp.ee', 'shope.ee'}
SHORT_HOSTS = {'s.shopee.co.th', 'shp.ee', 'shope.ee'}

NODE_FIELDS = ('itemId commissionRate sellerCommissionRate shopeeCommissionRate commission sales '
               'priceMax priceMin ratingStar priceDiscountRate imageUrl productName shopId shopName '
               'shopType productLink offerLink periodStartTime periodEndTime')

SORT_TYPES = {'relevance': 1, 'sales': 2, 'price_desc': 3, 'price_asc': 4, 'commission': 5}


class ShopeeError(Exception):
    pass


def endpoint() -> str:
    return os.getenv('SHOPEE_AFFILIATE_ENDPOINT', 'https://open-api.affiliate.shopee.co.th/graphql')


def _headers(app_id: str, secret: str, payload: str) -> dict:
    ts = int(time.time())
    sig = hashlib.sha256(f'{app_id}{ts}{payload}{secret}'.encode()).hexdigest()
    return {'Content-Type': 'application/json',
            'Authorization': f'SHA256 Credential={app_id}, Timestamp={ts}, Signature={sig}'}


def graphql(app_id: str, secret: str, query: str, variables: dict | None = None) -> dict:
    body = {'query': query}
    if variables:
        body['variables'] = variables
    payload = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    try:
        r = requests.post(endpoint(), data=payload.encode(), headers=_headers(app_id, secret, payload), timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ShopeeError(f'เชื่อมต่อ Shopee Affiliate API ไม่ได้: {e.__class__.__name__}')
    try:
        data = r.json()
    except ValueError:
        raise ShopeeError(f'Shopee ตอบกลับไม่ใช่ JSON (HTTP {r.status_code})')
    if data.get('errors'):
        e = data['errors'][0]
        code = (e.get('extensions') or {}).get('code')
        hint = {10020: 'AppID/Secret ไม่ถูกต้อง หรือเวลาเครื่องคลาดเคลื่อน', 10030: 'เรียก API ถี่เกินกำหนด ลองใหม่ภายหลัง',
                10035: 'บัญชียังไม่ได้รับสิทธิ์ Open API'}.get(code, '')
        raise ShopeeError(f'Shopee API: {e.get("message", "error")}{" — " + hint if hint else ""}'[:400])
    if r.status_code >= 400:
        raise ShopeeError(f'Shopee API HTTP {r.status_code}')
    return data.get('data') or {}


def _num(v):
    try:
        return float(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _rate_pct(v):
    """Shopee returns rates as fractions ("0.07"); show as percent. Values >1 are already percent."""
    x = _num(v)
    if x is None:
        return None
    return round(x * 100, 2) if x <= 1 else round(x, 2)


def normalize(node: dict) -> dict:
    pmin, pmax = _num(node.get('priceMin')), _num(node.get('priceMax'))
    return {
        'item_id': str(node.get('itemId') or ''),
        'shop_id': str(node.get('shopId') or ''),
        'title': (node.get('productName') or '').strip()[:200],
        'image_url': node.get('imageUrl') or '',
        'price_min': pmin, 'price_max': pmax,
        'price': pmin if pmin is not None else pmax,
        'commission_rate': _rate_pct(node.get('commissionRate')),
        'seller_comm_rate': _rate_pct(node.get('sellerCommissionRate')),
        'shopee_comm_rate': _rate_pct(node.get('shopeeCommissionRate')),
        'commission_baht': _num(node.get('commission')),
        'sales': int(_num(node.get('sales')) or 0),
        'rating': _num(node.get('ratingStar')),
        'discount_rate': _num(node.get('priceDiscountRate')),
        'shop_name': node.get('shopName') or '',
        'product_link': node.get('productLink') or '',
        'offer_link': node.get('offerLink') or '',
        'period_end': node.get('periodEndTime'),
        'source': 'shopee_affiliate_api',
    }


def product_offers(app_id, secret, *, keyword='', shop_id=None, item_id=None, sort='commission', page=1, limit=20) -> dict:
    args = [f'page:{int(page)}', f'limit:{max(1, min(int(limit), 50))}']
    if keyword:
        args.append(f'keyword:{json.dumps(keyword[:120], ensure_ascii=False)}')
    if shop_id:
        args.append(f'shopId:{int(shop_id)}')
    if item_id:
        args.append(f'itemId:{int(item_id)}')
    args.append(f'sortType:{SORT_TYPES.get(sort, 5)}')
    q = '{productOfferV2(%s){nodes{%s} pageInfo{page limit hasNextPage}}}' % (','.join(args), NODE_FIELDS)
    data = graphql(app_id, secret, q).get('productOfferV2') or {}
    return {'items': [normalize(n) for n in data.get('nodes') or []], 'page_info': data.get('pageInfo') or {}}


def short_link(app_id, secret, origin_url: str, sub_ids: list[str] | None = None) -> str:
    sub = ''
    if sub_ids:
        sub = ',subIds:' + json.dumps([re.sub(r'[^A-Za-z0-9]', '', s)[:50] for s in sub_ids[:5]])
    q = 'mutation{generateShortLink(input:{originUrl:%s%s}){shortLink}}' % (json.dumps(origin_url), sub)
    return ((graphql(app_id, secret, q).get('generateShortLink')) or {}).get('shortLink') or ''


def is_shopee_url(raw: str) -> bool:
    try:
        p = urlsplit(raw.strip())
    except ValueError:
        return False
    return (p.scheme == 'https' and (p.hostname or '').lower() in SHOPEE_HOSTS
            and not p.username and not p.password and p.port in (None, 443))


def parse_ids(url: str):
    """Return (shop_id, item_id) from a full Shopee product URL, else (None, None)."""
    path = urlsplit(url).path
    for pat in (r'-i\.(\d+)\.(\d+)', r'/product/(\d+)/(\d+)', r'/[^/]+/(\d+)/(\d+)/?$'):
        m = re.search(pat, path)
        if m:
            return m.group(1), m.group(2)
    m = re.search(r'[?&]shopid=(\d+).*?[?&]itemid=(\d+)', url, re.I)
    if m:
        return m.group(1), m.group(2)
    return None, None


def resolve_short(url: str, max_hops: int = 5) -> str:
    """Follow redirects of a Shopee short link, never leaving Shopee hosts."""
    current = url
    for _ in range(max_hops):
        if not is_shopee_url(current):
            raise ShopeeError('ลิงก์ redirect ออกนอกโดเมน Shopee')
        host = (urlsplit(current).hostname or '').lower()
        if host not in SHORT_HOSTS:
            return current
        try:
            r = requests.get(current, allow_redirects=False, timeout=TIMEOUT,
                             headers={'User-Agent': 'AffiliateAutoStudio/8 (+link-resolver)'})
        except requests.RequestException as e:
            raise ShopeeError(f'เปิดลิงก์สั้นไม่ได้: {e.__class__.__name__}')
        loc = r.headers.get('Location')
        if not loc:
            return current
        if loc.startswith('/'):
            loc = f'https://{host}{loc}'
        current = loc
    return current


def ids_from_link(url: str):
    if not is_shopee_url(url):
        raise ShopeeError('รองรับเฉพาะลิงก์ Shopee ประเทศไทย (shopee.co.th / s.shopee.co.th / shp.ee)')
    shop_id, item_id = parse_ids(url)
    if not item_id and (urlsplit(url).hostname or '').lower() in SHORT_HOSTS:
        shop_id, item_id = parse_ids(resolve_short(url))
    if not item_id:
        raise ShopeeError('อ่านรหัสสินค้าจากลิงก์ไม่ได้ ลองคัดลอกลิงก์จากหน้าสินค้าโดยตรง (มี -i.ร้าน.สินค้า)')
    return shop_id, item_id
