"""User-supplied Shopee Affiliate import; NEVER logs in or scrapes Shopee.

Only preview the text or CSV voluntarily provided by the user. The original
session, cookies, password and OTP are neither requested nor processed.
"""
from __future__ import annotations
import csv
import io
import re
from urllib.parse import urlsplit

MAX_ROWS = 100
ALLOWED_SHOPEE_HOSTS = {'shopee.co.th', 'www.shopee.co.th', 's.shopee.co.th'}


def allowed_link(raw: str) -> str:
    try:
        raw = raw.strip().rstrip('),.;]}>')
        parsed = urlsplit(raw)
        if (parsed.scheme != 'https' or (parsed.hostname or '').lower() not in ALLOWED_SHOPEE_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            return ''
        if len(raw) > 1000 or any(x.isspace() for x in raw):
            return ''
        return raw
    except ValueError:
        return ''


def rate_hint(raw: str):
    # A hint from user-pasted text is NOT proof of affiliate rate.
    m = re.search(r'(?:extra\s*comm(?:ission)?|ค่าคอม(?:มิชชั่น)?พิเศษ)\s*[:：=]?\s*(\d{1,3}(?:\.\d{1,2})?)\s*%', raw, re.I)
    if not m:
        return None
    value = float(m.group(1))
    return value if 0 <= value <= 100 else None


def pasted_preview(content: str):
    if len(content) > 12000:
        raise ValueError('ข้อความยาวเกิน 12,000 ตัวอักษร')
    content = content.strip()
    if not content:
        raise ValueError('กรุณาวางข้อมูลสินค้าก่อน')
    urls = re.findall(r'https?://[^\s<>"\'\u200b]+', content, re.I)
    url = next((s for u in urls if (s := allowed_link(u))), '')
    if urls and not url:
        raise ValueError('ลิงก์ไม่ใช่โดเมน Shopee ประเทศไทยที่อนุญาต')
    lines = [re.sub(r'\s+', ' ', x.strip()) for x in content.splitlines() if x.strip()]
    title = next((line[:200] for line in lines if len(line)>2 and not line.startswith(('http:', 'https:'))
            and not re.match(r'^(?:ราคา|฿|extra\s*comm|ค่าคอม|ลิงก์|ยอดขาย|จำนวนขาย|รีวิว|ร้านค้า|\d+[.,]?\d*\s*%)', line, re.I)), '')
    if title:
        # Strip pasted URLs and price fragments that share the title line.
        title = re.sub(r'https?://\S+', '', title)
        title = re.sub(r'(?:ราคา\s*[:：]?\s*)?฿\s*[\d,]+(?:\.\d{1,2})?', '', title)
        title = re.sub(r'\s+', ' ', title).strip(' -|·,') or ''
    if not title and url:
        title = 'สินค้า Shopee — กรุณาแก้ชื่อหลังนำเข้า'
    if not title:
        raise ValueError('กรุณาวางชื่อสินค้าอย่างน้อยหนึ่งบรรทัด พร้อมลิงก์ Shopee (ถ้ามี)')
    price = None
    p = re.search(r'(?:ราคา\s*[:：]?\s*฿?|฿)\s*([\d,]+(?:\.\d{1,2})?)', content)
    if p:
        try: price = float(p.group(1).replace(',',''))
        except ValueError: pass
    return {'items': [dict(title=title, url=url, platform='shopee', price=price,
             extra_comm_rate_hint=rate_hint(content),source='ข้อความที่สมาชิกคัดลอก',
             verification='unverified', orders=None, commission_baht=None)],
            'note':'เป็นข้อมูลที่สมาชิกคัดลอกจาก Shopee เอง ไม่ใช่การเชื่อม/ยืนยันผ่าน Shopee API'}


def normalize(h):
    return re.sub(r'[\s_\-\(\)\[\]฿%]+', '', str(h).lower().strip())


def first_value(row, headers):
    for key in headers:
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''


def report_preview(binary: bytes, filename: str):
    if len(binary) > 2*1024*1024:
        raise ValueError('ไฟล์เกิน 2 MB')
    if not filename.lower().endswith(('.csv','.txt')):
        raise ValueError('รองรับไฟล์ .csv หรือ .txt เท่านั้น')
    if b'\x00' in binary[:64] and not binary.startswith((b'\xff\xfe',b'\xfe\xff')):
        raise ValueError('ไฟล์ไม่ใช่ CSV ข้อความ')
    text = None
    for encoding in ('utf-8-sig','utf-16','cp874'):
        try:
            text=binary.decode(encoding)
            if '\x00' in text[:80]:continue
            break
        except (UnicodeDecodeError, UnicodeError): pass
    if text is None:
        raise ValueError('อ่านรหัสอักษรของไฟล์ CSV ไม่ได้')
    try: dialect=csv.Sniffer().sniff(text[:4000], delimiters=',;\t')
    except csv.Error: dialect='excel'
    reader=csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError('ไฟล์ไม่มีหัวคอลัมน์')
    fields={normalize(f):f for f in reader.fieldnames if f}
    def get_headers(names):return [fields[x] for x in names if x in fields]
    product_columns=get_headers(['ชื่อสินค้า','ชื่อสินค้าที่สั่งซื้อ','ชื่อผลิตภัณฑ์','ชื่อรายการสินค้า','ชื่อสินค้าที่ขาย','productname','itemname','producttitle','itemtitle'])
    link_columns=get_headers(['ลิงก์สินค้า','ลิงค์สินค้า','linkสินค้า','producturl','productlink','itemlink','affiliatelink','ลิงก์affiliate'])
    price_columns=get_headers(['ราคาสินค้า','price','productprice','itemprice'])
    order_columns=get_headers(['จำนวนออเดอร์','จำนวนคำสั่งซื้อ','orders','ordercount','จำนวนออเดอร์ที่เกิดขึ้น'])
    comm_columns=get_headers(['ค่าคอมมิชชั่น','ค่าคอมมิชชัน','ยอดคอมมิชชั่น','commission','commissionamount','commissionbaht'])
    if not product_columns:
        raise ValueError('ไม่พบคอลัมน์ชื่อสินค้าในรายงาน กรุณาใช้ CSV ที่มีชื่อสินค้า (ไม่ใช่รายงานยอดรวมอย่างเดียว)')
    items=[]
    for row in reader:
        if len(items)>=MAX_ROWS:break
        title=first_value(row,product_columns)[:200]
        if not title or title.lower() in ('total','รวม'):continue
        url=allowed_link(first_value(row,link_columns))
        def numeric(keys):
            x=first_value(row,keys).replace(',','').replace('฿','').strip()
            try: return float(x) if x else None
            except ValueError:return None
        items.append(dict(title=title,url=url,platform='shopee',price=numeric(price_columns),
                          orders=numeric(order_columns),commission_baht=numeric(comm_columns),
                          extra_comm_rate_hint=None, source='ไฟล์รายงานที่สมาชิกส่งออก',verification='unverified'))
    return {'items':items,'note':'อ่านได้เฉพาะคอลัมน์ที่มีจริงในไฟล์ สินค้าและค่าคอมยังไม่ได้ยืนยันผ่าน API ของ Shopee',
            'total_preview':len(items),'columns':list(reader.fieldnames)[:30]}
