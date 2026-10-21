"""Product images with the user's own Gemini key (the Gemini image models, "Nano Banana").

When the product already has a photo, that photo goes in as the reference and the model
is told to keep the product itself unchanged — only the setting, light and framing move.
A buyer must receive the thing in the picture; an affiliate image that invents a better
product than the one on sale is a misleading ad, not a nicer thumbnail.
"""
from __future__ import annotations

import base64
import os

import requests

TIMEOUT = 120
DEFAULT_MODEL = 'gemini-2.5-flash-image'
PREFERRED = ('gemini-3.1-flash-image-preview', 'gemini-2.5-flash-image', 'gemini-2.5-flash-image-preview')
MAX_REF_BYTES = 7 * 1024 * 1024
OUT_TYPES = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}

STYLES = [
    {'id': 'studio', 'label': 'สตูดิโอพื้นขาว', 'prompt': 'clean e-commerce studio shot on a seamless white background, soft even lighting, gentle shadow under the product'},
    {'id': 'lifestyle', 'label': 'ใช้งานจริงในบ้าน', 'prompt': 'natural lifestyle scene in a bright modern Thai home, the product in use on a table, daylight from a window'},
    {'id': 'flatlay', 'label': 'Flat lay ด้านบน', 'prompt': 'top-down flat lay on a light textured surface with a few tasteful related props, balanced composition'},
    {'id': 'promo', 'label': 'แบนเนอร์โปรโมต', 'prompt': 'bold promotional product shot on a vivid gradient background with dramatic rim light, space left at the top for a headline, no text'},
]
STYLE_IDS = {s['id'] for s in STYLES}


class GeminiImageError(Exception):
    pass


def base() -> str:
    return os.getenv('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise GeminiImageError(f'Gemini ตอบกลับไม่ใช่ JSON (HTTP {r.status_code})')
    err = data.get('error') if isinstance(data, dict) else None
    if err or r.status_code >= 400:
        if r.status_code in (401, 403):
            raise GeminiImageError('คีย์ Gemini ใช้ไม่ได้หรือไม่มีสิทธิ์สร้างรูป')
        if r.status_code == 429:
            raise GeminiImageError('โควต้าสร้างรูปของ Gemini เต็มชั่วคราว')
        msg = err.get('message') if isinstance(err, dict) else (str(err) if err else f'HTTP {r.status_code}')
        raise GeminiImageError(f'Gemini: {msg}'[:300])
    return data


def pick_model(api_key: str) -> str:
    """The image model this key can actually call, rather than a guessed name."""
    try:
        r = requests.get(f'{base()}/models', headers={'x-goog-api-key': api_key}, timeout=20)
        names = {str(m.get('name', '')).split('/')[-1] for m in (_check(r).get('models') or [])}
    except (requests.RequestException, GeminiImageError):
        return DEFAULT_MODEL
    for m in PREFERRED:
        if m in names:
            return m
    found = sorted(n for n in names if n.startswith('gemini') and 'image' in n)
    return found[0] if found else DEFAULT_MODEL


def build_prompt(title: str, style_id: str, has_reference: bool) -> str:
    style = next((s for s in STYLES if s['id'] == style_id), STYLES[0])
    if has_reference:
        return (f'Create a new square product photo of the exact product shown in the reference image ("{title}"). '
                f'Keep the product itself identical: same shape, colours, proportions, materials, buttons, labels '
                f'and any printing. Do not add features, accessories or text that are not on the real product. '
                f'Change only the setting: {style["prompt"]}. Photorealistic, sharp focus on the product, '
                f'no watermark, no added text or logos.')
    return (f'Create a square, photorealistic product photo of: "{title}". {style["prompt"]}. '
            f'Plain and honest depiction, no added text, no logos, no watermark, no exaggerated effects.')


def generate(api_key: str, title: str, style_id: str = 'studio', *, reference: bytes | None = None,
             reference_mime: str = 'image/jpeg', model: str = '') -> tuple[bytes, str]:
    if style_id not in STYLE_IDS:
        style_id = 'studio'
    parts = [{'text': build_prompt(title, style_id, bool(reference))}]
    if reference:
        if len(reference) > MAX_REF_BYTES:
            raise GeminiImageError('รูปต้นฉบับใหญ่เกิน 7MB')
        parts.append({'inlineData': {'mimeType': reference_mime or 'image/jpeg',
                                     'data': base64.b64encode(reference).decode()}})
    body = {'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '1:1'}}}
    try:
        r = requests.post(f'{base()}/models/{model or DEFAULT_MODEL}:generateContent', json=body, timeout=TIMEOUT,
                          headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'})
    except requests.RequestException as e:
        raise GeminiImageError('เชื่อมต่อ Gemini ไม่สำเร็จ') from e
    data = _check(r)
    for cand in data.get('candidates') or []:
        for part in (cand.get('content') or {}).get('parts') or []:
            if part.get('thought'):
                continue  # intermediate drafts, not the answer
            inline = part.get('inlineData') or part.get('inline_data')
            if inline and inline.get('data'):
                mime = inline.get('mimeType') or inline.get('mime_type') or 'image/png'
                if mime not in OUT_TYPES:
                    mime = 'image/png'
                return base64.b64decode(inline['data']), mime
    reason = ((data.get('candidates') or [{}])[0].get('finishReason') or
              (data.get('promptFeedback') or {}).get('blockReason') or '')
    raise GeminiImageError('Gemini ไม่ได้ส่งรูปกลับมา' + (f' ({reason})' if reason else ' — ลองเปลี่ยนสไตล์แล้วสร้างใหม่'))
