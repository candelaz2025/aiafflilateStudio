"""Meta connectors: Facebook Login (Pages + linked IG business) and Instagram API with Instagram Login.

Every base URL can be overridden by env so the full OAuth journey can be exercised against a
local mock (dev_tools/mock_providers.py). Production defaults point at Meta's official hosts.
"""
from __future__ import annotations

import os
from urllib.parse import urlencode

import requests

TIMEOUT = 20


class MetaError(Exception):
    pass


def graph_version() -> str:
    return os.getenv('META_GRAPH_VERSION', 'v25.0').strip() or 'v25.0'


def fb_dialog_base() -> str:
    return os.getenv('META_DIALOG_BASE', 'https://www.facebook.com').rstrip('/')


def fb_graph_base() -> str:
    return os.getenv('META_GRAPH_BASE', 'https://graph.facebook.com').rstrip('/')


def ig_auth_base() -> str:
    return os.getenv('IG_AUTH_BASE', 'https://www.instagram.com').rstrip('/')


def ig_api_base() -> str:
    return os.getenv('IG_API_BASE', 'https://api.instagram.com').rstrip('/')


def ig_graph_base() -> str:
    return os.getenv('IG_GRAPH_BASE', 'https://graph.instagram.com').rstrip('/')


FB_SCOPES = ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts',
             'business_management', 'instagram_basic', 'instagram_content_publish']
IG_SCOPES = ['instagram_business_basic', 'instagram_business_content_publish']


def _check(resp: requests.Response):
    try:
        data = resp.json()
    except ValueError:
        raise MetaError(f'Meta ตอบกลับไม่ใช่ JSON (HTTP {resp.status_code})')
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get('error')):
        err = data.get('error') if isinstance(data, dict) else None
        if isinstance(err, dict):
            message = err.get('message') or str(err)
        else:
            message = data.get('error_message') if isinstance(data, dict) else None
            message = message or str(err or data)
        raise MetaError(f'Meta API error: {message}'[:400])
    return data


def _get(url, params):
    try:
        return _check(requests.get(url, params=params, timeout=TIMEOUT))
    except requests.RequestException as e:
        raise MetaError(f'เชื่อมต่อ Meta ไม่ได้: {e.__class__.__name__}')


def _post(url, data=None, params=None):
    try:
        return _check(requests.post(url, data=data, params=params, timeout=TIMEOUT))
    except requests.RequestException as e:
        raise MetaError(f'เชื่อมต่อ Meta ไม่ได้: {e.__class__.__name__}')


# ---------------------------------------------------------------- Facebook Login (Pages)
def facebook_auth_url(app_id: str, redirect_uri: str, state: str) -> str:
    q = urlencode({'client_id': app_id, 'redirect_uri': redirect_uri, 'state': state,
                   'response_type': 'code', 'scope': ','.join(FB_SCOPES)})
    return f'{fb_dialog_base()}/{graph_version()}/dialog/oauth?{q}'


def facebook_exchange_code(app_id, app_secret, redirect_uri, code) -> str:
    g = f'{fb_graph_base()}/{graph_version()}'
    short = _get(f'{g}/oauth/access_token', {'client_id': app_id, 'client_secret': app_secret,
                                             'redirect_uri': redirect_uri, 'code': code})
    token = short.get('access_token')
    if not token:
        raise MetaError('ไม่ได้รับ access token จาก Facebook')
    # Long-lived user token -> page tokens derived from it do not expire.
    long = _get(f'{g}/oauth/access_token', {'grant_type': 'fb_exchange_token', 'client_id': app_id,
                                            'client_secret': app_secret, 'fb_exchange_token': token})
    return long.get('access_token') or token


def facebook_pages(user_token: str) -> list[dict]:
    g = f'{fb_graph_base()}/{graph_version()}'
    fields = ('id,name,access_token,category,picture{url},'
              'instagram_business_account{id,username,profile_picture_url}')
    data = _get(f'{g}/me/accounts', {'fields': fields, 'limit': 100, 'access_token': user_token})
    pages = []
    for p in data.get('data', []):
        if not p.get('id') or not p.get('access_token'):
            continue
        ig = p.get('instagram_business_account') or None
        pages.append({'id': str(p['id']), 'name': p.get('name') or 'Facebook Page',
                      'access_token': p['access_token'], 'category': p.get('category', ''),
                      'picture': ((p.get('picture') or {}).get('data') or {}).get('url', ''),
                      'instagram': ({'id': str(ig['id']), 'username': ig.get('username', ''),
                                     'picture': ig.get('profile_picture_url', '')} if ig and ig.get('id') else None)})
    return pages


def facebook_page_check(page_id, token) -> dict:
    g = f'{fb_graph_base()}/{graph_version()}'
    return _get(f'{g}/{page_id}', {'fields': 'id,name,fan_count,followers_count', 'access_token': token})


def facebook_page_from_token(token: str) -> dict:
    """Resolve a pasted Page Access Token into its page (no app needed).

    A page token answers /me as the page itself. We also read tasks so we can
    warn when the token lacks CREATE_CONTENT (posting) permission, and pull the
    linked IG business account when present.
    """
    g = f'{fb_graph_base()}/{graph_version()}'
    # 1) A token can describe itself: type (USER/PAGE) and the scopes it carries.
    #    Best-effort — some tokens cannot be introspected with themselves.
    ttype, scopes = '', []
    try:
        dbg = _get(f'{g}/debug_token', {'input_token': token, 'access_token': token}).get('data') or {}
        ttype, scopes = (dbg.get('type') or '').upper(), dbg.get('scopes') or []
    except MetaError:
        pass
    if ttype == 'USER':
        raise MetaError('นี่คือ User Token — ใน Graph API Explorer เปลี่ยนดรอปดาวน์ "User or Page" เป็นเพจของคุณ แล้วคัดลอก token ใหม่')
    if scopes and 'pages_manage_posts' not in scopes:
        raise MetaError('token นี้ไม่มีสิทธิ์ pages_manage_posts — ติ๊กสิทธิ์นี้ใน Permissions แล้วกด Generate Access Token ใหม่')
    # 2) The page itself (category only exists on pages, so a user token fails here too).
    try:
        data = _get(f'{g}/me', {'access_token': token,
                                'fields': 'id,name,category,picture{url},'
                                          'instagram_business_account{id,username,profile_picture_url}'})
    except MetaError as e:
        if 'category' in str(e) or 'nonexisting field' in str(e):
            raise MetaError('token นี้ไม่ใช่ Page Token — เลือกเพจในดรอปดาวน์ "User or Page" ของ Graph API Explorer แล้วคัดลอกใหม่')
        raise
    pid = str(data.get('id') or '')
    if not pid:
        raise MetaError('token นี้ไม่คืนค่าเพจ — ต้องเป็น Page Access Token (ไม่ใช่ User Token)')
    ig = data.get('instagram_business_account') or None
    return {'id': pid, 'name': data.get('name') or 'Facebook Page', 'category': data.get('category', ''),
            'picture': ((data.get('picture') or {}).get('data') or {}).get('url', ''),
            'scopes': scopes,
            'instagram': ({'id': str(ig['id']), 'username': ig.get('username', ''),
                           'picture': ig.get('profile_picture_url', '')} if ig and ig.get('id') else None)}


def facebook_publish(page_id, token, message, link='', image_url='') -> dict:
    g = f'{fb_graph_base()}/{graph_version()}'
    if image_url:
        caption = message + (f'\n\n🛒 {link}' if link else '')
        res = _post(f'{g}/{page_id}/photos', data={'url': image_url, 'caption': caption, 'access_token': token})
        return {'post_id': res.get('post_id') or res.get('id'), 'kind': 'photo'}
    payload = {'message': message, 'access_token': token}
    if link:
        payload['link'] = link
    res = _post(f'{g}/{page_id}/feed', data=payload)
    return {'post_id': res.get('id'), 'kind': 'feed'}


# ---------------------------------------------------------------- Instagram (both login types)
def instagram_auth_url(app_id, redirect_uri, state) -> str:
    q = urlencode({'client_id': app_id, 'redirect_uri': redirect_uri, 'state': state,
                   'response_type': 'code', 'scope': ','.join(IG_SCOPES)})
    return f'{ig_auth_base()}/oauth/authorize?{q}'


def instagram_exchange_code(app_id, app_secret, redirect_uri, code) -> dict:
    short = _post(f'{ig_api_base()}/oauth/access_token', data={
        'client_id': app_id, 'client_secret': app_secret, 'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri, 'code': code})
    if isinstance(short.get('data'), list) and short['data']:
        short = short['data'][0]
    token = short.get('access_token')
    if not token:
        raise MetaError('ไม่ได้รับ access token จาก Instagram')
    long = _get(f'{ig_graph_base()}/access_token', {'grant_type': 'ig_exchange_token',
                                                    'client_secret': app_secret, 'access_token': token})
    return {'access_token': long.get('access_token') or token,
            'expires_in': int(long.get('expires_in') or 0)}


def instagram_refresh(token) -> dict:
    data = _get(f'{ig_graph_base()}/refresh_access_token', {'grant_type': 'ig_refresh_token', 'access_token': token})
    return {'access_token': data.get('access_token') or token, 'expires_in': int(data.get('expires_in') or 0)}


def instagram_me(token) -> dict:
    data = _get(f'{ig_graph_base()}/{graph_version()}/me',
                {'fields': 'user_id,username,profile_picture_url,account_type', 'access_token': token})
    uid = str(data.get('user_id') or data.get('id') or '')
    if not uid:
        raise MetaError('ไม่พบบัญชี Instagram')
    return {'id': uid, 'username': data.get('username', ''), 'picture': data.get('profile_picture_url', ''),
            'account_type': data.get('account_type', '')}


def _ig_base(via: str) -> str:
    return f'{fb_graph_base() if via == "facebook" else ig_graph_base()}/{graph_version()}'


def instagram_check(ig_id, token, via='instagram') -> dict:
    return _get(f'{_ig_base(via)}/{ig_id}', {'fields': 'id,username,followers_count,media_count', 'access_token': token})


def instagram_publish(ig_id, token, caption, image_url, via='instagram') -> dict:
    if not image_url:
        raise MetaError('Instagram ต้องมีรูปภาพ (image_url สาธารณะแบบ https) จึงจะโพสต์ได้')
    base = _ig_base(via)
    container = _post(f'{base}/{ig_id}/media', data={'image_url': image_url, 'caption': caption, 'access_token': token})
    cid = container.get('id')
    if not cid:
        raise MetaError('สร้าง media container ไม่สำเร็จ')
    res = _post(f'{base}/{ig_id}/media_publish', data={'creation_id': cid, 'access_token': token})
    return {'post_id': res.get('id'), 'kind': 'image'}


# ---------------------------------------------------------------- video + scheduling (Auto-Post)
def fb_video_base() -> str:
    return os.getenv('META_GRAPH_VIDEO_BASE', os.getenv('META_GRAPH_BASE', 'https://graph-video.facebook.com')).rstrip('/')


def facebook_publish_video(page_id, token, file_path, description, scheduled_ts: int | None = None) -> dict:
    """Upload a video file to a Page. With scheduled_ts Facebook itself publishes it later (10 min–30 days)."""
    data = {'description': description, 'access_token': token}
    if scheduled_ts:
        data.update({'published': 'false', 'scheduled_publish_time': str(int(scheduled_ts))})
    try:
        with open(file_path, 'rb') as fh:
            r = requests.post(f'{fb_video_base()}/{graph_version()}/{page_id}/videos', data=data,
                              files={'source': (os.path.basename(file_path), fh)}, timeout=300)
        res = _check(r)
    except requests.RequestException as e:
        raise MetaError(f'อัปโหลดวิดีโอไป Facebook ไม่ได้: {e.__class__.__name__}')
    return {'post_id': res.get('id'), 'kind': 'video' + ('_scheduled' if scheduled_ts else '')}


def facebook_publish_scheduled(page_id, token, message, link='', image_url='', scheduled_ts: int | None = None) -> dict:
    """Photo/feed post; with scheduled_ts it is queued natively on Facebook."""
    if not scheduled_ts:
        return facebook_publish(page_id, token, message, link, image_url)
    g = f'{fb_graph_base()}/{graph_version()}'
    extra = {'published': 'false', 'scheduled_publish_time': str(int(scheduled_ts)), 'access_token': token}
    if image_url:
        caption = message + (f'\n\n🛒 {link}' if link and link not in message else '')
        res = _post(f'{g}/{page_id}/photos', data={'url': image_url, 'caption': caption, **extra})
        return {'post_id': res.get('post_id') or res.get('id'), 'kind': 'photo_scheduled'}
    data = {'message': message, **extra}
    if link:
        data['link'] = link
    res = _post(f'{g}/{page_id}/feed', data=data)
    return {'post_id': res.get('id'), 'kind': 'feed_scheduled'}


def delete_object(object_id, token) -> None:
    try:
        _check(requests.delete(f'{fb_graph_base()}/{graph_version()}/{object_id}', params={'access_token': token}, timeout=TIMEOUT))
    except requests.RequestException as e:
        raise MetaError(f'ยกเลิกโพสต์ที่ตั้งเวลาใน Facebook ไม่ได้: {e.__class__.__name__}')


def instagram_publish_reel(ig_id, token, caption, video_url, via='instagram', wait_s: int = 120) -> dict:
    """Instagram Reels need a public https MP4 URL; the container is processed before publishing."""
    import time as _t
    if not video_url.startswith('https://'):
        raise MetaError('Instagram Reels ต้องใช้ลิงก์วิดีโอ https สาธารณะ (ตั้ง PUBLIC_BASE_URL เป็น https)')
    base = _ig_base(via)
    container = _post(f'{base}/{ig_id}/media', data={'media_type': 'REELS', 'video_url': video_url, 'caption': caption,
                                                     'share_to_feed': 'true', 'access_token': token})
    cid = container.get('id')
    if not cid:
        raise MetaError('สร้าง Reels container ไม่สำเร็จ')
    deadline = _t.time() + wait_s
    while True:
        st = _get(f'{base}/{cid}', {'fields': 'status_code', 'access_token': token}).get('status_code')
        if st == 'FINISHED':
            break
        if st in ('ERROR', 'EXPIRED'):
            raise MetaError(f'Instagram ประมวลผลวิดีโอไม่สำเร็จ ({st}) — ใช้ไฟล์ MP4 H.264')
        if _t.time() > deadline:
            raise MetaError('Instagram ยังประมวลผลวิดีโอไม่เสร็จ — ลองใหม่อีกครั้ง')
        _t.sleep(3)
    res = _post(f'{base}/{ig_id}/media_publish', data={'creation_id': cid, 'access_token': token})
    return {'post_id': res.get('id'), 'kind': 'reel'}
