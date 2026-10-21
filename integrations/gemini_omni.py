"""Google Gemini Omni Flash video adapter (user's own API key).

Uses the documented Gemini API `interactions` endpoint with
`response_format.delivery = "uri"`, then polls the Files API and downloads the
MP4. Only Google's fixed hosts are ever contacted — no user-supplied URLs.

Veo 3.1 Preview (the older `predictLongRunning` path in studio_v6/video_service.py)
is shut down on 2026-10-22, so new work goes through Omni Flash.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

import os

MODEL = 'gemini-omni-1.1-flash'


def base() -> str:
    """Google's endpoint; overridable only so the dev mock can stand in during tests."""
    return os.getenv('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')
MAX_BYTES = 100 * 1024 * 1024
MAX_IMAGE_BYTES = 7 * 1024 * 1024
IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
ASPECTS = ('9:16', '16:9')
RESOLUTIONS = ('360p', '720p', '1080p')


class GeminiError(Exception):
    pass


def _json(r):
    try:
        return r.json()
    except ValueError as e:
        raise GeminiError('Gemini ส่งผลลัพธ์ที่อ่านไม่ได้') from e


def _check(r):
    if r.status_code < 400:
        return r
    detail = ''
    try:
        detail = ((r.json().get('error') or {}).get('message') or '')[:160]
    except ValueError:
        pass
    if r.status_code in (401, 403):
        raise GeminiError('Gemini ปฏิเสธคีย์นี้ หรือคีย์ยังไม่มีสิทธิ์สร้างวิดีโอ' + (f' — {detail}' if detail else ''))
    if r.status_code == 429:
        raise GeminiError('โควตา Gemini ของคีย์นี้หมด หรือส่งคำขอถี่เกินไป — รอสักครู่แล้วลองใหม่')
    if r.status_code in (400, 404):
        raise GeminiError('Gemini ปฏิเสธคำขอ' + (f' — {detail}' if detail else ' — ตรวจ prompt และสิทธิ์ของคีย์'))
    raise GeminiError(f'บริการ Gemini ขัดข้อง (HTTP {r.status_code})')


def _headers(api_key):
    return {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}


def verify_key(api_key: str) -> dict:
    """Cheap check that a pasted key works, before we store it."""
    try:
        r = requests.get(f'{base()}/models', headers={'x-goog-api-key': api_key}, timeout=20)
    except requests.RequestException as e:
        raise GeminiError('เชื่อมต่อ Google ไม่สำเร็จ') from e
    data = _json(_check(r))
    names = {str(m.get('name', '')).split('/')[-1] for m in (data.get('models') or [])}
    return {'ok': True, 'has_omni': MODEL in names, 'model_count': len(names)}


def start_video(api_key: str, prompt: str, *, image: bytes | None = None, mime: str = '',
                aspect: str = '9:16', resolution: str = '720p') -> str:
    """Create a video interaction; returns the Files API file id to poll."""
    if aspect not in ASPECTS:
        raise GeminiError('สัดส่วนวิดีโอไม่ถูกต้อง')
    if resolution not in RESOLUTIONS:
        raise GeminiError('ความละเอียดไม่ถูกต้อง')
    prompt = (prompt or '').strip()
    if not 10 <= len(prompt) <= 4000:
        raise GeminiError('prompt ต้องยาว 10–4000 ตัวอักษร')
    if image:
        if mime not in IMAGE_MIMES or len(image) > MAX_IMAGE_BYTES:
            raise GeminiError('ภาพตัวละครต้องเป็น JPEG/PNG/WEBP ขนาดไม่เกิน 7MB')
        parts = [{'type': 'image', 'data': base64.b64encode(image).decode('ascii'), 'mime_type': mime},
                 {'type': 'text', 'text': prompt}]
    else:
        parts = prompt
    payload = {'model': MODEL, 'input': parts,
               'response_format': {'type': 'video', 'aspect_ratio': aspect,
                                   'resolution': resolution, 'delivery': 'uri'}}
    try:
        r = requests.post(f'{base()}/interactions', headers=_headers(api_key), json=payload, timeout=(10, 180))
    except requests.RequestException as e:
        raise GeminiError('เชื่อมต่อ Gemini ไม่สำเร็จ') from e
    return _file_id(_json(_check(r)))


def _file_id(result: dict) -> str:
    """Pull the generated file id out of the interaction response."""
    for step in result.get('steps') or []:
        for item in (step.get('content') or []) if isinstance(step.get('content'), list) else []:
            if item.get('type') != 'video':
                continue
            uri = item.get('uri') or ''
            m = re.search(r'/files/([A-Za-z0-9_-]{1,128})', uri)
            if m:
                return m.group(1)
    raise GeminiError('Gemini ไม่ส่งลิงก์ไฟล์วิดีโอกลับมา — ลองใหม่อีกครั้ง')


def poll_video(api_key: str, file_id: str) -> tuple[str, str]:
    """Return ('running'|'ready', file_id). Raises on FAILED."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', file_id or ''):
        raise GeminiError('รหัสไฟล์วิดีโอไม่ถูกต้อง')
    try:
        r = requests.get(f'{base()}/files/{file_id}', headers={'x-goog-api-key': api_key}, timeout=25)
    except requests.RequestException as e:
        raise GeminiError('ตรวจสถานะวิดีโอกับ Gemini ไม่สำเร็จ') from e
    state = str(_json(_check(r)).get('state') or '').upper()
    if state == 'FAILED':
        raise GeminiError('Gemini สร้างวิดีโอไม่สำเร็จ — ลองปรับ prompt หรือเลือกเทมเพลตอื่น')
    return ('ready' if state == 'ACTIVE' else 'running'), file_id


def _google_host(url: str) -> bool:
    override = os.getenv('GEMINI_API_BASE', '')
    if override and url.startswith(override):
        return True
    try:
        p = urlparse(url)
        if p.scheme != 'https' or p.username or p.password or p.port:
            return False
        host = (p.hostname or '').lower()
        return any(host == h or host.endswith('.' + h) for h in ('googleapis.com', 'googleusercontent.com'))
    except (ValueError, TypeError):
        return False


def download_video(api_key: str, file_id: str, filepath) -> int:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', file_id or ''):
        raise GeminiError('รหัสไฟล์วิดีโอไม่ถูกต้อง')
    destination = Path(filepath)
    tmp = destination.with_suffix('.download')
    url = f'{base()}/files/{file_id}:download?alt=media'
    try:
        for _ in range(4):
            if not _google_host(url):
                raise GeminiError('ลิงก์ดาวน์โหลดไม่อยู่ในโดเมนของ Google')
            with requests.get(url, headers={'x-goog-api-key': api_key}, timeout=(10, 180),
                              stream=True, allow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.headers.get('Location', ''))
                    continue
                _check(r)
                length = r.headers.get('Content-Length')
                if length and int(length) > MAX_BYTES:
                    raise GeminiError('วิดีโอใหญ่เกิน 100MB')
                tmp.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                with tmp.open('wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        count += len(chunk)
                        if count > MAX_BYTES:
                            raise GeminiError('ไฟล์วิดีโอใหญ่เกินขีดจำกัด')
                        f.write(chunk)
                if count < 12:
                    raise GeminiError('ไฟล์วิดีโอว่างหรือไม่สมบูรณ์')
                tmp.replace(destination)
                return count
        raise GeminiError('ลิงก์ดาวน์โหลดเปลี่ยนเส้นทางมากเกินไป')
    except requests.RequestException as e:
        raise GeminiError('ดาวน์โหลดวิดีโอจาก Gemini ไม่สำเร็จ') from e
    finally:
        if tmp.exists():
            tmp.unlink()
