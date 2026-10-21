"""Copy rules for generated affiliate content — what may be said, and how it must be written.

The rules follow the approach of Kevin's Gem Studio prompt set
(https://prompt-ai-affiliate.vercel.app/): choose one angle rather than listing every
selling point, keep every claim checkable against data we actually hold, ban the hype
vocabulary, and spell spoken text out so a voice model reads Thai correctly.

The last one matters more than it looks. A voice model handed "฿1,290" or "2000mAh"
reads it wrong or in English; handed "หนึ่งพันสองร้อยเก้าสิบบาท" it reads it right.
So every voice-over line passes through `speakable()` before it reaches a video prompt.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------- claims
# Hype that is either unverifiable or, for health and cosmetics, outright illegal to
# claim in Thai advertising. Generated copy is scrubbed of these rather than trusted.
BANNED = [
    'ดีที่สุด', 'ดีที่สุดในโลก', 'อันดับ 1', 'อันดับหนึ่ง', 'เบอร์ 1', 'เบอร์หนึ่ง',
    'หายทันที', 'หายขาด', 'รักษาโรค', 'รักษาได้', 'ปลอดภัย 100%', 'ได้ผล 100%',
    'รับประกัน 100%', 'การันตีผล', 'ถูกที่สุด', 'ไม่มีผลข้างเคียง', 'ขาวใสใน 7 วัน',
    'ผอมเร็ว', 'ลดน้ำหนักได้จริง', 'ปราศจากสารเคมี 100%',
]
BANNED_HINT = 'ใช้คำที่ตรวจสอบได้แทน เช่น บอกสิ่งที่สินค้าทำได้จริง หรืออ้างเรตติ้ง/ยอดขายที่มีข้อมูลจริง'

# --------------------------------------------------------------------- angles
# One clip argues one thing. Three candidate angles, pick one — never all of them.
ANGLES = [
    {'id': 'problem', 'label': 'ปัญหาที่คนดูเจอ', 'brief': 'เปิดด้วยปัญหาที่กลุ่มเป้าหมายเจอจริง แล้วให้สินค้าเป็นทางออก'},
    {'id': 'benefit', 'label': 'ข้อดีที่ตรวจสอบได้', 'brief': 'ชูจุดเด่น 1 ข้อที่พิสูจน์ได้จากข้อมูลสินค้า ไม่เดา ไม่แต่ง'},
    {'id': 'question', 'label': 'คำถามที่คลิปตอบ', 'brief': 'เปิดด้วยคำถามที่คนดูสงสัย แล้วตอบให้จบในคลิป'},
]
ANGLE_IDS = {a['id'] for a in ANGLES}

# On-screen headline: either a 3–4 word punch, or one spoken POV line.
HEADLINE_MODES = [
    {'id': 'short', 'label': 'สั้น 3–4 คำ', 'brief': 'คำไทยล้วน 3–4 คำ อ่านจบในวินาทีเดียว'},
    {'id': 'pov', 'label': 'POV บทพูด', 'brief': 'หนึ่งประโยคคุยกับคนดู ขึ้นต้นด้วยอิโมจิผู้พูดและโคลอน เช่น "👩: ..." ไม่เกิน 80 ตัวอักษร'},
]
HEADLINE_MAX = 80
CAPTION_MAX = 80
HASHTAG_COUNT = 5

# Where the headline sits in a 9:16 frame — clear of the product and of the app's own UI.
PLACEMENT = {'position': 'top-center', 'x_pct': 50, 'y_pct': 16, 'max_width_pct': 80,
             'aspect': '9:16', 'align': 'center',
             'avoid': 'ใบหน้า ตัวสินค้า และแถบ UI ของแพลตฟอร์ม (บนสุด ~8% และล่างสุด ~20%)'}

# ------------------------------------------------------------- Thai number reading
_DIGITS = ['ศูนย์', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
_POS = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']


def thai_number(n: int) -> str:
    """Read an integer the way Thai is spoken: ๒๑ is ยี่สิบเอ็ด, not สองสิบหนึ่ง."""
    if n < 0:
        return 'ลบ' + thai_number(-n)
    if n == 0:
        return _DIGITS[0]
    if n >= 1_000_000:
        head, rest = divmod(n, 1_000_000)
        return thai_number(head) + 'ล้าน' + (thai_number(rest) if rest else '')
    out = ''
    s = str(n)
    length = len(s)
    for i, ch in enumerate(s):
        d = int(ch)
        pos = length - i - 1
        if d == 0:
            continue
        if pos == 0 and d == 1 and length > 1:
            out += 'เอ็ด'
        elif pos == 1 and d == 1:
            out += 'สิบ'
        elif pos == 1 and d == 2:
            out += 'ยี่สิบ'
        else:
            out += _DIGITS[d] + _POS[pos]
    return out


def thai_decimal(value: float) -> str:
    whole = int(abs(value))
    frac = round(abs(value) - whole, 2)
    out = ('ลบ' if value < 0 else '') + thai_number(whole)
    if frac > 0:
        digits = f'{frac:.2f}'.split('.')[1].rstrip('0')
        out += 'จุด' + ''.join(_DIGITS[int(d)] for d in digits)
    return out


# Units and loan words a Thai voice model otherwise reads in English or spells out.
# Longest first: 'mAh' must win over 'm', 'kg' over 'g'. No leading \b — in "2000mAh"
# there is no boundary between the digit and the unit.
UNITS = [
    ('mAh', 'มิลลิแอมป์ชั่วโมง'), ('inches', 'นิ้ว'), ('inch', 'นิ้ว'),
    ('kg', 'กิโลกรัม'), ('gb', 'กิกะไบต์'), ('tb', 'เทระไบต์'), ('hz', 'เฮิรตซ์'),
    ('ml', 'มิลลิลิตร'), ('mm', 'มิลลิเมตร'), ('cm', 'เซนติเมตร'),
    ('g', 'กรัม'), ('l', 'ลิตร'), ('m', 'เมตร'), ('w', 'วัตต์'), ('v', 'โวลต์'),
]
LOANWORDS = [
    (r'(?i)\bUSB[- ]?C\b', 'ยูเอสบีซี'), (r'(?i)\bUSB\b', 'ยูเอสบี'), (r'(?i)\bType[- ]?C\b', 'ไทป์ซี'),
    (r'(?i)\bBluetooth\b', 'บลูทูธ'), (r'(?i)\bWi[- ]?Fi\b', 'ไวไฟ'), (r'(?i)\bLED\b', 'แอลอีดี'),
    (r'(?i)\bOLED\b', 'โอแอลอีดี'), (r'(?i)\bHD\b', 'เอชดี'), (r'(?i)\bIP\s?(\d{2})\b', r'ไอพี \1'),
    (r'(?i)\bPro\b', 'โปร'), (r'(?i)\bMax\b', 'แม็กซ์'), (r'(?i)\bMini\b', 'มินิ'),
    (r'(?i)\bSet\b', 'เซ็ต'), (r'(?i)\bPack\b', 'แพ็ก'), (r'(?i)\bFree\b', 'ฟรี'),
    (r'(?i)\bOK\b', 'โอเค'), (r'(?i)\bShopee\b', 'ช้อปปี้'), (r'(?i)\bTikTok\b', 'ติ๊กต็อก'),
    (r'(?i)\bLazada\b', 'ลาซาด้า'), (r'(?i)\bLive\b', 'ไลฟ์'), (r'(?i)\bReview\b', 'รีวิว'),
]


def speakable(text: str) -> str:
    """Rewrite a line so a Thai voice model reads it out loud correctly.

    Numbers, currency, percentages, units and common English words become Thai words.
    Everything else is left alone — this is a reading aid, not a translator.
    """
    if not text:
        return ''
    out = str(text)
    # currency first: the symbol binds tighter than the bare number
    out = re.sub(r'฿\s*([\d,]+(?:\.\d+)?)',
                 lambda m: thai_decimal(float(m.group(1).replace(',', ''))) + 'บาท', out)
    out = re.sub(r'([\d,]+(?:\.\d+)?)\s*บาท',
                 lambda m: thai_decimal(float(m.group(1).replace(',', ''))) + 'บาท', out)
    out = re.sub(r'([\d,]+(?:\.\d+)?)\s*%',
                 lambda m: thai_decimal(float(m.group(1).replace(',', ''))) + 'เปอร์เซ็นต์', out)
    # ratings read as "x เต็ม y", and the left side may be a decimal (4.8/5)
    out = re.sub(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)',
                 lambda m: f'{thai_decimal(float(m.group(1)))}เต็ม{thai_decimal(float(m.group(2)))}', out)
    for unit, rep in UNITS:
        out = re.sub(r'([\d,]+(?:\.\d+)?)\s*' + unit + r'\b',
                     lambda m, r=rep: thai_decimal(float(m.group(1).replace(',', ''))) + r, out, flags=re.I)
    out = re.sub(r'(?<=[\d\u0E00-\u0E7F])"', ' นิ้ว ', out)
    for pat, rep in LOANWORDS:
        out = re.sub(pat, rep, out)
    # any number still standing reads as a Thai number
    out = re.sub(r'(?<![฀-๿])([\d,]+(?:\.\d+)?)(?![฀-๿])',
                 lambda m: thai_decimal(float(m.group(1).replace(',', ''))), out)
    return re.sub(r'\s{2,}', ' ', out).strip()


# --------------------------------------------------------------------- checks
def banned_in(text: str) -> list[str]:
    low = (text or '').lower()
    return [w for w in BANNED if w.lower() in low]


def scrub(text: str) -> str:
    """Remove banned hype from a line without mangling the rest of the sentence."""
    out = text or ''
    for w in BANNED:
        out = re.sub(re.escape(w), '', out, flags=re.I)
    return re.sub(r'\s{2,}', ' ', out).strip(' ·-—,')


def hashtags(title: str, extra: list[str] | None = None, n: int = HASHTAG_COUNT) -> list[str]:
    """Exactly n hashtags, none repeated — the reference set's rule, kept literally."""
    seen, out = set(), []
    def add(tag):
        t = '#' + re.sub(r'[^\w฀-๿]', '', str(tag).lstrip('#'))
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    for w in (extra or []):
        add(w)
    for w in re.split(r'[\s/|,()\[\]\-]+', title or ''):
        if 2 <= len(w) <= 18:
            add(w)
    for w in ('รีวิว', 'ของดีบอกต่อ', 'ShopeeAffiliate', 'TikTokShop', 'ป้ายยา', 'ของใช้ในบ้าน'):
        add(w)
    return out[:n]


def check(script: dict, product: dict) -> list[str]:
    """Problems a human should see before this script becomes a video.

    Only reports what is checkable: banned wording, a price that contradicts the
    product record, and over-long on-screen text.
    """
    issues = []
    blob = ' '.join(str(s.get(k, '')) for s in script.get('scenes', []) for k in ('text', 'voice'))
    blob += ' ' + str(script.get('caption', ''))
    for w in sorted(set(banned_in(blob))):
        issues.append(f'ใช้คำที่อ้างเกินจริง: "{w}" — {BANNED_HINT}')
    price = product.get('price')
    for m in re.finditer(r'฿\s*([\d,]+(?:\.\d+)?)', blob):
        said = float(m.group(1).replace(',', ''))
        if price and abs(said - float(price)) > 0.5:
            issues.append(f'บทพูดถึงราคา ฿{said:,.0f} แต่ข้อมูลสินค้าคือ ฿{float(price):,.0f} — แก้ให้ตรงกันก่อนโพสต์')
            break
    for s in script.get('scenes', []):
        if len(str(s.get('text', ''))) > HEADLINE_MAX:
            issues.append(f'ข้อความบนจอยาวเกิน {HEADLINE_MAX} ตัวอักษร: "{str(s["text"])[:40]}…"')
            break
    if len(str(script.get('caption', ''))) > 300:
        issues.append('แคปชั่นยาวเกินไป ตัดให้สั้นลงจะอ่านจบก่อนเลื่อนผ่าน')
    return issues


def voice_track(script: dict) -> list[str]:
    """Every voice-over line, rewritten the way it should be read aloud."""
    return [speakable(s.get('voice', '')) for s in script.get('scenes', []) if s.get('voice')]
