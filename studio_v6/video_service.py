"""Google Gemini Veo adapter. Calls only Google's fixed endpoints; no user-supplied URLs."""
import base64
from pathlib import Path
from urllib.parse import urlparse
import requests

BASE = 'https://generativelanguage.googleapis.com/v1beta'
MODEL = 'veo-3.1-generate-preview'
MAX_BYTES = 100 * 1024 * 1024

class VideoProviderError(Exception):
    pass


def _json(response):
    try:
        return response.json()
    except Exception as e:
        raise VideoProviderError('ผู้ให้บริการส่งผลลัพธ์ที่อ่านไม่ได้') from e


def _check(response):
    if response.status_code >= 400:
        if response.status_code in (401, 403):
            raise VideoProviderError('Google ไม่อนุญาตให้ใช้คีย์นี้หรือยังไม่มีสิทธิ์ Veo')
        if response.status_code == 429:
            raise VideoProviderError('เครดิต/โควตา API ไม่เพียงพอ หรือมีคำขอมากเกินไป')
        if response.status_code in (400, 404):
            raise VideoProviderError('Google ปฏิเสธคำขอ โปรดตรวจรุ่นโมเดล สิทธิ์ API และ Prompt')
        raise VideoProviderError('บริการ Google Veo ขัดข้อง (HTTP %d)' % response.status_code)
    return response


def start_video(api_key, prompt, image=None, mime=None):
    instance = {'prompt': prompt}
    if image:
        if mime not in ('image/jpeg', 'image/png') or len(image) > 5 * 1024 * 1024:
            raise VideoProviderError('รูปอ้างอิงต้องเป็น JPEG/PNG ขนาดไม่เกิน 5MB')
        instance['image'] = {'inlineData': {'mimeType': mime, 'data': base64.b64encode(image).decode('ascii')}}
    payload = {
        'instances': [instance],
        'parameters': {'aspectRatio': '9:16', 'durationSeconds': '8', 'resolution': '720p', 'numberOfVideos': 1},
    }
    try:
        r = requests.post(f'{BASE}/models/{MODEL}:predictLongRunning',
                          headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'},
                          json=payload, timeout=35)
    except requests.RequestException as e:
        raise VideoProviderError('เชื่อมต่อ Google Veo ไม่สำเร็จ') from e
    result = _json(_check(r))
    name = result.get('name', '')
    if not _valid_operation(name):
        raise VideoProviderError('Google ไม่ส่งรหัสงานวิดีโอที่ถูกต้อง')
    return name


def _valid_operation(name):
    import re
    return (isinstance(name, str) and len(name) <= 256
            and name.startswith(('operations/', 'models/'))
            and bool(re.fullmatch(r'[a-zA-Z0-9._/-]+', name))
            and '..' not in name and name.count('/') >= 1)


def poll_video(api_key, operation_name):
    if not _valid_operation(operation_name):
        raise VideoProviderError('รหัสงานวิดีโอไม่ถูกต้อง')
    try:
        r = requests.get(f'{BASE}/{operation_name}', headers={'x-goog-api-key': api_key}, timeout=25)
    except requests.RequestException as e:
        raise VideoProviderError('ตรวจสถานะ Google Veo ไม่สำเร็จ') from e
    result = _json(_check(r))
    if not result.get('done'):
        return 'running', None
    if result.get('error'):
        raise VideoProviderError('Google Veo สร้างวิดีโอไม่สำเร็จ โปรดตรวจพรอมต์หรือเครดิต')
    response = result.get('response') or {}
    nested = response.get('generateVideoResponse', response)
    samples = nested.get('generatedSamples') or nested.get('generatedVideos') or []
    if not samples:
        raise VideoProviderError('งานเสร็จแล้ว แต่ Google ไม่ส่งไฟล์วิดีโอ')
    item = samples[0]
    uri = (item.get('video') or {}).get('uri')
    if not uri:
        raise VideoProviderError('ไม่พบลิงก์ไฟล์วิดีโอในผลลัพธ์')
    return 'ready', uri


def _google_host(url):
    try:
        p = urlparse(url)
        if p.scheme != 'https' or p.username or p.password or p.port:
            return False
        hostname = (p.hostname or '').lower()
        return any(hostname == h or hostname.endswith('.' + h)
                   for h in ('googleapis.com', 'googleusercontent.com'))
    except (ValueError, TypeError):
        return False


def download_video(api_key, uri, filepath):
    if not _google_host(uri):
        raise VideoProviderError('Google ส่ง URL วิดีโอที่ไม่อยู่ในโดเมนที่อนุญาต')
    destination = Path(filepath)
    tmp = destination.with_suffix('.download')
    url = uri
    for _ in range(4):
        if not _google_host(url):
            raise VideoProviderError('ลิงก์ดาวน์โหลดเปลี่ยนไปยังโดเมนที่ไม่อนุญาต')
        try:
            with requests.get(url, headers={'x-goog-api-key': api_key}, timeout=(10, 100),
                              stream=True, allow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    from urllib.parse import urljoin
                    url = urljoin(url, r.headers.get('Location', ''))
                    continue
                _check(r)
                length = r.headers.get('Content-Length')
                if length and int(length) > MAX_BYTES:
                    raise VideoProviderError('วิดีโอใหญ่เกิน 100MB')
                tmp.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                with tmp.open('wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        count += len(chunk)
                        if count > MAX_BYTES:
                            raise VideoProviderError('ไฟล์วิดีโอใหญ่เกินขีดจำกัด')
                        f.write(chunk)
                if count < 12:
                    raise VideoProviderError('ไฟล์วิดีโอว่างหรือไม่สมบูรณ์')
                tmp.replace(destination)
                return count
        except requests.RequestException as e:
            raise VideoProviderError('ดาวน์โหลดวิดีโอจาก Google ไม่สำเร็จ') from e
        finally:
            if tmp.exists():
                tmp.unlink()
    raise VideoProviderError('ลิงก์ดาวน์โหลดเปลี่ยนเส้นทางมากเกินไป')
