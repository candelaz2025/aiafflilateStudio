"""Deterministic UGC script generator for TikTok (9:16, ~12 s). No API key needed.

Produces an editable shot list (hook → demo → proof → CTA), on-screen text, voice-over lines,
a TikTok caption and hashtags. Copy only states facts we actually have (title, price, rating,
sales); it never invents specs or results.
"""
from __future__ import annotations

import hashlib
import random
import re

from . import copy_rules as rules

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
    'ugc_pov': ['POV: เพิ่งรู้ว่าของชิ้นนี้ช่วยชีวิตได้ขนาดนี้', 'POV: วันธรรมดาที่ง่ายขึ้นเพราะของชิ้นเดียว',
                'POV: ของที่ซื้อแล้วใช้ทุกวันจริง', 'POV: ซื้อมาแบบไม่คิดอะไร แล้วติดใจ',
                'POV: ของชิ้นนี้อยู่ในกระเป๋าตลอด', 'POV: เพื่อนถามทุกคนว่าซื้อที่ไหน',
                'สิ่งที่ใช้ทุกวันจนลืมไปว่าเคยอยู่ได้ยังไง', 'ของชิ้นเดียวที่ไม่เคยเก็บเข้าตู้'],
    'ugc_unboxing': ['แกะกล่องให้ดูกันชัดๆ ได้อะไรบ้าง?', 'ของมาส่งแล้ว! มาแกะไปด้วยกัน',
                     'สั่งมาลองเอง แกะให้ดูไม่มีตัดต่อ', 'เปิดกล่องสดๆ ไม่ได้จัดฉาก',
                     'มาดูกันว่าได้ของครบไหม', 'แกะให้ดูทุกชิ้นในกล่อง',
                     'ของถึงแล้ว เปิดพร้อมกันเลย', 'กล่องมาแล้ว ข้างในจะเป็นยังไง'],
    'ugc_problem': ['ใครเจอปัญหานี้บ่อยๆ ยกมือหน่อย 🙋', 'เบื่อไหม… กับปัญหาเดิมๆ ทุกวัน?',
                    'ปัญหานี้แก้ได้ง่ายกว่าที่คิด', 'ทนกับเรื่องนี้มานานแค่ไหนแล้ว',
                    'ถ้าคุณก็เจอแบบนี้ ดูคลิปนี้ให้จบ', 'เรื่องเล็กๆ ที่กวนใจทุกวัน',
                    'แก้ตรงนี้จุดเดียว สบายขึ้นเยอะ', 'ปัญหาที่หลายคนคิดว่าต้องทนไปตลอด'],
    'ugc_before_after': ['ก่อนมีชิ้นนี้ vs หลังมีชิ้นนี้', 'ความต่างที่เห็นได้ในไม่กี่วินาที',
                         'เทียบให้ดูก่อน/หลังแบบตรงๆ', 'จากเดิมที่วุ่น เป็นแบบนี้แทน',
                         'เปลี่ยนแค่ชิ้นเดียว ต่างกันเท่านี้', 'ซ้ายคือเมื่อก่อน ขวาคือตอนนี้',
                         'ดูความต่างก่อนตัดสินใจ', 'ก่อน-หลัง ถ่ายเองไม่ได้แต่ง'],
    'ugc_3reasons': ['3 เหตุผลที่ฉันไม่คืนของชิ้นนี้', '3 ข้อที่ทำให้ตัดสินใจกดสั่ง',
                     'ถ้าลังเลอยู่ ดู 3 ข้อนี้ก่อน', '3 อย่างที่ชอบหลังใช้มาสักพัก',
                     'ทำไมถึงแนะนำ? มี 3 ข้อ', '3 จุดที่คนมักมองข้าม',
                     'เก็บไว้ดู 3 ข้อก่อนกดซื้อ', '3 เหตุผลสั้นๆ ก่อนเลื่อนผ่าน'],
    'ugc_budget': ['ของดีงบไม่ถึงพัน ต้องมีติดบ้าน', 'คุ้มขนาดนี้ ไม่บอกต่อไม่ได้',
                   'งบน้อยก็ได้ของดี ดูชิ้นนี้', 'ราคานี้ได้เท่านี้ ถือว่าโอเคมาก',
                   'ของถูกที่ใช้ได้จริง มีอยู่', 'จ่ายเท่านี้ ใช้ได้ทุกวัน',
                   'งบจำกัดแต่ไม่อยากได้ของพัง', 'คุ้มไม่คุ้ม ดูตัวเลขเอาเอง'],
}

# Alternative phrasings for the body beats. A regenerate rotates through these, so the
# second script for a product is a different clip, not the same one with a new opener.
BEAT_POOL = {
    'demo': [
        ('ถือ {name} ใกล้กล้อง หมุนให้เห็นรอบตัว', 'งานจริงเป็นแบบนี้', 'ของจริงหน้าตาแบบนี้เลย'),
        ('วาง {name} บนโต๊ะ แล้วค่อยๆ ซูมเข้า', 'ดูใกล้ๆ กัน', 'ซูมให้ดูชัดๆ ไปเลย'),
        ('ใช้ {name} จริงในสถานการณ์ประจำวัน', 'ใช้จริงทุกวัน', 'อันนี้คือใช้จริง ไม่ได้ถือโชว์'),
        ('มือหยิบ {name} ขึ้นมาจากโต๊ะทำงาน', 'หยิบง่าย ใช้ง่าย', 'หยิบมาใช้ได้เลย ไม่ต้องตั้งค่าอะไร'),
    ],
    'use': [
        ('สาธิตการใช้งานจริง 1 ฉาก ไม่ตัดต่อ', 'ใช้ง่ายมาก', 'กดทีเดียวก็ใช้ได้แล้ว'),
        ('ใช้งานในบ้าน มุมกว้างให้เห็นบรรยากาศ', 'สะดวกขึ้นเยอะ', 'สะดวกขึ้นจริง ไม่ต้องคิดเยอะ'),
        ('ใช้นอกบ้าน พกใส่กระเป๋าไปด้วย', 'พกไปไหนก็ได้', 'พกง่าย ใส่กระเป๋าไปได้เลย'),
        ('ใช้ที่โต๊ะทำงาน ระหว่างทำงานจริง', 'ใช้ตอนทำงานได้', 'วางไว้ข้างโต๊ะ ใช้ได้ทั้งวัน'),
    ],
    'proof': [
        ('โคลสอัปรายละเอียดวัสดุและรอยต่อ', '{proof}', 'ลองดูงานประกอบใกล้ๆ ก่อนตัดสินใจ'),
        ('เลื่อนหน้าจอรีวิวของคนที่ซื้อไปแล้ว', '{proof}', 'ดูรีวิวคนซื้อจริงก่อนก็ได้'),
        ('ถือสินค้าเทียบกับมือให้เห็นขนาดจริง', '{proof}', 'ขนาดจริงประมาณนี้ เทียบกับมือ'),
        ('โชว์หน้าจอสินค้าในแอปพร้อมเรตติ้ง', '{proof}', 'ข้อมูลในหน้าสินค้าเป็นแบบนี้'),
    ],
}

CTAS = [
    ('ชี้ลงที่ตะกร้า + โชว์สินค้าอีกครั้ง', 'กดตะกร้าเหลือง 🛒', 'สนใจกดตะกร้าได้เลย เช็กราคาล่าสุดก่อนสั่งนะ'),
    ('มือชี้มุมล่างขวา พร้อมยิ้มเข้ากล้อง', 'ลิงก์อยู่ในตะกร้า 🛒', 'ลิงก์อยู่ในตะกร้าแล้ว ไปดูราคากันได้'),
    ('วางสินค้ากลางเฟรม ค้างไว้ 2 วินาที', 'กดดูในตะกร้าได้เลย', 'ใครสนใจกดเข้าไปดูในตะกร้าก่อนได้'),
    ('ชูสินค้าขึ้นแล้วชี้ไปที่ตะกร้า', 'เช็กราคาในตะกร้า 🛒', 'เช็กราคากับโปรล่าสุดในตะกร้าก่อนนะ'),
]


def _short(title: str, n: int = 38) -> str:
    t = re.sub(r'\s+', ' ', title or '').strip()
    t = re.sub(r'\(สินค้าตัวอย่าง\)', '', t).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + '…'


def _tags(title: str) -> list[str]:
    words = [w for w in re.split(r'[\s/|,()\[\]]+', title) if 2 <= len(w) <= 18][:2]
    base = ['#รีวิว', '#ของดีบอกต่อ', '#TikTokShop', '#ShopeeAffiliate', '#tiktokป้ายยา']
    return base + ['#' + re.sub(r'[^\w฀-๿]', '', w) for w in words if re.sub(r'[^\w฀-๿]', '', w)]


def signature(script: dict) -> str:
    """What makes two scripts 'the same clip' to a viewer: the opener and the on-screen
    beats. Visuals alone changing is not a different clip."""
    parts = [script.get('hook', '')] + [s.get('text', '') for s in script.get('scenes', [])]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


def generate(product: dict, style: str, variant: int = 0, avoid: list[str] | None = None) -> dict:
    """Build one script that is not one the user has already seen.

    `avoid` holds openers and signatures from previous generations; the builder re-rolls
    until it lands somewhere new, so pressing 'สร้างใหม่' always changes the clip.
    """
    used = {str(a).strip() for a in (avoid or []) if a}
    for attempt in range(12):
        out = _build(product, style, variant + attempt * 101, used)
        if signature(out) not in used and out['hook'] not in used:
            return out
    return out


def _build(product: dict, style: str, variant: int, used: set[str]) -> dict:
    if style not in STYLE_IDS:
        raise ValueError('สไตล์ไม่ถูกต้อง')
    title = product.get('title') or 'สินค้า'
    name = _short(title)
    seed = (int(hashlib.sha256(f'{title}|{style}'.encode()).hexdigest()[:12], 16) + variant * 7919) % (2 ** 31)
    rnd = random.Random(seed)
    pool = [h for h in HOOKS[style] if h not in used] or list(HOOKS[style])
    hook = rnd.choice(pool)

    price = product.get('price')
    price_txt = f'฿{price:,.0f}' if isinstance(price, (int, float)) and price else ''
    proof = []
    if product.get('rating'):
        proof.append(f"เรตติ้ง {product['rating']:.1f}/5")
    if product.get('sales'):
        proof.append(f"ขายแล้ว {int(product['sales']):,} ชิ้น")
    proof_txt = ' · '.join(proof)

    def beat(kind):
        visual, text, voice = rnd.choice(BEAT_POOL[kind])
        fill = {'name': name, 'proof': proof_txt or 'งานดีเกินราคา', 'price': price_txt or 'ราคาคุ้ม'}
        return {'visual': visual.format(**fill), 'text': text.format(**fill), 'voice': voice.format(**fill)}

    if style == 'ugc_3reasons':
        mid = [
            {**beat('demo'), 'text': '1) ใช้ง่าย'},
            {**beat('use'), 'text': '2) ใช้ได้ทุกวัน'},
            {**beat('proof'), 'text': f'3) {"ราคา " + price_txt if price_txt else "คุ้มราคา"}'},
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
            beat('demo'),
            {'visual': 'ลองใช้ครั้งแรก', 'text': 'ลองครั้งแรก!', 'voice': 'ลองใช้ครั้งแรก ความรู้สึกคือ…โอเคเลย'},
        ]
    elif style == 'ugc_problem':
        mid = [
            {'visual': 'แสดงปัญหา (สีหน้า/สถานการณ์จริง)', 'text': 'ปัญหาเดิมๆ 😤', 'voice': 'ปัญหานี้เจอบ่อยมาก ใช่ไหม'},
            {'visual': f'หยิบ {name} ขึ้นมา', 'text': 'ทางออกอยู่นี่', 'voice': 'ลองตัวนี้ดู'},
            beat('use'),
        ]
    elif style == 'ugc_budget':
        mid = [
            {'visual': f'โชว์ {name} คู่กับป้ายราคา', 'text': price_txt or 'ราคาน่ารัก',
             'voice': f'ราคาเริ่ม {price_txt} เท่านั้น' if price_txt else 'ราคาไม่แรงเลย'},
            beat('use'),
            beat('proof'),
        ]
    else:  # ugc_pov
        mid = [beat('demo'), beat('use'), beat('proof')]

    scenes = [{'t': '0–2s', 'visual': 'เปิดด้วยหน้าคน/มือ + ตัวหนังสือใหญ่กลางจอ', 'text': hook, 'voice': hook}]
    for i, m in enumerate(mid):
        scenes.append({'t': f'{2 + i * 3}–{5 + i * 3}s', **m})
    cta_v, cta_t, cta_voice = rnd.choice(CTAS)
    scenes.append({'t': f'{2 + len(mid) * 3}–{4 + len(mid) * 3}s', 'visual': cta_v, 'text': cta_t, 'voice': cta_voice})

    for sc in scenes:
        for k in ('text', 'voice'):
            sc[k] = rules.scrub(sc[k])
    caption = rules.scrub(f'{hook} {name}' + (f' ราคา {price_txt}' if price_txt else ''))[:rules.CAPTION_MAX]
    return {'style': style, 'hook': hook, 'scenes': scenes, 'cta': cta_t, 'caption': caption,
            'hashtags': ' '.join(rules.hashtags(title)), 'duration_s': 4 + len(mid) * 3,
            'aspect': '9:16', 'platform': 'tiktok', 'source': 'builtin',
            'placement': rules.PLACEMENT,
            'voice_track': [rules.speakable(s['voice']) for s in scenes],
            'product': {'title': title, 'price_txt': price_txt, 'proof': proof_txt}}


def from_model(data: dict, product: dict, style: str) -> dict:
    """Turn whatever the model returned into our script shape, enforcing the same rules
    the deterministic generator follows. A model is a writer, not an authority."""
    title = product.get('title') or 'สินค้า'
    raw = data.get('scenes') if isinstance(data, dict) else None
    scenes = []
    for i, sc in enumerate(raw or []):
        if not isinstance(sc, dict):
            continue
        scenes.append({
            't': str(sc.get('t') or f'{i * 3}–{i * 3 + 3}s')[:16],
            'visual': rules.scrub(str(sc.get('visual', '')))[:200],
            'text': rules.scrub(str(sc.get('text', '')))[:rules.HEADLINE_MAX],
            'voice': rules.scrub(str(sc.get('voice', '')))[:200],
        })
    if not 2 <= len(scenes) <= 8:
        raise ValueError('บทที่ได้จากโมเดลมีจำนวนฉากไม่ถูกต้อง')
    hook = rules.scrub(str(data.get('hook') or scenes[0]['text']))[:rules.HEADLINE_MAX]
    scenes[0]['text'] = scenes[0]['text'] or hook
    tags = [t for t in str(data.get('hashtags', '')).split() if t.startswith('#')]
    price = product.get('price')
    return {'style': style, 'hook': hook, 'scenes': scenes,
            'cta': scenes[-1]['text'], 'source': 'gemini',
            'angle': str(data.get('angle', ''))[:20],
            'caption': rules.scrub(str(data.get('caption', '')))[:rules.CAPTION_MAX] or hook,
            'hashtags': ' '.join(rules.hashtags(title, tags)),
            'duration_s': 15, 'aspect': '9:16', 'platform': 'tiktok',
            'placement': rules.PLACEMENT,
            'voice_track': [rules.speakable(s['voice']) for s in scenes],
            'product': {'title': title,
                        'price_txt': f'฿{price:,.0f}' if isinstance(price, (int, float)) and price else '',
                        'proof': ' · '.join(filter(None, [
                            f"เรตติ้ง {product['rating']:.1f}/5" if product.get('rating') else '',
                            f"ขายแล้ว {int(product['sales']):,} ชิ้น" if product.get('sales') else '']))}}


def to_text(script: dict) -> str:
    lines = [f"[{s['t']}] ภาพ: {s['visual']} | ข้อความ: {s['text']} | พากย์: {s['voice']}" for s in script['scenes']]
    return '\n'.join(lines) + f"\n\nแคปชั่น: {script['caption']}\n{script['hashtags']}"


def to_prompt(script: dict) -> str:
    title = script.get('product', {}).get('title', 'the product')
    beats = '; '.join(f"{s['t']} {s['visual']}" for s in script.get('scenes', []))
    voice = ' / '.join(script.get('voice_track') or [rules.speakable(s.get('voice', '')) for s in script.get('scenes', [])])
    pl = script.get('placement') or rules.PLACEMENT
    return (f'Vertical {pl["aspect"]} Thai UGC TikTok video (~{script.get("duration_s", 13)}s) of a creator using "{title}". '
            f'Handheld phone look, natural light, authentic hands-on demo, no fake results, no other brand logos. '
            f'Beats: {beats}. '
            f'Thai voice-over, spoken exactly as written: {voice}. '
            f'On-screen Thai captions {pl["position"]} at {pl["y_pct"]}% from top, max {pl["max_width_pct"]}% frame width, '
            f'clear of the product and of platform UI.')[:1800]
