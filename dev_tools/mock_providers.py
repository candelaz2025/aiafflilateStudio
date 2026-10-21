"""Local stand-in for Meta (Facebook/Instagram), LINE Messaging API and Shopee Affiliate Open API.

For E2E testing only. Run:
  uvicorn dev_tools.mock_providers:app --port 9100
and start the studio with:
  META_DIALOG_BASE=http://127.0.0.1:9100/fb META_GRAPH_BASE=http://127.0.0.1:9100/graph \
  IG_AUTH_BASE=http://127.0.0.1:9100/igauth IG_API_BASE=http://127.0.0.1:9100/igapi \
  IG_GRAPH_BASE=http://127.0.0.1:9100/iggraph LINE_API_BASE=http://127.0.0.1:9100/line \
  SHOPEE_AFFILIATE_ENDPOINT=http://127.0.0.1:9100/shopee/graphql \
  META_APP_ID=111222333 META_APP_SECRET=mocksecret IG_APP_ID=444555666 IG_APP_SECRET=mockigsecret

Known-good test credentials:
  Shopee  AppID 15012345678  Secret MOCKSHOPEESECRET01
  LINE    Channel ID 1650000000  Secret 0123456789abcdef0123456789abcdef  (long-lived token: MOCK-LINE-LONG-TOKEN)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import time
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

app = FastAPI(title='Mock providers')
LOG: list[dict] = []

SHOPEE_APP_ID, SHOPEE_SECRET = '15012345678', 'MOCKSHOPEESECRET01'
LINE_CHANNEL_ID, LINE_SECRET = '1650000000', '0123456789abcdef0123456789abcdef'
LINE_LONG = 'MOCK-LINE-LONG-TOKEN'
LINE_TOKENS = {LINE_LONG}
BOT_USER = 'U' + 'a' * 32


def log(kind, **data):
    LOG.append({'t': time.time(), 'kind': kind, **data})


@app.get('/_log')
def get_log(kind: str = ''):
    return {'calls': [x for x in LOG if not kind or x['kind'].startswith(kind)][-200:]}


@app.delete('/_log')
def clear_log():
    LOG.clear()
    return {'ok': True}


def consent_page(title, approve_url, cancel_url, detail):
    return HTMLResponse(f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:sans-serif;max-width:420px;margin:60px auto;padding:20px;border:1px solid #ddd;border-radius:12px}}
a{{display:inline-block;padding:10px 18px;border-radius:8px;margin-right:8px;text-decoration:none}}
.ok{{background:#1877f2;color:#fff}}.no{{background:#eee;color:#333}}</style></head><body>
<h2>{html.escape(title)}</h2><p>{html.escape(detail)}</p>
<a class="ok" id="approve" href="{html.escape(approve_url)}">Continue / อนุญาต</a>
<a class="no" id="cancel" href="{html.escape(cancel_url)}">Cancel</a></body></html>''')


# ----------------------------------------------------------------- Facebook
PAGES = [
    {'id': '1010101010', 'name': 'ดีลเด็ดของใช้ในบ้าน', 'access_token': 'EAAPAGETOKEN1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 'category': 'Shopping & retail',
     'picture': {'data': {'url': 'https://example.com/p1.jpg'}},
     'instagram_business_account': {'id': '17841400000000001', 'username': 'deal_home_th', 'profile_picture_url': ''}},
    {'id': '2020202020', 'name': 'รีวิวแกดเจ็ตไอที', 'access_token': 'EAAPAGETOKEN2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 'category': 'Product/service',
     'picture': {'data': {'url': ''}}},
]


@app.get('/fb/{ver}/dialog/oauth')
def fb_dialog(ver: str, client_id: str, redirect_uri: str, state: str, scope: str = ''):
    log('fb.dialog', client_id=client_id, redirect_uri=redirect_uri, scope=scope)
    ok = redirect_uri + '?' + urlencode({'code': 'FBCODE-' + state[:6], 'state': state})
    no = redirect_uri + '?' + urlencode({'error': 'access_denied', 'error_description': 'Permissions error', 'state': state})
    return consent_page('Facebook (mock) — Affiliate Studio ต้องการเข้าถึงเพจของคุณ', ok, no, f'Scopes: {scope}')


@app.get('/graph/{ver}/oauth/access_token')
def fb_token(ver: str, client_id: str, client_secret: str, code: str = '', redirect_uri: str = '',
             grant_type: str = '', fb_exchange_token: str = ''):
    if client_secret != 'mocksecret':
        return JSONResponse({'error': {'message': 'Error validating client secret.', 'code': 1}}, 400)
    if grant_type == 'fb_exchange_token':
        return {'access_token': 'USER-LONG-' + fb_exchange_token[-6:], 'token_type': 'bearer', 'expires_in': 5184000}
    if not code.startswith('FBCODE-'):
        return JSONResponse({'error': {'message': 'Invalid verification code format.', 'code': 100}}, 400)
    log('fb.token', redirect_uri=redirect_uri)
    return {'access_token': 'USER-SHORT-' + code[-6:], 'token_type': 'bearer'}


@app.get('/graph/{ver}/me/accounts')
def fb_accounts(ver: str, access_token: str, fields: str = '', limit: int = 25):
    if not access_token.startswith('USER-LONG-'):
        return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)
    return {'data': PAGES}


def _page_tokens():
    return {p['access_token']: p for p in PAGES}


@app.get('/graph/{ver}/debug_token')
def fb_debug_token(ver: str, input_token: str, access_token: str):
    if input_token in _page_tokens():
        return {'data': {'type': 'PAGE', 'is_valid': True,
                         'scopes': ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts']}}
    if input_token.startswith('USER-'):
        return {'data': {'type': 'USER', 'is_valid': True, 'scopes': ['pages_show_list']}}
    return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)


@app.get('/graph/{ver}/me')
def fb_me(ver: str, access_token: str, fields: str = ''):
    toks = _page_tokens()
    if access_token not in toks:
        if access_token.startswith('USER-'):  # a user token has no `category`
            return JSONResponse({'error': {'message': '(#100) Tried accessing nonexisting field (category)', 'code': 100}}, 400)
        return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)
    p = toks[access_token]
    log('fb.me', page=p['id'])
    out = {'id': p['id'], 'name': p['name'], 'category': p['category'], 'picture': p['picture']}
    ig = p.get('instagram_business_account')
    if ig:
        out['instagram_business_account'] = ig
    return out


@app.get('/graph/{ver}/{obj_id}')
def fb_object(ver: str, obj_id: str, access_token: str, fields: str = ''):
    toks = _page_tokens()
    if obj_id.startswith('container') and access_token in toks:
        return {'id': obj_id, 'status_code': 'FINISHED'}
    if access_token not in toks:
        return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)
    for p in PAGES:
        if p['id'] == obj_id:
            return {'id': obj_id, 'name': p['name'], 'fan_count': 1520, 'followers_count': 1610}
        ig = p.get('instagram_business_account')
        if ig and ig['id'] == obj_id:
            return {'id': obj_id, 'username': ig['username'], 'followers_count': 980, 'media_count': 42}
    return JSONResponse({'error': {'message': 'Unsupported get request.', 'code': 100}}, 400)


@app.delete('/graph/{ver}/{obj_id}')
def fb_delete(ver: str, obj_id: str, access_token: str):
    if access_token not in _page_tokens():
        return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)
    log('fb.delete', obj=obj_id)
    return {'success': True}


@app.post('/graph/{ver}/{obj_id}/{edge}')
async def fb_post(ver: str, obj_id: str, edge: str, request: Request):
    raw_form = await request.form()
    form = {k: (f'<file {v.filename} {len(await v.read())} bytes>' if hasattr(v, 'filename') else v) for k, v in raw_form.items()}
    if form.get('access_token') not in _page_tokens():
        return JSONResponse({'error': {'message': 'Invalid OAuth access token.', 'code': 190}}, 400)
    log(f'fb.{edge}', obj=obj_id, **{k: v for k, v in form.items() if k != 'access_token'})
    n = int(time.time() * 1000) % 10 ** 9
    if edge == 'photos':
        return {'id': f'ph{n}', 'post_id': f'{obj_id}_{n}'}
    if edge == 'feed':
        return {'id': f'{obj_id}_{n}'}
    if edge == 'videos':
        if not str(form.get('source', '')).startswith('<file'):
            return JSONResponse({'error': {'message': 'No video file', 'code': 100}}, 400)
        return {'id': f'vid{n}'}
    if edge == 'media':
        if not (str(form.get('image_url', '')).startswith('https://') or str(form.get('video_url', '')).startswith('https://')):
            return JSONResponse({'error': {'message': 'Only photo or video can be accepted as media type.', 'code': 9004}}, 400)
        return {'id': f'container{n}'}
    if edge == 'media_publish':
        return {'id': f'igmedia{n}'}
    return JSONResponse({'error': {'message': 'Unknown edge'}}, 400)


# ----------------------------------------------------------------- Instagram Login
@app.get('/igauth/oauth/authorize')
def ig_authorize(client_id: str, redirect_uri: str, state: str, scope: str = '', response_type: str = 'code'):
    log('ig.dialog', client_id=client_id, redirect_uri=redirect_uri, scope=scope)
    ok = redirect_uri + '?' + urlencode({'code': 'IGCODE-' + state[:6], 'state': state}) + '#_'
    no = redirect_uri + '?' + urlencode({'error': 'access_denied', 'error_reason': 'user_denied',
                                         'error_description': 'The user denied your request.', 'state': state})
    return consent_page('Instagram (mock) — อนุญาตให้ Affiliate Studio โพสต์', ok, no, f'Scopes: {scope}')


@app.post('/igapi/oauth/access_token')
def ig_token(client_id: str = Form(...), client_secret: str = Form(...), grant_type: str = Form(...),
             redirect_uri: str = Form(...), code: str = Form(...)):
    if client_secret != 'mockigsecret' or not code.startswith('IGCODE-'):
        return JSONResponse({'error_type': 'OAuthException', 'code': 400, 'error_message': 'Invalid authorization code'}, 400)
    return {'data': [{'access_token': 'IG-SHORT-' + code[-6:], 'user_id': '17841499999999999', 'permissions': 'instagram_business_basic'}]}


@app.get('/iggraph/access_token')
def ig_long(grant_type: str, client_secret: str, access_token: str):
    return {'access_token': 'IG-LONG-' + access_token[-6:], 'token_type': 'bearer', 'expires_in': 5183944}


@app.get('/iggraph/refresh_access_token')
def ig_refresh(grant_type: str, access_token: str):
    return {'access_token': access_token, 'token_type': 'bearer', 'expires_in': 5183944}


@app.get('/iggraph/{ver}/me')
def ig_me(ver: str, access_token: str, fields: str = ''):
    if not access_token.startswith('IG-LONG-'):
        return JSONResponse({'error': {'message': 'Invalid OAuth access token', 'code': 190}}, 400)
    return {'user_id': '17841499999999999', 'username': 'kevin.creator.th', 'profile_picture_url': '', 'account_type': 'BUSINESS'}


@app.get('/iggraph/{ver}/{obj_id}')
def ig_obj(ver: str, obj_id: str, access_token: str, fields: str = ''):
    if not access_token.startswith('IG-LONG-'):
        return JSONResponse({'error': {'message': 'Invalid OAuth access token', 'code': 190}}, 400)
    if obj_id.startswith('container'):
        return {'id': obj_id, 'status_code': 'FINISHED'}
    return {'id': obj_id, 'username': 'kevin.creator.th', 'followers_count': 2300, 'media_count': 18}


@app.post('/iggraph/{ver}/{obj_id}/{edge}')
async def ig_post(ver: str, obj_id: str, edge: str, request: Request):
    form = dict(await request.form())
    if not str(form.get('access_token', '')).startswith('IG-LONG-'):
        return JSONResponse({'error': {'message': 'Invalid OAuth access token', 'code': 190}}, 400)
    log(f'ig.{edge}', obj=obj_id, **{k: v for k, v in form.items() if k != 'access_token'})
    n = int(time.time() * 1000) % 10 ** 9
    if edge == 'media':
        if not (str(form.get('image_url', '')).startswith('https://') or str(form.get('video_url', '')).startswith('https://')):
            return JSONResponse({'error': {'message': 'Only photo or video can be accepted as media type.'}}, 400)
        return {'id': f'container{n}'}
    return {'id': f'igmedia{n}'}


# ----------------------------------------------------------------- LINE
def line_auth(authorization: str | None):
    tok = (authorization or '').removeprefix('Bearer ').strip()
    if tok not in LINE_TOKENS:
        raise HTTPException(401, detail='Authentication failed. Confirm that the access token in the authorization header is valid.')
    return tok


@app.exception_handler(HTTPException)
async def line_style_errors(request: Request, exc: HTTPException):
    return JSONResponse({'message': exc.detail}, exc.status_code)


@app.post('/line/v2/oauth/accessToken')
def line_issue(grant_type: str = Form(...), client_id: str = Form(...), client_secret: str = Form(...)):
    if client_id != LINE_CHANNEL_ID or client_secret != LINE_SECRET:
        return JSONResponse({'error': 'invalid_client', 'error_description': 'invalid client_id or client_secret'}, 400)
    tok = f'MOCK-LINE-ISSUED-{int(time.time())}'
    LINE_TOKENS.add(tok)
    return {'access_token': tok, 'expires_in': 2592000, 'token_type': 'Bearer'}


@app.get('/line/v2/bot/info')
def line_info(authorization: str | None = Header(default=None)):
    line_auth(authorization)
    return {'userId': BOT_USER, 'basicId': '@123abcde', 'displayName': 'Affiliate Studio OA', 'pictureUrl': '',
            'chatMode': 'bot', 'markAsReadMode': 'auto'}


@app.get('/line/v2/bot/message/quota')
def line_quota(authorization: str | None = Header(default=None)):
    line_auth(authorization)
    return {'type': 'limited', 'value': 300}


@app.get('/line/v2/bot/message/quota/consumption')
def line_consumption(authorization: str | None = Header(default=None)):
    line_auth(authorization)
    return {'totalUsage': sum(1 for x in LOG if x['kind'] in ('line.push', 'line.broadcast'))}


@app.put('/line/v2/bot/channel/webhook/endpoint')
async def line_set_webhook(request: Request, authorization: str | None = Header(default=None)):
    line_auth(authorization)
    log('line.webhook_set', **(await request.json()))
    return {}


@app.post('/line/v2/bot/channel/webhook/test')
async def line_test_webhook(request: Request, authorization: str | None = Header(default=None)):
    line_auth(authorization)
    return {'success': True, 'timestamp': '2026-10-21T00:00:00Z', 'statusCode': 200, 'reason': 'OK', 'detail': '200'}


@app.post('/line/v2/bot/message/{kind}')
async def line_send(kind: str, request: Request, authorization: str | None = Header(default=None)):
    line_auth(authorization)
    body = await request.json()
    if kind == 'push' and not re.fullmatch(r'U[0-9a-f]{32}', str(body.get('to', ''))):
        return JSONResponse({'message': 'The property, \'to\', in the request body is invalid'}, 400)
    log(f'line.{kind}', **body)
    return {'sentMessages': [{'id': str(int(time.time() * 1000))}]}


@app.get('/line/v2/bot/profile/{uid}')
def line_profile(uid: str, authorization: str | None = Header(default=None)):
    line_auth(authorization)
    return {'userId': uid, 'displayName': 'Kevin (LINE)', 'pictureUrl': ''}


@app.post('/_line/follow')
async def simulate_follow(request: Request):
    """Simulate a user adding the OA + sending a message: signs and POSTs to the studio webhook."""
    d = await request.json()
    uid = d.get('user_id') or 'U' + 'b' * 32
    body = json.dumps({'destination': BOT_USER, 'events': [
        {'type': 'follow', 'source': {'type': 'user', 'userId': uid}, 'timestamp': int(time.time() * 1000)},
        {'type': 'message', 'source': {'type': 'user', 'userId': uid}, 'message': {'type': 'text', 'text': 'สวัสดี'},
         'replyToken': 'r' * 32, 'timestamp': int(time.time() * 1000)}]}).encode()
    sig = base64.b64encode(hmac.new(d.get('secret', LINE_SECRET).encode(), body, hashlib.sha256).digest()).decode()
    r = requests.post(d['webhook_url'], data=body, headers={'Content-Type': 'application/json', 'X-Line-Signature': sig}, timeout=10)
    return {'status': r.status_code, 'body': r.text[:300], 'user_id': uid}


# ----------------------------------------------------------------- Shopee Affiliate
CATALOG = [
    (24001001, 900001, 'พัดลมพกพาไร้ใบพัด ชาร์จ USB หมุน 360°', 159, 199, 0.12, 0.10, 0.02, 15230, 4.8, 'GadgetHome Official'),
    (24001002, 900001, 'พัดลมตั้งโต๊ะ 12 นิ้ว ปรับ 3 ระดับ เสียงเงียบ', 390, 450, 0.08, 0.06, 0.02, 4120, 4.7, 'GadgetHome Official'),
    (24001003, 900002, 'เครื่องดูดฝุ่นไร้สาย แรงดูด 12000Pa', 890, 1290, 0.15, 0.13, 0.02, 2210, 4.6, 'CleanPro TH'),
    (24001004, 900002, 'ไม้ถูพื้นสเปรย์ ถังรีดน้ำ 360°', 249, 249, 0.10, 0.07, 0.03, 9800, 4.9, 'CleanPro TH'),
    (24001005, 900003, 'หูฟังบลูทูธ TWS ตัดเสียงรบกวน ANC', 599, 799, 0.20, 0.18, 0.02, 6600, 4.5, 'SoundMax'),
    (24001006, 900003, 'ลำโพงบลูทูธพกพา กันน้ำ IPX7', 459, 459, 0.11, 0.09, 0.02, 3150, 4.6, 'SoundMax'),
    (24001007, 900004, 'เซรั่มวิตามินซี 30ml ผิวกระจ่างใส', 299, 399, 0.25, 0.22, 0.03, 21000, 4.8, 'GlowLab'),
    (24001008, 900004, 'ครีมกันแดด SPF50 PA++++ 50ml', 219, 219, 0.18, 0.15, 0.03, 18800, 4.9, 'GlowLab'),
    (24001009, 900005, 'กระติกน้ำเก็บอุณหภูมิ 1 ลิตร สแตนเลส 304', 189, 259, 0.09, 0.07, 0.02, 12500, 4.8, 'DrinkWare'),
    (24001010, 900005, 'แก้วเยติ 30oz พร้อมหลอด', 129, 129, 0.06, 0.04, 0.02, 30500, 4.7, 'DrinkWare'),
    (24001011, 900006, 'ไฟ LED เส้น RGB 5 เมตร ควบคุมผ่านแอป', 199, 299, 0.14, 0.12, 0.02, 7400, 4.6, 'LightUp'),
    (24001012, 900006, 'โคมไฟตั้งโต๊ะถนอมสายตา ชาร์จไร้สาย', 359, 459, 0.0, 0.0, 0.0, 860, 4.4, 'LightUp'),
]


def node(c):
    item, shop, name, pmin, pmax, rate, srate, prate, sales, star, shop_name = c
    return {'itemId': item, 'shopId': shop, 'productName': name, 'priceMin': str(pmin), 'priceMax': str(pmax),
            'commissionRate': str(rate), 'sellerCommissionRate': str(srate), 'shopeeCommissionRate': str(prate),
            'commission': str(round(pmin * rate, 2)), 'sales': sales, 'ratingStar': str(star), 'priceDiscountRate': 10,
            'imageUrl': f'https://cf.shopee.co.th/file/mock-{item}', 'shopName': shop_name, 'shopType': [1],
            'productLink': f'https://shopee.co.th/product/{shop}/{item}',
            'offerLink': f'https://s.shopee.co.th/mock{item}', 'periodStartTime': 1760000000, 'periodEndTime': 1790000000}


@app.post('/shopee/graphql')
async def shopee_graphql(request: Request, authorization: str | None = Header(default=None)):
    raw = (await request.body()).decode()
    m = re.fullmatch(r'SHA256 Credential=(\d+), Timestamp=(\d+), Signature=([0-9a-f]{64})', authorization or '')
    if not m:
        return {'errors': [{'message': 'Invalid Authorization Header', 'extensions': {'code': 10020}}]}
    app_id, ts, sig = m.groups()
    expected = hashlib.sha256(f'{app_id}{ts}{raw}{SHOPEE_SECRET}'.encode()).hexdigest()
    if app_id != SHOPEE_APP_ID or not hmac.compare_digest(sig, expected) or abs(time.time() - int(ts)) > 600:
        return {'errors': [{'message': 'Invalid Signature', 'extensions': {'code': 10020}}]}
    q = json.loads(raw)['query']
    log('shopee.graphql', query=q[:300])
    if 'generateShortLink' in q:
        return {'data': {'generateShortLink': {'shortLink': 'https://s.shopee.co.th/mockShort'}}}
    args = re.search(r'productOfferV2\(([^)]*)\)', q).group(1)
    get = lambda k: (re.search(k + r':("(?:[^"\\]|\\.)*"|\d+)', args) or [None, None])[1]
    keyword = json.loads(get('keyword')) if get('keyword') else ''
    item_id, shop_id = get('itemId'), get('shopId')
    sort, page, limit = int(get('sortType') or 1), int(get('page') or 1), int(get('limit') or 20)
    rows = list(CATALOG)
    if item_id:
        rows = [r for r in rows if str(r[0]) == item_id and (not shop_id or str(r[1]) == shop_id)]
    elif keyword:
        words = [w for w in re.split(r'\s+', keyword.lower()) if w]
        rows = [r for r in rows if any(w in r[2].lower() for w in words)] or ([] if keyword != 'พัดลม' else rows[:1])
    key = {2: lambda r: -r[8], 3: lambda r: -r[3], 4: lambda r: r[3], 5: lambda r: -r[5]}.get(sort)
    if key:
        rows.sort(key=key)
    chunk = rows[(page - 1) * limit: page * limit]
    return {'data': {'productOfferV2': {'nodes': [node(r) for r in chunk],
                                        'pageInfo': {'page': page, 'limit': limit, 'hasNextPage': len(rows) > page * limit}}}}


# ----------------------------------------------------------------- Gemini Omni Flash (video)
GEMINI_KEY = 'MOCK-GEMINI-KEY'
_gem_files: dict[str, dict] = {}
# Smallest thing that passes our >12-byte sanity check and looks like an MP4.
_MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


def _gem_auth(key):
    if key != GEMINI_KEY:
        return JSONResponse({'error': {'code': 403, 'message': 'API key not valid'}}, 403)
    return None


@app.get('/gemini/models')
def gem_models(x_goog_api_key: str = Header(default='')):
    bad = _gem_auth(x_goog_api_key)
    if bad:
        return bad
    return {'models': [{'name': 'models/gemini-omni-1.1-flash'}, {'name': 'models/gemini-2.5-flash'}]}


@app.post('/gemini/interactions')
async def gem_interactions(request: Request, x_goog_api_key: str = Header(default='')):
    bad = _gem_auth(x_goog_api_key)
    if bad:
        return bad
    body = await request.json()
    prompt = body.get('input')
    text = prompt if isinstance(prompt, str) else ' '.join(
        p.get('text', '') for p in prompt if isinstance(p, dict))
    has_image = isinstance(prompt, list) and any(p.get('type') == 'image' for p in prompt)
    fmt = body.get('response_format') or {}
    log('gemini.interactions', model=body.get('model'), aspect=fmt.get('aspect_ratio'),
        resolution=fmt.get('resolution'), has_image=has_image, prompt=text[:3000])
    if 'GEMFAIL' in text:
        return JSONResponse({'error': {'code': 400, 'message': 'Prompt rejected'}}, 400)
    fid = 'mockgem' + secrets.token_hex(6)
    _gem_files[fid] = {'polls': 0, 'fail': 'GEMSLOWFAIL' in text}
    uri = str(request.base_url).rstrip('/') + f'/gemini/files/{fid}:download?alt=media'
    return {'id': 'interactions/' + fid,
            'steps': [{'model_output': True, 'content': [{'type': 'video', 'mime_type': 'video/mp4', 'uri': uri}]}]}


@app.get('/gemini/files/{file_id}:download')
def gem_download(file_id: str, alt: str = '', x_goog_api_key: str = Header(default='')):
    bad = _gem_auth(x_goog_api_key)
    if bad:
        return bad
    if file_id not in _gem_files:
        return JSONResponse({'error': {'code': 404, 'message': 'File not found'}}, 404)
    log('gemini.download', file=file_id)
    return Response(_MP4, media_type='video/mp4')


@app.get('/gemini/files/{file_id}')
def gem_file(file_id: str, x_goog_api_key: str = Header(default='')):
    bad = _gem_auth(x_goog_api_key)
    if bad:
        return bad
    f = _gem_files.get(file_id)
    if not f:
        return JSONResponse({'error': {'code': 404, 'message': 'File not found'}}, 404)
    f['polls'] += 1
    if f['fail']:
        return {'name': f'files/{file_id}', 'state': 'FAILED'}
    return {'name': f'files/{file_id}', 'state': 'ACTIVE' if f['polls'] >= 2 else 'PROCESSING'}


# ----------------------------------------------------------------- TikTok
TT_CLIENT_KEY = 'mocktiktokkey'
TT_CLIENT_SECRET = 'mocktiktoksecret'
_tt_publishes: dict[str, dict] = {}
# Flip these from a test to exercise the unaudited (SELF_ONLY) path and account-level locks.
TT_STATE = {'privacy_options': ['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY'],
            'comment_disabled': False, 'duet_disabled': False, 'stitch_disabled': False,
            'max_duration_sec': 600, 'fail_publish': False}


def _tt_err(code: str, message: str, http: int = 400):
    return JSONResponse({'error': {'code': code, 'message': message, 'log_id': 'mocklog'}}, http)


def _tt_bearer(auth: str):
    token = auth[7:] if auth.lower().startswith('bearer ') else ''
    if not token.startswith('TTACCESS-'):
        return None, _tt_err('access_token_invalid', 'The access token is invalid or expired.', 401)
    return token, None


@app.get('/tiktok/v2/auth/authorize/')
def tt_authorize(client_key: str, redirect_uri: str, state: str, scope: str = '', response_type: str = 'code'):
    log('tiktok.authorize', client_key=client_key, redirect_uri=redirect_uri, scope=scope)
    ok = redirect_uri + '?' + urlencode({'code': 'TTCODE-' + state[:6], 'state': state, 'scopes': scope})
    no = redirect_uri + '?' + urlencode({'error': 'access_denied',
                                         'error_description': 'User denied the authorization.', 'state': state})
    return consent_page('TikTok (mock) — popcont wants to access your TikTok account', ok, no, f'Scopes: {scope}')


@app.post('/tiktok/oauth/token/')
def tt_token(client_key: str = Form(''), client_secret: str = Form(''), code: str = Form(''),
             grant_type: str = Form(''), redirect_uri: str = Form(''), refresh_token: str = Form('')):
    if client_key != TT_CLIENT_KEY or client_secret != TT_CLIENT_SECRET:
        return JSONResponse({'error': 'invalid_client', 'error_description': 'Client key or secret is incorrect.'}, 401)
    if grant_type == 'refresh_token':
        if not refresh_token.startswith('TTREFRESH-'):
            return JSONResponse({'error': 'invalid_grant', 'error_description': 'Refresh token is invalid.'}, 401)
        log('tiktok.refresh')
        return {'access_token': 'TTACCESS-' + secrets.token_hex(4), 'refresh_token': refresh_token,
                'open_id': 'tt-open-id-001', 'scope': 'user.info.basic,video.publish',
                'expires_in': 86400, 'refresh_expires_in': 31536000, 'token_type': 'Bearer'}
    if not code.startswith('TTCODE-'):
        return JSONResponse({'error': 'invalid_grant', 'error_description': 'Authorization code is invalid.'}, 400)
    log('tiktok.token', redirect_uri=redirect_uri)
    return {'access_token': 'TTACCESS-' + code[-6:], 'refresh_token': 'TTREFRESH-' + code[-6:],
            'open_id': 'tt-open-id-001', 'scope': 'user.info.basic,video.publish',
            'expires_in': 86400, 'refresh_expires_in': 31536000, 'token_type': 'Bearer'}


@app.post('/tiktok/oauth/revoke/')
def tt_revoke(client_key: str = Form(''), client_secret: str = Form(''), token: str = Form('')):
    log('tiktok.revoke')
    return {'error': {'code': 'ok', 'message': '', 'log_id': 'mocklog'}}


@app.get('/tiktok/user/info/')
def tt_user_info(fields: str = '', authorization: str = Header(default='')):
    token, bad = _tt_bearer(authorization)
    if bad:
        return bad
    log('tiktok.user_info', fields=fields)
    return {'data': {'user': {'open_id': 'tt-open-id-001', 'username': 'candelaz.kengza',
                              'display_name': 'Candelaz Kengza', 'avatar_url': 'https://example.com/tt.jpg',
                              'follower_count': 1280, 'likes_count': 9400, 'video_count': 37}},
            'error': {'code': 'ok', 'message': '', 'log_id': 'mocklog'}}


@app.post('/tiktok/post/publish/creator_info/query/')
def tt_creator_info(authorization: str = Header(default='')):
    token, bad = _tt_bearer(authorization)
    if bad:
        return bad
    log('tiktok.creator_info')
    return {'data': {'creator_avatar_url': 'https://example.com/tt.jpg',
                     'creator_username': 'candelaz.kengza', 'creator_nickname': 'Candelaz Kengza',
                     'privacy_level_options': TT_STATE['privacy_options'],
                     'comment_disabled': TT_STATE['comment_disabled'],
                     'duet_disabled': TT_STATE['duet_disabled'],
                     'stitch_disabled': TT_STATE['stitch_disabled'],
                     'max_video_post_duration_sec': TT_STATE['max_duration_sec']},
            'error': {'code': 'ok', 'message': '', 'log_id': 'mocklog'}}


@app.post('/tiktok/post/publish/video/init/')
async def tt_video_init(req: Request, authorization: str = Header(default='')):
    token, bad = _tt_bearer(authorization)
    if bad:
        return bad
    body = await req.json()
    info = body.get('post_info') or {}
    src = body.get('source_info') or {}
    if info.get('privacy_level') not in TT_STATE['privacy_options']:
        return _tt_err('invalid_param', 'privacy_level is not available to this creator.')
    if info.get('brand_content_toggle') and info.get('privacy_level') == 'SELF_ONLY':
        return _tt_err('invalid_param', 'Branded content cannot be set to private.')
    if src.get('source') != 'FILE_UPLOAD' or not src.get('video_size'):
        return _tt_err('invalid_param', 'source_info is incomplete.')
    pid = 'v_pub_' + secrets.token_hex(6)
    _tt_publishes[pid] = {'size': int(src['video_size']), 'received': 0, 'polls': 0,
                          'privacy': info.get('privacy_level'), 'fail': TT_STATE['fail_publish']}
    log('tiktok.init', publish_id=pid, title=(info.get('title') or '')[:3000],
        privacy=info.get('privacy_level'), is_aigc=info.get('is_aigc'),
        brand_content=info.get('brand_content_toggle'), brand_organic=info.get('brand_organic_toggle'),
        disable_comment=info.get('disable_comment'), chunks=src.get('total_chunk_count'),
        video_size=src.get('video_size'))
    return {'data': {'publish_id': pid, 'upload_url': f'{str(req.base_url).rstrip("/")}/tiktok/upload/{pid}'},
            'error': {'code': 'ok', 'message': '', 'log_id': 'mocklog'}}


@app.put('/tiktok/upload/{publish_id}')
async def tt_upload(publish_id: str, req: Request, content_range: str = Header(default=''),
                    content_type: str = Header(default='')):
    rec = _tt_publishes.get(publish_id)
    if not rec:
        return _tt_err('invalid_publish_id', 'Unknown publish id.', 404)
    if content_type not in ('video/mp4', 'video/quicktime', 'video/webm'):
        return _tt_err('invalid_param', f'Unsupported Content-Type: {content_type}')
    m = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range or '')
    if not m:
        return _tt_err('invalid_param', f'Bad Content-Range: {content_range}')
    first, last, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if total != rec['size']:
        return _tt_err('invalid_param', 'Content-Range total does not match video_size.')
    blob = await req.body()
    if len(blob) != last - first + 1:
        return _tt_err('invalid_param', 'Chunk length does not match Content-Range.')
    rec['received'] += len(blob)
    log('tiktok.upload', publish_id=publish_id, range=content_range, bytes=len(blob))
    return Response(status_code=201)


@app.post('/tiktok/post/publish/status/fetch/')
async def tt_status(req: Request, authorization: str = Header(default='')):
    token, bad = _tt_bearer(authorization)
    if bad:
        return bad
    pid = (await req.json()).get('publish_id', '')
    rec = _tt_publishes.get(pid)
    if not rec:
        return _tt_err('invalid_publish_id', 'Unknown publish id.')
    rec['polls'] += 1
    if rec['fail']:
        data = {'status': 'FAILED', 'fail_reason': 'file_format_check_failed'}
    elif rec['received'] < rec['size'] or rec['polls'] < 2:
        data = {'status': 'PROCESSING_UPLOAD', 'uploaded_bytes': rec['received']}
    else:
        data = {'status': 'PUBLISH_COMPLETE', 'uploaded_bytes': rec['received']}
        if rec['privacy'] != 'SELF_ONLY':
            data['publicaly_available_post_id'] = [7300000000000000001]
    log('tiktok.status', publish_id=pid, status=data['status'])
    return {'data': data, 'error': {'code': 'ok', 'message': '', 'log_id': 'mocklog'}}
