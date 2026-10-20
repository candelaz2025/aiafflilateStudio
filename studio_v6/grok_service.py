"""xAI Grok Imagine REST adapter. Fixed xAI endpoints, validated output host.

No external login automation. Never send API keys to the browser.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests

BASE='https://api.x.ai/v1'
MODELS=('grok-imagine-video-1.5-lite', 'grok-imagine-video-1.5')
MAX_BYTES=100 * 1024 * 1024

class VideoProviderError(Exception):
    pass


def _check(r):
    if r.status_code >= 400:
        if r.status_code in (401, 403):
            raise VideoProviderError('xAI ไม่อนุญาตคีย์นี้ หรือบัญชีไม่มีสิทธิ์สร้างวิดีโอ')
        if r.status_code == 429:
            raise VideoProviderError('xAI จำกัดคำขอหรือเครดิต API ไม่เพียงพอ')
        if r.status_code in (400, 404):
            raise VideoProviderError('xAI ปฏิเสธคำขอ โปรดตรวจโมเดล รูป และ Prompt')
        raise VideoProviderError('บริการ xAI ขัดข้อง (HTTP %d)' % r.status_code)
    return r


def _json(r):
    try:
        data=r.json()
        if not isinstance(data,dict): raise ValueError('not object')
        return data
    except (ValueError, TypeError) as exc:
        raise VideoProviderError('xAI ส่งผลลัพธ์ที่อ่านไม่ได้') from exc


def _valid_request_id(value):
    return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{8,128}',value))


def start_video(api_key, prompt, image=None, mime=None, *, model='grok-imagine-video-1.5-lite', duration=10):
    if model not in MODELS or not isinstance(duration,int) or not (1 <= duration <= 15):
        raise VideoProviderError('โมเดลหรือความยาว Grok ไม่ถูกต้อง')
    payload={'model':model,'prompt':prompt,'duration':duration,'aspect_ratio':'9:16','resolution':'720p'}
    if image is not None:
        if mime not in ('image/jpeg','image/png') or not (0<len(image)<=5*1024*1024):
            raise VideoProviderError('ภาพต้องเป็น JPG/PNG ไม่เกิน 5MB')
        # Official API image.url accepts base64 data URLs. Image-to-video matches image aspect ratio.
        payload['image']={'url':f'data:{mime};base64,{base64.b64encode(image).decode("ascii")}'}
    try:
        r=requests.post(f'{BASE}/videos/generations',headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'},json=payload,timeout=45)
    except requests.RequestException as exc:
        raise VideoProviderError('เชื่อมต่อ xAI ไม่สำเร็จ') from exc
    result=_json(_check(r))
    rid=result.get('request_id')
    if not _valid_request_id(rid):
        raise VideoProviderError('xAI ไม่ส่งรหัสงานที่ถูกต้อง')
    return rid


def poll_video(api_key, request_id):
    if not _valid_request_id(request_id):
        raise VideoProviderError('รหัสงาน xAI ไม่ถูกต้อง')
    try:
        r=requests.get(f'{BASE}/videos/{request_id}',headers={'Authorization':f'Bearer {api_key}'},timeout=30)
    except requests.RequestException as exc:
        raise VideoProviderError('ตรวจสถานะ xAI ไม่สำเร็จ') from exc
    result=_json(_check(r))
    state=result.get('status')
    if state in ('pending','queued','running','in_progress'):
        return 'running',None
    if state=='failed':
        raise VideoProviderError('xAI สร้างคลิปไม่สำเร็จ กรุณาตรวจเนื้อหาและเครดิต')
    if state!='done':
        raise VideoProviderError('xAI ส่งสถานะงานที่ไม่รู้จัก')
    video=result.get('video') or {}
    if video.get('respect_moderation') is False:
        raise VideoProviderError('วิดีโอถูกกรองตามนโยบายของ xAI')
    url=video.get('url')
    if not _xai_host(url):
        raise VideoProviderError('xAI ไม่ได้ส่งลิงก์วิดีโอที่อนุญาต')
    return 'ready',url


def _xai_host(url):
    try:
        p=urlparse(url)
        return (p.scheme=='https' and not p.username and not p.password and p.port is None
                and (p.hostname or '').lower()=='vidgen.x.ai')
    except (ValueError,TypeError):
        return False


def download_video(api_key, url, filepath):
    if not _xai_host(url):
        raise VideoProviderError('URL ไม่ใช่โดเมนวิดีโอที่เชื่อถือได้ของ xAI')
    dest=Path(filepath)
    temp=dest.with_suffix('.download')
    try:
        for _ in range(4):
            if not _xai_host(url):
                raise VideoProviderError('ปลายทางดาวน์โหลดไม่อยู่ในโดเมน xAI ที่อนุญาต')
            try:
                with requests.get(url,timeout=(10,120),stream=True,allow_redirects=False) as r:
                    if r.status_code in (301,302,303,307,308):
                        url=urljoin(url,r.headers.get('Location',''))
                        continue
                    _check(r)
                    size=r.headers.get('Content-Length')
                    if size and int(size)>MAX_BYTES:
                        raise VideoProviderError('ไฟล์วิดีโอใหญ่เกิน 100 MB')
                    temp.parent.mkdir(parents=True,exist_ok=True)
                    total=0
                    with temp.open('wb') as f:
                        for part in r.iter_content(chunk_size=1024*1024):
                            if not part: continue
                            total+=len(part)
                            if total>MAX_BYTES:
                                raise VideoProviderError('ไฟล์วิดีโอใหญ่เกิน 100 MB')
                            f.write(part)
                    if total<12:
                        raise VideoProviderError('ไฟล์วิดีโอว่างหรือเสียหาย')
                    temp.replace(dest)
                    return total
            except requests.RequestException as exc:
                raise VideoProviderError('ดาวน์โหลดวิดีโอจาก xAI ไม่สำเร็จ') from exc
        raise VideoProviderError('URL วิดีโอเปลี่ยนเส้นทางมากเกินไป')
    finally:
        if temp.exists(): temp.unlink()
