"""TikTok connector: Login Kit (OAuth v2) + Content Posting API (Direct Post).

Base URLs are env-overridable so the whole journey — consent, token exchange, creator
lookup, chunked upload, status polling — runs against dev_tools/mock_providers.py in
tests. Production defaults point at TikTok's official hosts.

Compliance notes that shape this module (TikTok Content Sharing Guidelines):
  * `privacy_level` must be one of the values creator_info returns for THAT creator —
    never a value we pick ourselves. An unaudited client only ever gets SELF_ONLY.
  * Commercial content must be declared. Affiliate posts promote someone else's product,
    so `brand_content_toggle` is the honest flag; `brand_organic_toggle` is for the
    creator's own brand. TikTok rejects a post that sets branded content together with
    SELF_ONLY privacy, so the caller has to reconcile the two.
  * AI-generated clips must carry `is_aigc` so TikTok can apply the AI label.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

import requests

TIMEOUT = 30
UPLOAD_TIMEOUT = 300

# TikTok's media transfer rules: a chunk is 5 MiB–64 MiB and a video may have at most
# 1000 chunks. Anything that fits in one chunk is sent as a single PUT.
MIN_CHUNK = 5 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024

SCOPES = ['user.info.basic', 'video.publish']
PRIVACY_LEVELS = ('PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY')
PRIVACY_LABEL_TH = {
    'PUBLIC_TO_EVERYONE': 'สาธารณะ — ทุกคนเห็น',
    'MUTUAL_FOLLOW_FRIENDS': 'เพื่อน — ผู้ที่ติดตามกันทั้งสองฝ่าย',
    'FOLLOWER_OF_CREATOR': 'ผู้ติดตามของฉัน',
    'SELF_ONLY': 'ส่วนตัว — เห็นคนเดียว',
}
CONTENT_TYPES = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm'}


class TikTokError(Exception):
    pass


def auth_base() -> str:
    return os.getenv('TIKTOK_AUTH_BASE', 'https://www.tiktok.com').rstrip('/')


def api_base() -> str:
    return os.getenv('TIKTOK_API_BASE', 'https://open.tiktokapis.com/v2').rstrip('/')


def _check(resp: requests.Response):
    try:
        data = resp.json()
    except ValueError:
        raise TikTokError(f'TikTok ตอบกลับไม่ใช่ JSON (HTTP {resp.status_code})')
    err = data.get('error') if isinstance(data, dict) else None
    # The OAuth endpoints return a flat {"error": "...", "error_description": "..."};
    # every Content Posting endpoint returns {"error": {"code": "ok", ...}}.
    if isinstance(err, str) and err:
        raise TikTokError(f'TikTok API error: {data.get("error_description") or err}'[:400])
    if isinstance(err, dict) and err.get('code') not in (None, '', 'ok'):
        raise TikTokError(f'TikTok API error: {err.get("message") or err.get("code")}'[:400])
    if resp.status_code >= 400:
        raise TikTokError(f'TikTok API error: HTTP {resp.status_code}')
    return data


def _form(url, data):
    try:
        return _check(requests.post(url, data=data, timeout=TIMEOUT,
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'}))
    except requests.RequestException as e:
        raise TikTokError(f'เชื่อมต่อ TikTok ไม่ได้: {e.__class__.__name__}')


def _json(url, token, payload=None):
    try:
        return _check(requests.post(url, json=payload if payload is not None else {}, timeout=TIMEOUT,
                                    headers={'Authorization': f'Bearer {token}',
                                             'Content-Type': 'application/json; charset=UTF-8'}))
    except requests.RequestException as e:
        raise TikTokError(f'เชื่อมต่อ TikTok ไม่ได้: {e.__class__.__name__}')


def _get(url, token, params=None):
    try:
        return _check(requests.get(url, params=params, timeout=TIMEOUT,
                                   headers={'Authorization': f'Bearer {token}'}))
    except requests.RequestException as e:
        raise TikTokError(f'เชื่อมต่อ TikTok ไม่ได้: {e.__class__.__name__}')


# ------------------------------------------------------------------ Login Kit (OAuth)
def auth_url(client_key: str, redirect_uri: str, state: str) -> str:
    q = urlencode({'client_key': client_key, 'response_type': 'code', 'scope': ','.join(SCOPES),
                   'redirect_uri': redirect_uri, 'state': state})
    return f'{auth_base()}/v2/auth/authorize/?{q}'


def _tokens(data: dict) -> dict:
    if not data.get('access_token'):
        raise TikTokError('TikTok ไม่ได้ส่ง access_token กลับมา')
    return {'access_token': data['access_token'],
            'refresh_token': data.get('refresh_token', ''),
            'open_id': data.get('open_id', ''),
            'scope': data.get('scope', ''),
            'expires_in': int(data.get('expires_in') or 0),
            'refresh_expires_in': int(data.get('refresh_expires_in') or 0)}


def exchange_code(client_key: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    return _tokens(_form(f'{api_base()}/oauth/token/', {
        'client_key': client_key, 'client_secret': client_secret, 'code': code,
        'grant_type': 'authorization_code', 'redirect_uri': redirect_uri}))


def refresh(client_key: str, client_secret: str, refresh_token: str) -> dict:
    return _tokens(_form(f'{api_base()}/oauth/token/', {
        'client_key': client_key, 'client_secret': client_secret,
        'grant_type': 'refresh_token', 'refresh_token': refresh_token}))


def revoke(client_key: str, client_secret: str, token: str) -> None:
    try:
        _form(f'{api_base()}/oauth/revoke/', {'client_key': client_key,
                                              'client_secret': client_secret, 'token': token})
    except TikTokError:
        pass  # disconnecting locally must not fail because TikTok refused the revoke


def user_info(access_token: str) -> dict:
    fields = 'open_id,avatar_url,display_name,username,follower_count,likes_count,video_count'
    data = _get(f'{api_base()}/user/info/', access_token, {'fields': fields}).get('data', {})
    u = data.get('user', {}) if isinstance(data, dict) else {}
    return {'open_id': u.get('open_id', ''), 'username': u.get('username', ''),
            'display_name': u.get('display_name', ''), 'avatar': u.get('avatar_url', ''),
            'followers': u.get('follower_count'), 'likes': u.get('likes_count'),
            'videos': u.get('video_count')}


# ----------------------------------------------------------- Content Posting API
def creator_info(access_token: str) -> dict:
    """Must be called before every post: it is what tells us which privacy levels this
    creator may use and whether comments/duet/stitch are off at the account level."""
    d = _json(f'{api_base()}/post/publish/creator_info/query/', access_token).get('data', {})
    opts = [p for p in (d.get('privacy_level_options') or []) if p in PRIVACY_LEVELS]
    return {'username': d.get('creator_username', ''), 'nickname': d.get('creator_nickname', ''),
            'avatar': d.get('creator_avatar_url', ''),
            'privacy_options': opts or ['SELF_ONLY'],
            'comment_disabled': bool(d.get('comment_disabled')),
            'duet_disabled': bool(d.get('duet_disabled')),
            'stitch_disabled': bool(d.get('stitch_disabled')),
            'max_duration_sec': int(d.get('max_video_post_duration_sec') or 0)}


def plan_chunks(size: int) -> tuple[int, int]:
    """TikTok wants chunk_size and total_chunk_count up front, and the last chunk carries
    the remainder rather than becoming a short chunk of its own."""
    if size <= 0:
        raise TikTokError('ไฟล์วิดีโอว่างเปล่า')
    if size > MAX_VIDEO_BYTES:
        raise TikTokError('ไฟล์วิดีโอใหญ่เกิน 4GB')
    if size <= MAX_CHUNK:
        return size, 1
    chunk = max(MIN_CHUNK, min(CHUNK, MAX_CHUNK))
    count = max(1, size // chunk)
    if count > 1000:
        count = 1000
        chunk = min(MAX_CHUNK, -(-size // count))
    return chunk, count


def init_direct_post(access_token: str, *, title: str, privacy_level: str, video_size: int,
                     disable_comment: bool = False, disable_duet: bool = False,
                     disable_stitch: bool = False, brand_content_toggle: bool = False,
                     brand_organic_toggle: bool = False, is_aigc: bool = False,
                     cover_timestamp_ms: int = 0) -> dict:
    if privacy_level not in PRIVACY_LEVELS:
        raise TikTokError(f'privacy_level ไม่ถูกต้อง: {privacy_level}')
    if brand_content_toggle and privacy_level == 'SELF_ONLY':
        raise TikTokError('TikTok ไม่อนุญาตให้ตั้งคลิปเป็น "ส่วนตัว" พร้อมกับประกาศเป็น Branded content '
                          '— ต้องเลือกอย่างใดอย่างหนึ่ง')
    chunk_size, total = plan_chunks(video_size)
    post_info = {'title': (title or '')[:2200], 'privacy_level': privacy_level,
                 'disable_comment': bool(disable_comment), 'disable_duet': bool(disable_duet),
                 'disable_stitch': bool(disable_stitch),
                 'brand_content_toggle': bool(brand_content_toggle),
                 'brand_organic_toggle': bool(brand_organic_toggle),
                 'is_aigc': bool(is_aigc)}
    if cover_timestamp_ms > 0:
        post_info['video_cover_timestamp_ms'] = int(cover_timestamp_ms)
    body = {'post_info': post_info,
            'source_info': {'source': 'FILE_UPLOAD', 'video_size': int(video_size),
                            'chunk_size': int(chunk_size), 'total_chunk_count': int(total)}}
    d = _json(f'{api_base()}/post/publish/video/init/', access_token, body).get('data', {})
    if not d.get('publish_id') or not d.get('upload_url'):
        raise TikTokError('TikTok ไม่ได้ส่ง upload_url กลับมา')
    return {'publish_id': d['publish_id'], 'upload_url': d['upload_url'],
            'chunk_size': chunk_size, 'total_chunk_count': total}


def upload_file(upload_url: str, path: str | Path, chunk_size: int, total_chunk_count: int) -> int:
    """PUT the file to the url init handed back. Each chunk declares its own byte range
    against the full length; the final chunk absorbs the remainder."""
    p = Path(path)
    if not p.is_file():
        raise TikTokError('ไม่พบไฟล์วิดีโอที่จะอัปโหลด')
    size = p.stat().st_size
    ctype = CONTENT_TYPES.get(p.suffix.lower(), 'video/mp4')
    sent = 0
    with p.open('rb') as fh:
        for i in range(total_chunk_count):
            first = i * chunk_size
            last = size - 1 if i == total_chunk_count - 1 else min(first + chunk_size, size) - 1
            fh.seek(first)
            blob = fh.read(last - first + 1)
            if not blob:
                break
            try:
                r = requests.put(upload_url, data=blob, timeout=UPLOAD_TIMEOUT, headers={
                    'Content-Type': ctype, 'Content-Length': str(len(blob)),
                    'Content-Range': f'bytes {first}-{last}/{size}'})
            except requests.RequestException as e:
                raise TikTokError(f'อัปโหลดวิดีโอไป TikTok ไม่สำเร็จ: {e.__class__.__name__}')
            if r.status_code >= 400:
                raise TikTokError(f'TikTok ปฏิเสธการอัปโหลด (HTTP {r.status_code})')
            sent += len(blob)
    return sent


def publish_status(access_token: str, publish_id: str) -> dict:
    d = _json(f'{api_base()}/post/publish/status/fetch/', access_token,
              {'publish_id': publish_id}).get('data', {})
    ids = d.get('publicaly_available_post_id') or d.get('publicly_available_post_id') or []
    return {'status': d.get('status', ''), 'fail_reason': d.get('fail_reason', ''),
            'post_ids': [str(x) for x in ids], 'uploaded_bytes': int(d.get('uploaded_bytes') or 0)}
