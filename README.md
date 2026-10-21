# Affiliate Auto Studio

ระบบช่วยนักทำ Affiliate ไทย: **ดึงสินค้าจาก Shopee → สร้างบทรีวิวแบบ UGC → ทำคลิปแนวตั้ง 9:16 → เชื่อม Facebook / Instagram / LINE OA → ตั้งเวลาโพสต์อัตโนมัติ** ในหน้าเดียว

> สถานะ: **Beta — Phase 1 (MVP)** ระบบอยู่ระหว่างพัฒนา บางฟีเจอร์ต้องตั้งค่าหรือรออนุมัติจากแพลตฟอร์มก่อนใช้งานจริง

| | URL |
|---|---|
| เว็บแอป (Netlify) | https://affiliate-auto-studio.netlify.app |
| Backend API (Railway) | https://backend-production-e1a6.up.railway.app/health |

---

## ฟีเจอร์ใน Phase 1 (MVP)

| ฟีเจอร์ | สถานะ | หมายเหตุ |
|---|---|---|
| โหมด Demo — ใช้ได้ทุกฟีเจอร์โดยไม่ต้องสมัคร | ✅ ใช้ได้ | บัญชีทดลองแยกต่อเบราว์เซอร์ เก็บ 7 วัน สมัครทีหลังงานย้ายตามไปด้วย |
| สร้างบท UGC 6 สไตล์ + คลิปพรีวิว 9:16 (ดาวน์โหลด mp4/webm) | ✅ ใช้ได้ | เรนเดอร์ในเบราว์เซอร์ ไม่ใช้เครดิต |
| สินค้าของฉัน — เพิ่มเอง พร้อมรูป ราคา ค่าคอม | ✅ ใช้ได้ | |
| ดึงสินค้าจาก Shopee (รูป ราคา ค่าคอมจริง + ลิงก์ Affiliate) | ⚙️ ต้องตั้งค่า | ใส่ AppID / Secret ของ Shopee Affiliate Open API ของผู้ใช้เอง |
| เชื่อม Facebook Page / Instagram / LINE OA | ⚙️ ต้องตั้งค่า | ผู้ดูแลต้องตั้ง Meta App ก่อน (ดูหัวข้อ “ตั้งค่า Meta”) |
| Auto-Post ตั้งเวลา (FB / IG Reels / LINE) | ⚙️ ต้องตั้งค่า | ใช้ Facebook native scheduling เมื่อเวลาห่าง 15 นาที–29 วัน |
| คลิป AI จริง (google/veo-3.1-lite ผ่าน OpenRouter) | ⚙️ ต้องตั้งค่า | ตัดเครดิตก่อนสร้าง คืนเครดิตอัตโนมัติถ้าล้มเหลว |
| เติมเครดิตผ่าน PromptPay | 🧪 โหมดจำลอง | เลือกแพ็กเกจ → QR → ชำระ → เครดิตเข้าจริง (ดู “ระบบชำระเงิน”) |
| บัญชีสมาชิก — โปรไฟล์ เปลี่ยนรหัสผ่าน ประวัติเติมเครดิต | ✅ ใช้ได้ | เมนูโปรไฟล์มุมขวาบน |
| ศูนย์ช่วยเหลือ (FAQ) + Onboarding ครั้งแรก | ✅ ใช้ได้ | |
| โพสต์ TikTok / Shopee Video อัตโนมัติ | ❌ ยังไม่รองรับ | ดาวน์โหลดคลิปไปโพสต์เอง แล้วติดตามในคิวโพสต์ |

ฟีเจอร์ที่พักไว้ใน MVP (โค้ดยังอยู่ ซ่อนจากเมนู): เรดาร์สินค้ามาแรง, โรงงานบทรีวิวแบบเก่า, ปฏิทินคอนเทนต์, ห้องทดลองชุมชน, หน้าสนับสนุน, ศูนย์อัปเดต — เปิดกลับได้ที่ `MVP_HIDDEN_TABS` ใน `static/app.js`

---

## สถาปัตยกรรม

```
Browser ──► Netlify (static: public/)
              │  _redirects proxy: /api/*, /media/*, /ws/*, /health
              ▼
           Railway (Docker) ──► FastAPI  community_app.py
                                  ├─ features_v8.py   connectors FB/IG/LINE, Shopee, help, support
                                  ├─ studio_v8.py     UGC script, preview/AI clip, credits ledger
                                  ├─ scheduler_v8.py  scheduled posts + worker
                                  ├─ payments_v8.py   PromptPay top-up
                                  └─ SQLite (WAL) + media  →  Railway volume /app/data
```

| ส่วน | เทคโนโลยี |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, SQLite (WAL), argon2, Fernet (เข้ารหัส token/secret) |
| Frontend | HTML + Vanilla JS (`static/app.js`, `static/v8.js`), CSS (`static/v8.css`) |
| Integrations | Meta Graph API v25.0, LINE Messaging API, Shopee Affiliate Open API (TH), OpenRouter |
| QR | `segno` (สร้าง SVG), PromptPay EMVCo payload + CRC16-CCITT |
| Tests | pytest (`tests_v8/`, `tests_beta/`), Playwright สำหรับ E2E |

---

## รันบนเครื่อง (Local)

```bash
git clone https://github.com/therw101/affiliate-auto-studio.git
cd affiliate-auto-studio
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn community_app:app --port 8010
# เปิด http://localhost:8010
```

โหมดทดสอบครบวงจรกับผู้ให้บริการจำลอง (Meta / IG / LINE / Shopee):

```bash
bash dev_tools/run_e2e.sh      # mock providers :9100 + app :8010
```

รันเทสต์:

```bash
python -m pytest -q tests_v8 tests_beta
```

---

## ตัวแปรสภาพแวดล้อม (Environment)

| ตัวแปร | จำเป็น | ค่าเริ่มต้น | ความหมาย |
|---|---|---|---|
| `PUBLIC_DEPLOYMENT` | production | `0` | `1` = โหมดใช้งานจริง (cookie secure, ปิด prototype V6) |
| `APP_MASTER_KEY` | production | – | Fernet key สำหรับเข้ารหัส token/secret — **ห้ามหาย** ไม่งั้นถอดรหัสข้อมูลเดิมไม่ได้ |
| `COOKIE_SECURE` | production | `0` | `1` เมื่อใช้ HTTPS |
| `PUBLIC_BASE_URL` | production | – | URL หน้าเว็บ ใช้สร้าง OAuth redirect เช่น `https://affiliate-auto-studio.netlify.app` |
| `COMMUNITY_DATA_DIR` | – | `./data` | ที่เก็บฐานข้อมูลและไฟล์ (บน Railway คือ volume `/app/data`) |
| `MAX_BETA_USERS` | – | `100` | จำนวนที่นั่งสมาชิก (ไม่นับบัญชี Demo) |
| `BETA_INVITE_CODE` | – | ว่าง | ถ้าตั้งไว้ การสมัครต้องใช้รหัสเชิญ ถ้าว่าง = สมัครได้เลย |
| `DEMO_CREDITS` / `DEMO_TTL_DAYS` / `DEMO_PER_IP_HOUR` | – | `50` / `7` / `30` | เครดิตเริ่มต้น อายุ และ rate limit ของบัญชี Demo |
| `PAYMENT_MODE` | – | `simulate` | `simulate` = จำลองการจ่าย, `manual` = รับเงินจริงผ่าน PromptPay |
| `PROMPTPAY_ID` / `PROMPTPAY_NAME` | manual | – | เบอร์ 10 หลัก / เลขบัตร 13 หลัก / e-Wallet 15 หลัก และชื่อผู้รับ |
| `META_APP_ID` / `META_APP_SECRET` | FB/IG | – | ตั้งได้ที่นี่หรือในหน้า “เชื่อมต่อช่องทาง” (ผู้ดูแล) |
| `PLATFORM_OPENROUTER_API_KEY` | AI clip | – | เปิดคลิป AI จริงด้วยคีย์ของแพลตฟอร์ม |
| `STUDIO_CLIP_CREDITS` | – | `10` | เครดิตต่อคลิป AI |
| `SCHEDULER_WORKER` / `SCHEDULER_INTERVAL` / `SCHEDULER_SECRET` | – | `1` / `20` / – | worker โพสต์ตามเวลา และ secret สำหรับ `POST /api/scheduler/tick` |
| `VIDEO_MOCK` | – | `0` | `1` = จำลองคลิป AI ไม่เรียก API จริง |

ดูตัวอย่างเพิ่มเติมใน `.env.server.example` — **ห้าม commit ไฟล์ `.env` จริง**

---

## Deploy

### Backend → Railway

```bash
railway login
railway up --service backend --detach
railway variable set PUBLIC_DEPLOYMENT=1 COOKIE_SECURE=1 APP_MASTER_KEY=... PUBLIC_BASE_URL=https://affiliate-auto-studio.netlify.app --service backend
```

ต้องมี volume mount ที่ `/app/data` และตั้ง `RAILWAY_RUN_UID=0` (volume เป็นของ root) — healthcheck: `/health`

### Frontend → Netlify

```bash
API_ORIGIN=https://backend-production-e1a6.up.railway.app python3 build_public.py
netlify deploy --prod --dir=public --no-build
```

`build_public.py` สร้างโฟลเดอร์ `public/` พร้อมไฟล์ `_redirects` ที่ proxy `/api/*`, `/media/*`, `/ws/*`, `/health` ไปยัง backend ทำให้ cookie เป็น same-origin

### ตั้งค่า Meta (Facebook / Instagram)

1. สร้างแอปที่ https://developers.facebook.com → เพิ่ม Facebook Login
2. Valid OAuth Redirect URI: `https://affiliate-auto-studio.netlify.app/api/oauth/facebook/callback`
3. ตั้ง `META_APP_ID` / `META_APP_SECRET` แล้วผู้ใช้กด “เชื่อมต่อ Facebook” ได้เลย

---

## ระบบชำระเงิน (PromptPay)

แพ็กเกจกำหนดใน `payments_v8.py` (`PACKAGES`):

| แพ็กเกจ | ราคา | เครดิต |
|---|---|---|
| Starter | ฿99 | 100 |
| Creator | ฿299 | 350 |
| Pro | ฿699 | 900 |
| Business | ฿1,490 | 2,100 |

| โหมด | การทำงาน |
|---|---|
| `simulate` (ค่าเริ่มต้น) | QR จำลอง (สแกนจ่ายจริงไม่ได้) → ปุ่ม “จำลองการชำระเงินสำเร็จ” → เครดิตเข้าบัญชีจริงในฐานข้อมูล |
| `manual` | QR PromptPay จริงไปที่ `PROMPTPAY_ID` ยอดมีเศษสตางค์ไม่ซ้ำเพื่อจับคู่รายการ → ผู้ดูแลยืนยันที่ `POST /api/admin/payments/{id}/confirm` |

ทุกรายการเติมเครดิตบันทึกใน `credit_ledger` และเพิ่มเครดิตได้ครั้งเดียวต่อคำสั่งซื้อ (idempotent) คำสั่งซื้อหมดอายุใน 15 นาที

---

## API หลัก

| กลุ่ม | Endpoint |
|---|---|
| บัญชี | `POST /api/demo/start`, `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/me`, `POST /api/my/password` |
| สตูดิโอ | `GET /api/studio/bootstrap`, `POST /api/studio/projects`, `POST /api/studio/projects/{id}/preview`, `POST /api/studio/projects/{id}/ai-clip` |
| สินค้า | `POST /api/my/products/manual`, `GET /api/shopee/search`, `POST /api/shopee/import` |
| เชื่อมต่อ | `GET /api/connectors`, `GET /api/connectors/facebook/start`, `POST /api/connectors/line` |
| โพสต์ | `POST /api/scheduled-posts`, `GET /api/scheduled-posts`, `POST /api/products/{id}/publish` |
| ชำระเงิน | `GET /api/payments/packages`, `POST /api/payments/orders`, `GET /api/payments/orders/{id}`, `POST /api/payments/orders/{id}/simulate-paid` |
| ช่วยเหลือ | `GET /api/help/articles` |

---

## โครงสร้างโปรเจกต์

```
community_app.py        แอปหลัก: auth, session, products, demo mode, admin
features_v8.py          connectors (FB/IG/LINE), Shopee, help, support
studio_v8.py            สตูดิโอ UGC + เครดิต
scheduler_v8.py         ตั้งเวลาโพสต์ + worker
payments_v8.py          PromptPay top-up
integrations/           meta.py, line_oa.py, shopee_affiliate.py, ugc.py, help_content.py
static/                 index.html (dashboard), app.js, v8.js, v8.css, landing.html, ...
tests_v8/, tests_beta/  pytest
dev_tools/              mock providers + สคริปต์ E2E
build_public.py         สร้าง public/ สำหรับ Netlify
Dockerfile              image สำหรับ Railway
```

---

## Backup & Restore

| สิ่งที่สำรอง | วิธี |
|---|---|
| โค้ดก่อนตัดเหลือ MVP | tag `backup-pre-mvp-20261021-0935` / branch `backup/pre-mvp-20261021-0935` |
| ฐานข้อมูล | `data/community.db` (+ `-wal`) และ `data/media/` — สำรองพร้อม `data/community.key` หรือ `APP_MASTER_KEY` เสมอ |
| หน้าเว็บ | Netlify → Deploys → เลือกเวอร์ชันก่อนหน้า → Publish deploy |

กู้คืนโค้ดเวอร์ชันเต็ม: `git checkout backup-pre-mvp-20261021-0935`

---

## ความปลอดภัย

Session cookie แบบ HttpOnly + SameSite=Strict, CSRF token ทุกคำขอที่เปลี่ยนข้อมูล, รหัสผ่านแบบ argon2, token ของแพลตฟอร์มเข้ารหัสด้วย Fernet, จำกัดการพยายาม login ผิด, rate limit การสร้างบัญชี Demo และคำสั่งซื้อ, เครดิตเพิ่มได้เฉพาะจากคำสั่งซื้อที่ชำระแล้ว

---

## เอกสารเพิ่มเติม

`README_V8_TH.md` (รายละเอียด V8: connectors / studio / scheduler), `CHANGELOG.md`, `DESIGN.md`
