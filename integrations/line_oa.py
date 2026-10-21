"""LINE Official Account via Messaging API.

LINE OA has no third-party OAuth for bots; the official way to "connect an account" is the
Messaging API channel credentials from LINE Developers Console. We verify them live against
api.line.me and register this app's webhook URL on the channel automatically.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

import requests

TIMEOUT = 15


class LineError(Exception):
    pass


def api_base() -> str:
    return os.getenv('LINE_API_BASE', 'https://api.line.me').rstrip('/')


def _check(resp: requests.Response):
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        message = data.get('message') or data.get('error_description') or data.get('error') or f'HTTP {resp.status_code}'
        details = data.get('details')
        if details and isinstance(details, list):
            message += ' — ' + '; '.join(str(d.get('message', d)) for d in details[:3])
        raise LineError(f'LINE API error: {message}'[:400])
    return data


def _req(method, path, token=None, **kw):
    headers = kw.pop('headers', {})
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        return _check(requests.request(method, api_base() + path, headers=headers, timeout=TIMEOUT, **kw))
    except requests.RequestException as e:
        raise LineError(f'เชื่อมต่อ LINE ไม่ได้: {e.__class__.__name__}')


def issue_token(channel_id: str, channel_secret: str) -> dict:
    """Short-lived (30 days) channel access token via client credentials."""
    data = _req('POST', '/v2/oauth/accessToken', data={
        'grant_type': 'client_credentials', 'client_id': channel_id, 'client_secret': channel_secret})
    if not data.get('access_token'):
        raise LineError('ออก Channel access token ไม่สำเร็จ ตรวจ Channel ID / Channel secret')
    return {'access_token': data['access_token'], 'expires_in': int(data.get('expires_in') or 0)}


def bot_info(token: str) -> dict:
    d = _req('GET', '/v2/bot/info', token)
    if not d.get('userId'):
        raise LineError('Channel access token ใช้งานไม่ได้')
    return {'user_id': d['userId'], 'basic_id': d.get('basicId', ''), 'premium_id': d.get('premiumId', ''),
            'display_name': d.get('displayName', 'LINE OA'), 'picture': d.get('pictureUrl', ''),
            'chat_mode': d.get('chatMode', ''), 'mark_as_read_mode': d.get('markAsReadMode', '')}


def quota(token: str) -> dict:
    q = _req('GET', '/v2/bot/message/quota', token)
    used = _req('GET', '/v2/bot/message/quota/consumption', token)
    return {'type': q.get('type'), 'limit': q.get('value'), 'used': used.get('totalUsage', 0)}


def set_webhook(token: str, endpoint: str) -> dict:
    _req('PUT', '/v2/bot/channel/webhook/endpoint', token, json={'endpoint': endpoint})
    try:
        return _req('POST', '/v2/bot/channel/webhook/test', token, json={'endpoint': endpoint})
    except LineError as e:  # endpoint saved; test may fail if server not public yet
        return {'success': False, 'reason': str(e)}


def product_flex(title: str, price: str, image_url: str, link: str, note: str = '') -> dict:
    body = [{'type': 'text', 'text': title[:120] or 'สินค้าแนะนำ', 'weight': 'bold', 'size': 'md', 'wrap': True}]
    if price:
        body.append({'type': 'text', 'text': price, 'color': '#EE4D2D', 'weight': 'bold', 'size': 'lg', 'margin': 'sm'})
    if note:
        body.append({'type': 'text', 'text': note[:300], 'size': 'sm', 'color': '#666666', 'wrap': True, 'margin': 'sm'})
    bubble = {'type': 'bubble', 'body': {'type': 'box', 'layout': 'vertical', 'contents': body}}
    if image_url:
        bubble['hero'] = {'type': 'image', 'url': image_url, 'size': 'full', 'aspectRatio': '1:1', 'aspectMode': 'cover'}
    if link:
        bubble['footer'] = {'type': 'box', 'layout': 'vertical', 'contents': [
            {'type': 'button', 'style': 'primary', 'color': '#EE4D2D',
             'action': {'type': 'uri', 'label': 'ดูสินค้า / สั่งซื้อ', 'uri': link}}]}
    return {'type': 'flex', 'altText': (title or 'สินค้าแนะนำ')[:300], 'contents': bubble}


def push(token: str, to: str, messages: list) -> dict:
    return _req('POST', '/v2/bot/message/push', token, json={'to': to, 'messages': messages[:5]})


def broadcast(token: str, messages: list) -> dict:
    return _req('POST', '/v2/bot/message/broadcast', token, json={'messages': messages[:5]})


def reply(token: str, reply_token: str, messages: list) -> dict:
    return _req('POST', '/v2/bot/message/reply', token, json={'replyToken': reply_token, 'messages': messages[:5]})


def profile(token: str, user_id: str) -> dict:
    try:
        return _req('GET', f'/v2/bot/profile/{user_id}', token)
    except LineError:
        return {}


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    if not signature or not channel_secret:
        return False
    mac = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature)
