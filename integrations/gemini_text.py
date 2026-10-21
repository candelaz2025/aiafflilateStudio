"""Script writing with the user's own Gemini key.

The deterministic generator in ugc.py never runs out of correctness but it does run out
of ideas — it recombines fixed phrases. With a key connected, the script comes from the
model instead, which is what makes two clips for the same product genuinely different.

The prompt carries the rules from copy_rules: one angle, claims only from data we hold,
no hype vocabulary, a caption within its limit and exactly five hashtags.
"""
from __future__ import annotations

import json
import os
import re

import requests

from . import copy_rules as rules

TIMEOUT = 60
DEFAULT_MODEL = 'gemini-2.5-flash'
FALLBACK_MODELS = ('gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash')


class GeminiTextError(Exception):
    pass


def base() -> str:
    return os.getenv('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise GeminiTextError(f'Gemini ตอบกลับไม่ใช่ JSON (HTTP {r.status_code})')
    err = data.get('error') if isinstance(data, dict) else None
    if err:
        msg = err.get('message') if isinstance(err, dict) else str(err)
        if r.status_code in (401, 403):
            raise GeminiTextError('คีย์ Gemini ใช้ไม่ได้หรือหมดสิทธิ์ — ตรวจคีย์ในเมนู "คีย์ API"')
        if r.status_code == 429:
            raise GeminiTextError('โควต้า Gemini เต็มชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่')
        raise GeminiTextError(f'Gemini: {msg}'[:300])
    if r.status_code >= 400:
        raise GeminiTextError(f'Gemini ขัดข้อง (HTTP {r.status_code})')
    return data


def pick_model(api_key: str) -> str:
    """Use the best text model this key can actually see, rather than assuming one."""
    try:
        r = requests.get(f'{base()}/models', headers={'x-goog-api-key': api_key}, timeout=20)
        names = {str(m.get('name', '')).split('/')[-1] for m in (_check(r).get('models') or [])}
    except (requests.RequestException, GeminiTextError):
        return DEFAULT_MODEL
    for m in FALLBACK_MODELS:
        if m in names:
            return m
    text_models = sorted(n for n in names if 'flash' in n and 'omni' not in n and 'image' not in n)
    return text_models[0] if text_models else DEFAULT_MODEL


SYSTEM = f"""คุณคือนักเขียนบทคลิปสั้นสาย Affiliate ชาวไทย เขียนบทคลิปแนวตั้ง 9:16 ความยาวประมาณ 12-15 วินาที
สำหรับ TikTok / Reels โดยคนธรรมดาถ่ายเองด้วยมือถือ

กฎที่ห้ามละเมิด:
1. เลือก "มุมเล่า" เพียงหนึ่งมุมต่อคลิป ไม่ใช่ยัดทุกจุดขาย เลือกจาก: {', '.join(a['label'] for a in rules.ANGLES)}
2. พูดได้เฉพาะสิ่งที่มีข้อมูลรองรับ (ชื่อ ราคา เรตติ้ง ยอดขายที่ให้มา) ห้ามแต่งสเปก ห้ามแต่งรีวิว
   ห้ามแต่งราคา ห้ามอ้างผลลัพธ์ที่พิสูจน์ไม่ได้
3. ห้ามใช้คำเหล่านี้เด็ดขาด: {', '.join(rules.BANNED[:12])}
4. ข้อความบนจอแต่ละฉากยาวไม่เกิน {rules.HEADLINE_MAX} ตัวอักษร
5. แคปชั่นยาวไม่เกิน {rules.CAPTION_MAX} ตัวอักษร และตามด้วยแฮชแท็ก {rules.HASHTAG_COUNT} ตัวที่ไม่ซ้ำกัน
6. บทพากย์ต้องเป็นภาษาพูดที่คนไทยพูดจริง สั้น กระชับ ไม่เป็นภาษาเขียน

ตอบกลับเป็น JSON อย่างเดียว ไม่ต้องมีคำอธิบายหรือ markdown fence:
{{"angle":"problem|benefit|question","hook":"ข้อความเปิดบนจอ",
 "scenes":[{{"t":"0-2s","visual":"สิ่งที่เห็นในเฟรม","text":"ข้อความบนจอ","voice":"บทพากย์"}}],
 "caption":"แคปชั่น","hashtags":"#a #b #c #d #e"}}
ต้องมี 4-6 ฉาก ฉากสุดท้ายเป็น call-to-action ชวนกดตะกร้า"""


def _product_brief(product: dict) -> str:
    lines = [f"ชื่อสินค้า: {product.get('title') or 'ไม่ระบุ'}"]
    if product.get('price'):
        lines.append(f"ราคา: {float(product['price']):,.0f} บาท")
    if product.get('rating'):
        lines.append(f"เรตติ้ง: {float(product['rating']):.1f} จาก 5")
    if product.get('sales'):
        lines.append(f"ยอดขาย: {int(product['sales']):,} ชิ้น")
    if product.get('discount_rate'):
        lines.append(f"ส่วนลด: {float(product['discount_rate']):.0f}%")
    lines.append('ข้อมูลมีเท่านี้ อย่าเติมสเปกหรือคุณสมบัติที่ไม่ได้อยู่ในรายการนี้')
    return '\n'.join(lines)


def _extract_json(text: str) -> dict:
    t = re.sub(r'^```(?:json)?|```$', '', (text or '').strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if not m:
            raise GeminiTextError('Gemini ตอบกลับไม่เป็นรูปแบบที่อ่านได้ ลองสร้างใหม่อีกครั้ง')
        try:
            return json.loads(m.group(0))
        except ValueError:
            raise GeminiTextError('Gemini ตอบกลับไม่เป็นรูปแบบที่อ่านได้ ลองสร้างใหม่อีกครั้ง')


def write_script(api_key: str, product: dict, style_label: str, *, avoid: list[str] | None = None,
                 model: str = '', temperature: float = 1.1) -> dict:
    """Ask Gemini for one script. `avoid` lists hooks already shown to this user, so a
    regenerate is required to come back with something new rather than a reshuffle."""
    ask = [f'สไตล์คลิป: {style_label}', '', _product_brief(product)]
    if avoid:
        ask += ['', 'ห้ามเขียนให้ซ้ำหรือคล้ายกับประโยคเปิดเหล่านี้ที่เคยสร้างไปแล้ว:']
        ask += [f'- {a}' for a in avoid[:8]]
        ask.append('ต้องเปลี่ยนทั้งมุมเล่า ประโยคเปิด และบทพากย์ให้ต่างออกไปอย่างชัดเจน')
    body = {
        'systemInstruction': {'parts': [{'text': SYSTEM}]},
        'contents': [{'role': 'user', 'parts': [{'text': '\n'.join(ask)}]}],
        'generationConfig': {'temperature': temperature, 'topP': 0.95,
                             'maxOutputTokens': 2048, 'responseMimeType': 'application/json'},
    }
    use = model or DEFAULT_MODEL
    try:
        r = requests.post(f'{base()}/models/{use}:generateContent', json=body, timeout=TIMEOUT,
                          headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'})
    except requests.RequestException as e:
        raise GeminiTextError('เชื่อมต่อ Gemini ไม่สำเร็จ') from e
    data = _check(r)
    cands = data.get('candidates') or []
    if not cands:
        raise GeminiTextError('Gemini ไม่ได้ส่งบทกลับมา — อาจติดตัวกรองเนื้อหา ลองเปลี่ยนชื่อสินค้าหรือสไตล์')
    parts = (cands[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts)
    return _extract_json(text)


LISTING_SYSTEM = f"""คุณคือนักเขียนหน้าสินค้าภาษาไทยสำหรับร้านค้าออนไลน์และงาน Affiliate
งาน: เขียนชื่อสินค้าใหม่ให้อ่านง่ายและค้นเจอ และเขียนรายละเอียดสั้นๆ จากข้อมูลที่ให้มาเท่านั้น

กฎที่ห้ามละเมิด:
1. ชื่อสินค้ายาวไม่เกิน 100 ตัวอักษร ขึ้นต้นด้วยชนิดสินค้า ตามด้วยจุดเด่นที่มีอยู่ในชื่อเดิม ไม่ใส่อิโมจิ ไม่ใส่ราคา
2. ห้ามเพิ่มสเปก ขนาด วัสดุ จำนวน หรือคุณสมบัติที่ไม่ได้อยู่ในชื่อเดิม ถ้าชื่อเดิมไม่บอก ก็ห้ามเดา
3. ห้ามใช้คำเหล่านี้: {', '.join(rules.BANNED[:12])}
4. รายละเอียด 3-5 บรรทัด แต่ละบรรทัดขึ้นต้นด้วย "• " เขียนว่าเหมาะกับใคร ใช้ทำอะไร จากสิ่งที่ชื่อบอกได้จริง
5. ห้ามแต่งรีวิว ห้ามอ้างผลลัพธ์ทางสุขภาพหรือความงาม

ตอบเป็น JSON อย่างเดียว: {{"title":"ชื่อใหม่","description":"• ...\\n• ..."}}"""


def rewrite_listing(api_key: str, product: dict, *, model: str = '') -> dict:
    """A cleaner title and a short description, built only from what the product record says."""
    ask = [_product_brief(product)]
    if product.get('shop_name'):
        ask.append(f"ร้าน: {product['shop_name']}")
    body = {'systemInstruction': {'parts': [{'text': LISTING_SYSTEM}]},
            'contents': [{'role': 'user', 'parts': [{'text': '\n'.join(ask)}]}],
            'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 1024, 'responseMimeType': 'application/json'}}
    try:
        r = requests.post(f'{base()}/models/{model or DEFAULT_MODEL}:generateContent', json=body, timeout=TIMEOUT,
                          headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'})
    except requests.RequestException as e:
        raise GeminiTextError('เชื่อมต่อ Gemini ไม่สำเร็จ') from e
    data = _check(r)
    parts = ((data.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    out = _extract_json(''.join(p.get('text', '') for p in parts))
    title = rules.scrub(str(out.get('title', '')).strip())[:120]
    # A line built around a banned claim is dropped whole — cutting the phrase out of it
    # leaves a fragment ("• หายทันทีเมื่อใช้" → "• เมื่อใช้") that reads as nonsense.
    desc = '\n'.join(line.strip() for line in str(out.get('description', '')).splitlines()
                      if line.strip() and not rules.banned_in(line))[:1200]
    if len(title) < 3:
        raise GeminiTextError('Gemini ไม่ได้ส่งชื่อสินค้าที่ใช้ได้กลับมา')
    return {'title': title, 'description': desc}
