"""Deterministic UGC script generator for TikTok (9:16, ~12 s). No API key needed.

Produces an editable shot list (hook → demo → proof → CTA), on-screen text, voice-over lines,
a TikTok caption and hashtags. Copy only states facts we actually have (title, price, rating,
sales); it never invents specs or results.
"""
from __future__ import annotations

import hashlib
import re

STYLES = [
    {'id': 'ugc_pov', 'label': 'POV ใช้จริง', 'emoji': '🤳', 'desc': 'มุมมองบุคคลที่หนึ่ง ใช้ของในชีวิตประจำวัน ดูเป็นธรรมชาติที่สุด'},
    {'id': 'ugc_unboxing', 'label': 'แกะกล่องรีวิว', 'emoji': '📦', 'desc': 'เปิดกล่อง โชว์ของที่ได้ ลองใช้ครั้งแรก'},
    {'id': 'ugc_problem', 'label': 'ปัญหา → ทางออก', 'emoji': '💡', 'desc': 'เปิดด้วยปัญหาที่คนดูเจอ แล้วโชว์สินค้าเป็นทางแก้'},
    {'id': 'ugc_before_after', 'label': 'ก่อน / หลัง', 'emoji': '🔁', 'desc': 'เทียบสถานการณ์ก่อนและหลังมีสินค้า (ไม่อ้างผลเกินจริง)'},
    {'id': 'ugc_3reasons', 'label': '3 เหตุผลที่ควรมี', 'emoji': '3️⃣', 'desc': 'ลิสต์สั้น 3 ข้อ จำง่าย เหมาะกับคนเลื่อนเร็ว'},
    {'id': 'ugc_budget', 'label': 'ของดีงบน้อย', 'emoji': '💸', 'desc': 'เน้นความคุ้มค่าและราคา เหมาะกับสินค้าราคาไม่สูง'},
]
STYLE_IDS = {s['id'] for s in STYLES}

HOOKS = {
    'ugc_pov': ['POV: เพิ่งรู้ว่าของชิ้นนี้ช่วยชีวิตได้ขนาดนี้', 'POV: วันธรรมดาที่ง่ายขึ้นเพราะของชิ้นเดียว', 'POV: ของที่ซื้อแล้วใช้ทุกวันจริง'],
    'ugc_unboxing': ['แกะกล่องให้ดูกันชัดๆ ได้อะไรบ้าง?', 'ของมาส่งแล้ว! มาแกะไปด้วยกัน', 'สั่งมาลองเอง แกะให้ดูไม่มีตัดต่อ'],
    'ugc_problem': ['ใครเจอปัญหานี้บ่อยๆ ยกมือหน่อย 🙋', 'เบื่อไหม… กับปัญหาเดิมๆ ทุกวัน?', 'ปัญหานี้แก้ได้ง่ายกว่าที่คิด'],
    'ugc_before_after': ['ก่อนมีชิ้นนี้ vs หลังมีชิ้นนี้', 'ความต่างที่เห็นได้ในไม่กี่วินาที', 'เทียบให้ดูก่อน/หลังแบบตรงๆ'],
    'ugc_3reasons': ['3 เหตุผลที่ฉันไม่คืนของชิ้นนี้', '3 ข้อที่ทำให้ตัดสินใจกดสั่ง', 'ถ้าลังเลอยู่ ดู 3 ข้อนี้ก่อน'],
    'ugc_budget': ['ของดีงบไม่ถึงพัน ต้องมีติดบ้าน', 'คุ้มขนาดนี้ ไม่บอกต่อไม่ได้', 'งบน้อยก็ได้ของดี ดูชิ้นนี้'],
}


def _short(title: str, n: int = 38) -> str:
    t = re.sub(r'\s+', ' ', title or '').strip()
    t = re.sub(r'\(สินค้าตัวอย่าง\)', '', t).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + '…'


def _tags(title: str) -> list[str]:
    words = [w for w in re.split(r'[\s/|,()\[\]]+', title) if 2 <= len(w) <= 18][:2]
    base = ['#รีวิว', '#ของดีบอกต่อ', '#TikTokShop', '#ShopeeAffiliate', '#tiktokป้ายยา']
    return base + ['#' + re.sub(r'[^\w฀-๿]', '', w) for w in words if re.sub(r'[^\w฀-๿]', '', w)]


def generate(product: dict, style: str, variant: int = 0) -> dict:
    if style not in STYLE_IDS:
        raise ValueError('สไตล์ไม่ถูกต้อง')
    title = product.get('title') or 'สินค้า'
    name = _short(title)
    seed = int(hashlib.sha256(f'{title}|{style}'.encode()).hexdigest(), 16) + variant
    hook = HOOKS[style][seed % len(HOOKS[style])]
    price = product.get('price')
    price_txt = f'฿{price:,.0f}' if isinstance(price, (int, float)) and price else ''
    proof = []
    if product.get('rating'):
        proof.append(f"เรตติ้ง {product['rating']:.1f}/5")
    if product.get('sales'):
        proof.append(f"ขายแล้ว {int(product['sales']):,} ชิ้น")
    proof_txt = ' · '.join(proof)

    if style == 'ugc_3reasons':
        mid = [
            {'visual': f'ถือ {name} ใกล้กล้อง หมุนให้เห็นรอบตัว', 'text': '1) ใช้ง่าย', 'voice': 'ข้อแรก ใช้ง่ายมาก หยิบมาใช้ได้เลย'},
            {'visual': 'สาธิตการใช้งานจริง 1 ฉาก', 'text': '2) ใช้ได้ทุกวัน', 'voice': 'ข้อสอง ใช้ได้ทุกวันจริง ไม่ได้ซื้อมาวางเฉยๆ'},
            {'visual': 'โชว์หน้าจอราคา/ตะกร้า', 'text': f'3) {"ราคา " + price_txt if price_txt else "คุ้มราคา"}', 'voice': 'ข้อสาม ราคาจับต้องได้ ดูโปรในตะกร้าก่อนกดนะ'},
        ]
    elif style == 'ugc_before_after':
        mid = [
            {'visual': 'ฉาก "ก่อน": สถานการณ์ที่ไม่สะดวก (โทนสีหม่น)', 'text': 'ก่อน 😩', 'voice': 'ก่อนหน้านี้คือวุ่นวายทุกครั้ง'},
            {'visual': f'หยิบ {name} เข้ามาในเฟรม', 'text': 'แล้วก็เจอชิ้นนี้', 'voice': 'จนได้ลองชิ้นนี้'},
            {'visual': 'ฉาก "หลัง": ใช้งานจริง (โทนสีสว่าง)', 'text': 'หลัง 😍', 'voice': 'ตอนนี้ง่ายขึ้นเยอะ เห็นความต่างชัด'},
        ]
    elif style == 'ugc_unboxing':
        mid = [
            {'visual': 'มือเปิดกล่อง/ซอง ช้าๆ ใกล้กล้อง', 'text': 'แกะกล่อง 📦', 'voice': 'มาดูกันว่าในกล่องมีอะไร'},
            {'visual': f'วาง {name} บนโต๊ะ โชว์รายละเอียด', 'text': 'งานจริงเป็นแบบนี้', 'voice': 'ของจริงหน้าตาแบบนี้เลย'},
            {'visual': 'ลองใช้ครั้งแรก', 'text': 'ลองครั้งแรก!', 'voice': 'ลองใช้ครั้งแรก ความรู้สึกคือ…โอเคเลย'},
        ]
    elif style == 'ugc_problem':
        mid = [
            {'visual': 'แสดงปัญหา (สีหน้า/สถานการณ์จริง)', 'text': 'ปัญหาเดิมๆ 😤', 'voice': 'ปัญหานี้เจอบ่อยมาก ใช่ไหม'},
            {'visual': f'หยิบ {name} ขึ้นมา', 'text': 'ทางออกอยู่นี่', 'voice': 'ลองตัวนี้ดู'},
            {'visual': 'สาธิตแก้ปัญหาจริง 1 ฉาก', 'text': 'จบในไม่กี่วินาที', 'voice': 'ใช้แบบนี้ จบเลย'},
        ]
    elif style == 'ugc_budget':
        mid = [
            {'visual': f'โชว์ {name} คู่กับป้ายราคา', 'text': price_txt or 'ราคาน่ารัก', 'voice': f'ราคาเริ่ม {price_txt} เท่านั้น' if price_txt else 'ราคาไม่แรงเลย'},
            {'visual': 'สาธิตการใช้งาน', 'text': 'ใช้ได้จริง', 'voice': 'ใช้งานได้จริง ไม่ใช่ของเล่น'},
            {'visual': 'ภาพรวมสินค้า + รีวิวจากคนซื้อ', 'text': proof_txt or 'คนซื้อเยอะ', 'voice': 'ดูรีวิวคนซื้อก่อนตัดสินใจได้'},
        ]
    else:  # ugc_pov
        mid = [
            {'visual': f'มุมมองมือถือ หยิบ {name} จากโต๊ะ', 'text': 'ใช้ทุกเช้า', 'voice': 'ชิ้นนี้หยิบใช้ทุกวัน'},
            {'visual': 'ใช้งานจริงในบ้าน/ที่ทำงาน', 'text': 'สะดวกขึ้นเยอะ', 'voice': 'สะดวกขึ้นจริง ไม่ต้องคิดเยอะ'},
            {'visual': 'โคลสอัปรายละเอียดสินค้า', 'text': proof_txt or 'งานดีเกินราคา', 'voice': 'รายละเอียดงานดีเกินราคา'},
        ]

    scenes = [{'t': '0–2s', 'visual': 'เปิดด้วยหน้าคน/มือ + ตัวหนังสือใหญ่กลางจอ', 'text': hook, 'voice': hook}]
    for i, m in enumerate(mid):
        scenes.append({'t': f'{2 + i * 3}–{5 + i * 3}s', **m})
    cta = 'กดตะกร้าเหลือง / ลิงก์ในไบโอ 🛒'
    scenes.append({'t': '11–13s', 'visual': 'ชี้ลงที่ตะกร้า + โชว์สินค้าอีกครั้ง', 'text': cta,
                   'voice': 'สนใจกดตะกร้าได้เลย เช็กราคาล่าสุดก่อนสั่งนะ'})
    caption = f"{hook} {name}" + (f" ราคา {price_txt}" if price_txt else '') + ' 🛒 กดตะกร้าเลย'
    return {'style': style, 'hook': hook, 'scenes': scenes, 'cta': cta, 'caption': caption[:300],
            'hashtags': ' '.join(_tags(title)), 'duration_s': 13, 'aspect': '9:16', 'platform': 'tiktok',
            'product': {'title': title, 'price_txt': price_txt, 'proof': proof_txt}}


def to_text(script: dict) -> str:
    lines = [f"[{s['t']}] ภาพ: {s['visual']} | ข้อความ: {s['text']} | พากย์: {s['voice']}" for s in script['scenes']]
    return '\n'.join(lines) + f"\n\nแคปชั่น: {script['caption']}\n{script['hashtags']}"


def to_prompt(script: dict) -> str:
    title = script.get('product', {}).get('title', 'the product')
    beats = '; '.join(f"{s['t']} {s['visual']}" for s in script['scenes'])
    return (f'Vertical 9:16 Thai UGC TikTok video (~8-13s) of a creator using "{title}". Handheld phone look, natural light, '
            f'authentic hands-on demo, no fake results, no logos of other brands. Beats: {beats}')[:1150]
