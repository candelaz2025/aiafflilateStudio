"""OpenRouter video adapter (/api/v1/videos). Fixed OpenRouter endpoints only.

One OpenRouter key reaches several video models (Veo, Grok, Kling, Wan).
Never send API keys to the browser.
"""
from __future__ import annotations

import base64
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests

BASE='https://openrouter.ai/api/v1'
# model -> whether to request generated audio. All support 8 s, 720p, 9:16 and a first-frame image.
MODELS={
    'google/veo-3.1-lite': True,
    'google/veo-3.1-fast': True,
    'x-ai/grok-imagine-video-1.5-lite': False,
    'kwaivgi/kling-v3.0-std': True,
    'alibaba/wan-3.0': True,
}
DURATION=8
# Approximate USD list price per 8 s 720p clip as (with audio, without audio), from
# GET /api/v1/videos/models in Oct 2026. Used for budget caps and UI hints, not billing.
PRICES={
    'google/veo-3.1-lite': (0.40, 0.24),
    'google/veo-3.1-fast': (0.80, 0.64),
    'x-ai/grok-imagine-video-1.5-lite': (0.25, 0.25),
    'kwaivgi/kling-v3.0-std': (1.01, 0.67),
    'alibaba/wan-3.0': (0.80, 0.80),
}
MAX_BYTES=100 * 1024 * 1024

class VideoProviderError(Exception):
    pass


def _check(r):
    if r.status_code >= 400:
        if r.status_code in (401, 403):
            raise VideoProviderError('OpenRouter ไม่อนุญาตคีย์นี้ โปรดตรวจ API key')
        if r.status_code == 402:
            raise VideoProviderError('เครดิต OpenRouter ไม่พอ เติมเครดิตที่ openrouter.ai/credits')
        if r.status_code == 429:
            raise VideoProviderError('OpenRouter จำกัดคำขอ โปรดรอสักครู่แล้วสั่งใหม่')
        if r.status_code in (400, 404, 413):
            raise VideoProviderError('OpenRouter ปฏิเสธคำขอ โปรดตรวจโมเดล รูป และ Prompt')
        raise VideoProviderError('บริการ OpenRouter ขัดข้อง (HTTP %d)' % r.status_code)
    return r


def _json(r):
    try:
        data=r.json()
        if not isinstance(data,dict): raise ValueError('not object')
        return data
    except (ValueError, TypeError) as exc:
        raise VideoProviderError('OpenRouter ส่งผลลัพธ์ที่อ่านไม่ได้') from exc


def _valid_job_id(value):
    return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{6,128}',value))


def estimated_cost(model, audio=None):
    with_audio, without_audio = PRICES[model]
    return with_audio if (MODELS[model] if audio is None else audio) else without_audio


def start_video(api_key, prompt, image=None, mime=None, *, model='google/veo-3.1-lite', audio=None, user=None):
    if model not in MODELS:
        raise VideoProviderError('โมเดล OpenRouter ไม่ถูกต้อง')
    payload={'model':model,'prompt':prompt,'duration':DURATION,'resolution':'720p','aspect_ratio':'9:16'}
    # audio=None keeps the model default; False saves cost when a Thai voice-over is added later.
    if MODELS[model] and audio is not False:
        payload['generate_audio']=True
    elif MODELS[model]:
        payload['generate_audio']=False
    if user:
        payload['user']=str(user)[:256]
    if image is not None:
        if mime not in ('image/jpeg','image/png') or not (0<len(image)<=5*1024*1024):
            raise VideoProviderError('ภาพต้องเป็น JPG/PNG ไม่เกิน 5MB')
        # OpenRouter image_url accepts base64 data URLs, so a local server needs no public image host.
        payload['frame_images']=[{'type':'image_url','frame_type':'first_frame',
            'image_url':{'url':f'data:{mime};base64,{base64.b64encode(image).decode("ascii")}'}}]
    try:
        r=requests.post(f'{BASE}/videos',headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'},json=payload,timeout=45)
    except requests.RequestException as exc:
        raise VideoProviderError('เชื่อมต่อ OpenRouter ไม่สำเร็จ') from exc
    result=_json(_check(r))
    jid=result.get('id')
    if not _valid_job_id(jid):
        raise VideoProviderError('OpenRouter ไม่ส่งรหัสงานที่ถูกต้อง')
    return jid


def poll_video(api_key, job_id):
    if not _valid_job_id(job_id):
        raise VideoProviderError('รหัสงาน OpenRouter ไม่ถูกต้อง')
    # Build the URL from the id instead of trusting polling_url from the response.
    try:
        r=requests.get(f'{BASE}/videos/{job_id}',headers={'Authorization':f'Bearer {api_key}'},timeout=30)
    except requests.RequestException as exc:
        raise VideoProviderError('ตรวจสถานะ OpenRouter ไม่สำเร็จ') from exc
    result=_json(_check(r))
    state=result.get('status')
    if state in ('pending','in_progress'):
        return 'running',None
    if state in ('failed','cancelled','expired'):
        raise VideoProviderError('OpenRouter สร้างคลิปไม่สำเร็จ (%s) กรุณาตรวจเนื้อหาและเครดิต' % state)
    if state!='completed':
        raise VideoProviderError('OpenRouter ส่งสถานะงานที่ไม่รู้จัก')
    return 'ready',f'{BASE}/videos/{job_id}/content?index=0'


def _openrouter_api(url):
    try:
        p=urlparse(url)
        return (p.scheme=='https' and not p.username and not p.password and p.port is None
                and (p.hostname or '').lower()=='openrouter.ai' and p.path.startswith('/api/v1/videos/'))
    except (ValueError,TypeError):
        return False


def _safe_redirect(url):
    # The content endpoint may redirect to storage on another host; allow public HTTPS names only.
    try:
        p=urlparse(url)
        host=(p.hostname or '').lower()
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not host:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return host!='localhost' and not host.endswith(('.localhost','.local','.internal'))
    except (ValueError,TypeError):
        return False


def download_video(api_key, url, filepath):
    if not _openrouter_api(url):
        raise VideoProviderError('URL ไม่ใช่ปลายทางวิดีโอของ OpenRouter')
    dest=Path(filepath)
    temp=dest.with_suffix('.download')
    try:
        for _ in range(4):
            if not _safe_redirect(url):
                raise VideoProviderError('ปลายทางดาวน์โหลดไม่อยู่ในโดเมนที่อนุญาต')
            # The key goes only to OpenRouter itself, never to a redirect target.
            headers={'Authorization':f'Bearer {api_key}'} if _openrouter_api(url) else {}
            try:
                with requests.get(url,headers=headers,timeout=(10,120),stream=True,allow_redirects=False) as r:
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
                raise VideoProviderError('ดาวน์โหลดวิดีโอจาก OpenRouter ไม่สำเร็จ') from exc
        raise VideoProviderError('URL วิดีโอเปลี่ยนเส้นทางมากเกินไป')
    finally:
        if temp.exists(): temp.unlink()
