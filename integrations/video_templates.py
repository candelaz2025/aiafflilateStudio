"""Video style templates (แนววิดีโอ) for the Gemini Omni clip generator.

Each template turns the product + UGC script into a camera/lighting/pacing
description. Keeping these server-side means the prompt we send is ours, not
free-form user text sent straight to the model.
"""
from __future__ import annotations

TEMPLATES = [
    {'id': 'studio_product', 'name': 'ภาพสินค้าสตูดิโอ', 'icon': '📦',
     'desc': 'สินค้าเด่นกลางจอ พื้นหลังสะอาด แสงนุ่ม กล้องหมุนช้า',
     'style': 'Clean studio product shot on a seamless white backdrop, soft diffused key light with gentle rim light, '
              'slow smooth orbit around the product, shallow depth of field, crisp focus on the product, premium commercial look.'},
    {'id': 'ugc_handheld', 'name': 'UGC ถือมือถือรีวิว', 'icon': '🤳',
     'desc': 'เหมือนรีวิวจริงจากมือถือ ภาพสั่นเล็กน้อย แสงธรรมชาติ',
     'style': 'Authentic user-generated content style, handheld phone camera with natural micro-shake, natural indoor daylight, '
              'casual home setting, selfie-review framing, unpolished and believable, vertical social video look.'},
    {'id': 'unbox', 'name': 'แกะกล่องบนโต๊ะ', 'icon': '🎁',
     'desc': 'มุมมองจากด้านบน มือหยิบสินค้าออกจากกล่อง',
     'style': 'Top-down overhead flat-lay unboxing, hands entering frame to lift the product out of its box, '
              'warm wooden table surface, soft daylight from the side, satisfying tactile close-ups.'},
    {'id': 'lifestyle', 'name': 'ไลฟ์สไตล์ใช้งานจริง', 'icon': '🏠',
     'desc': 'เห็นสินค้าถูกใช้งานในชีวิตประจำวัน',
     'style': 'Lifestyle scene showing the product in everyday real use, natural window light, cozy modern home interior, '
              'gentle handheld movement following the action, warm inviting color grade.'},
    {'id': 'before_after', 'name': 'ก่อน–หลัง เปรียบเทียบ', 'icon': '🔄',
     'desc': 'ตัดสลับก่อนใช้กับหลังใช้ให้เห็นผลชัด',
     'style': 'Split before-and-after comparison, identical framing and lighting on both sides, clean match cut between states, '
              'clear visual contrast that makes the improvement obvious.'},
    {'id': 'dynamic_ads', 'name': 'โฆษณาจังหวะเร็ว', 'icon': '⚡',
     'desc': 'ตัดเร็ว ซูมกระชาก สีจัด เหมาะกับ TikTok',
     'style': 'High-energy advertising cut, fast punchy zooms and whip pans, bold saturated color grade, dramatic lighting, '
              'quick rhythmic beat-matched motion, attention-grabbing opening frame.'},
]
TEMPLATE_IDS = {t['id'] for t in TEMPLATES}
_BY_ID = {t['id']: t for t in TEMPLATES}


def build_prompt(template_id: str, *, product_title: str, script_text: str = '',
                 has_avatar: bool = False, seconds: int = 10) -> str:
    """Compose the final prompt we send to Gemini: style + product + spoken script."""
    t = _BY_ID.get(template_id) or _BY_ID['studio_product']
    seconds = 20 if int(seconds) >= 20 else 10
    lines = [f'Create a {seconds}-second vertical short-form product video.',
             f'Visual style: {t["style"]}']
    if product_title:
        lines.append(f'Product featured: {product_title.strip()[:180]}')
    if has_avatar:
        lines.append('Use the attached photo as the on-camera presenter; keep their face and outfit consistent '
                     'throughout the whole video, and have them present the product to camera.')
    if script_text:
        lines.append('Thai voice-over narration, natural friendly Thai speaking voice, spoken exactly as written: '
                     f'"{script_text.strip()[:1200]}"')
        lines.append('Burn matching Thai subtitles at the lower third, large readable text with a subtle shadow.')
    lines.append('No on-screen logos, watermarks or brand names other than the product itself.')
    return '\n'.join(lines)
