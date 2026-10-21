# Affiliate Auto Studio V8 — Phase 1 (Studio · Connectors · Shopee · Help)

## สิ่งที่เพิ่มใน V8

| ฟีเจอร์ | เมนู | สถานะ |
|---|---|---|
| สตูดิโอ 4 ขั้นตอน: สินค้า → บท UGC (6 สไตล์) → คลิปพรีวิว 9:16 → บันทึก/ดาวน์โหลด/คิว TikTok | สร้างคอนเทนต์ (เริ่มที่นี่) | ใช้ได้ทันที ไม่ต้องตั้งค่า (มีสินค้า+บทตัวอย่างให้) |
| คลิป AI เอนจินเดียว: Google Veo 3.1 Lite ผ่าน OpenRouter แสดงเครดิตก่อนสร้าง หักตอนส่ง คืนอัตโนมัติเมื่อล้มเหลว | สร้างคอนเทนต์ → ขั้นตอน 3B | ต้องมี `PLATFORM_OPENROUTER_API_KEY` หรือคีย์ OpenRouter ของสมาชิก |
| ดึงสินค้า Shopee จริง (รูป ราคา ค่าคอม Seller/Shopee ยอดขาย เรตติ้ง ลิงก์ Affiliate) ผ่าน Shopee Affiliate Open API | สินค้าของฉัน | สมาชิกใส่ AppID/Secret ของตัวเอง |
| Connectors จริง: Facebook Pages (OAuth), Instagram (ผ่านเพจหรือ Instagram Login), LINE OA (Messaging API + Webhook) | Connectors | แอดมินตั้ง Meta App ครั้งเดียว |
| โพสต์สินค้า (รูป+แคปชั่น+ลิงก์) ไปเพจ/IG/LINE พร้อมผลแยกช่องทาง | สินค้าของฉัน → 📤 | หลังเชื่อม Connectors |
| **Auto-Post ตั้งเวลา** Facebook (วิดีโอ/รูป), Instagram (Reels/รูป), LINE OA — Facebook ที่ตั้งล่วงหน้า ≥15 นาทีฝากคิวที่ Facebook โดยตรง ที่เหลือโพสต์ด้วย worker ทุก 20 วินาที | สร้างคอนเทนต์ → ⏰ Auto-Post | หลังกด Connect with Facebook |
| ศูนย์ช่วยเหลือ 22 บทความ + แชทสด Realtime (WebSocket, fallback polling) + บอทตอบอัตโนมัติเมื่อแอดมินไม่ออนไลน์ | ช่วยเหลือ & สอนใช้งาน / ปุ่ม 💬 | ใช้ได้ทันที |

TikTok ยังเป็น **โพสต์เอง** (ดาวน์โหลดคลิป + คัดลอกแคปชั่น) จนกว่าจะได้สิทธิ์ Content Posting API — UI แสดง "ยังไม่เชื่อมต่อ" ชัดเจนทุกจุด

## ENV ที่ใช้

| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `PUBLIC_BASE_URL` | โดเมน https ที่ผู้ใช้เปิด เช่น `https://studio.example.com` (ใช้สร้าง Redirect URI + Webhook) |
| `META_APP_ID` / `META_APP_SECRET` | Facebook Login for Business (หรือใส่ในหน้า Connectors → ตั้งค่าแอป Admin) |
| `IG_APP_ID` / `IG_APP_SECRET` | Instagram API with Instagram Login (ไม่บังคับ — เชื่อม IG ผ่านเพจได้) |
| `META_GRAPH_VERSION` | ค่าเริ่ม `v25.0` |
| `PLATFORM_OPENROUTER_API_KEY` | เปิดคลิป AI แบบใช้เครดิตระบบ |
| `STUDIO_CLIP_CREDITS` | เครดิตต่อคลิป AI (ค่าเริ่ม 10) |
| `VIDEO_MOCK=1` | โหมดจำลองสร้างคลิป (หัก/คืนเครดิตจริงแต่ไม่เรียก AI) |
| `ALLOW_QUICK_LOGIN=1` | เปิด `/api/quick-login` สำหรับเครื่อง dev เท่านั้น (ค่าเริ่ม: ปิด) |
| `SCHEDULER_WORKER` | `1` (ค่าเริ่ม) = รัน worker Auto-Post ในเซิร์ฟเวอร์ทุก `SCHEDULER_INTERVAL` วินาที (20) |
| `SCHEDULER_SECRET` | ใช้กับ cron ภายนอก: `POST /api/scheduler/tick` + header `X-Cron-Secret` (สำหรับ serverless) |

## ตั้งค่า Meta App (แอดมิน ครั้งเดียว)

1. developers.facebook.com/apps → Create app → use case "Manage everything on your Page" + "Manage messaging & content on Instagram"
2. Facebook Login for Business → Valid OAuth Redirect URIs = `<PUBLIC_BASE_URL>/api/oauth/facebook/callback`
3. Instagram → Business login settings → Redirect = `<PUBLIC_BASE_URL>/api/oauth/instagram/callback`
4. ใส่ App ID/Secret ใน Connectors → "ตั้งค่าแอป (Admin)" หรือ ENV
5. Development mode ใช้ได้เฉพาะ Admin/Tester ของแอป — ส่ง App Review สิทธิ์ `pages_manage_posts`, `instagram_business_content_publish` ก่อนเปิดให้ทุกคน

## ทดสอบทั้งระบบแบบไม่ใช้บัญชีจริง

```bash
pip install -r requirements.txt
dev_tools/run_e2e.sh            # mock Meta/IG/LINE/Shopee ที่ :9100 + แอปที่ :8010 (VIDEO_MOCK=1)
PYTHONPATH=. pytest tests tests_beta tests_unified tests_v8
```

คีย์ทดสอบของ mock: Shopee AppID `15012345678` / Secret `MOCKSHOPEESECRET01` · LINE Channel ID `1650000000` / Secret `0123456789abcdef0123456789abcdef`

## หมายเหตุสำคัญ

- Webhook ของ LINE และ OAuth ของ Meta ต้องการเว็บ https สาธารณะ — บน 127.0.0.1 จะใช้ได้เฉพาะโหมด mock
- Auto-Post บน serverless (Vercel/Netlify): ตั้ง cron เรียก `/api/scheduler/tick` ทุก 1 นาที — Facebook ที่ฝากคิวล่วงหน้าไม่ต้องพึ่ง cron
- Vercel serverless ไม่รองรับ WebSocket: แชทจะสลับเป็นโหมด polling อัตโนมัติ (ทำงานได้แต่ช้ากว่า) — Railway/Docker รองรับ realtime เต็ม
- คลิปพรีวิวสร้างในเบราว์เซอร์ (Canvas + MediaRecorder) ได้ไฟล์ MP4 (Chrome/Safari ใหม่) หรือ WebM — TikTok รับทั้งสองแบบ
