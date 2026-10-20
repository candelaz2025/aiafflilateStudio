# AI Studio Pro — ระบบ Auto Gen Video, Drama AI, UGC, Meta AI & Google Flow

ระบบสตูดิโอสร้างวิดีโออัตโนมัติเต็มรูปแบบสำหรับ **macOS (Desktop App)** ออกแบบมาสำหรับงานสร้างคอนเทนต์แนวตั้ง (Vertical 9:16) บน TikTok, Reels, Shorts และ Shopee Video

---

## 🌟 จุดเด่นและฟีเจอร์หลัก (Features)

### 1. แดชบอร์ด & ระบบโชว์การทำงานสด (Live Workflow Visualizer)
- แสดงสถานะระบบแบบ Realtime (งานที่รันอยู่, งานในคิว, คลิปที่สร้างเสร็จ, แผนใน Calendar)
- **Interactive Pipeline Flow**: แสดงสถานะ 5 ขั้นตอนแบบเห็นภาพชัดเจน:
  `[1. คิด & ปรับ Prompt] → [2. ส่ง Engine] → [3. Render โมชัน 9:16] → [4. ประมวลผล MP4 & Thumbnail] → [5. คอนเทนต์พร้อมใช้]`
- **Worker Terminal Console**: หน้าต่างแสดงบันทึกการทำงาน (Log stream) สด พร้อม Timestamp แบบนาทีต่อวินาที
- **เครื่องเล่นวิดีโอในตัว (Modal Player)**: รองรับการเปิดดูคลิปแนวตั้ง 9:16 ทันที และดาวน์โหลดไฟล์ MP4 (H.264 / AAC)

### 2. Drama AI Studio (ระบบสร้างซีรีส์ละครสั้น)
- เลือกแนวละครยอดนิยม (ประธานหนุ่มปลอมตัว, ศึกแม่ผัวลูกสะใภ้, ลุ้นระทึกหักมุม, ดราม่าออฟฟิศ)
- สร้างโครงเรื่อง (Synopsis), ข้อมูลตัวละคร (Characters Bible)
- **แยกตอนอัตโนมัติ (Episodes Breakdown)** พร้อม:
  - **3-Second Viral Hook**: คำเปิดเรื่องดึงสายตาคนดูใน 3 วินาทีแรก
  - **บทพูดและอารมณ์ (Thai Dialogue)**
  - **จุดหักมุมชวนติดตาม (Cliffhanger)**
  - **Visual Prompt สำหรับ AI Video**: 9:16 Cinematic Film Look, 24fps
  - ปุ่ม **"🚀 สั่ง Gen คลิปตอนนี้"** 1-Click ส่งเข้าคิวสร้างวิดีโอทันที

### 3. UGC Creator AI (สร้างคลิปรีวิว & ป้ายยาสินค้า)
- กรอกชื่อสินค้า, หมวดหมู่ (สกินแคร์, แก็ดเจ็ต, แฟชั่น, ของใช้ในบ้าน ฯลฯ)
- สูตร Hook ยอดฮิต:
  - *Problem - Solution* (ปัญหาที่ทุกคนเจอ → เฉลยทางรอด)
  - *POV Unboxing* (แกะกล่องสด & First Impression)
  - *7-Day Challenge* (ท้าพิสูจน์ผลลัพธ์ 7 วัน)
  - *Stop Scrolling Warning* (เตือนภัย / หยุดทำสิ่งนี้)
- แจกแจงสคริปต์พูดตามช่วงเวลา (0-3s, 3-7s, 7-12s, 12-16s, 16-20s)
- สร้างฉากสำหรับ AI Video (ฉากหน้ากล้อง, ฉากมาโครสัมผัสเนื้อสินค้า POV, ฉากรีแอ็กชัน)
- แคปชันพร้อมแฮชแท็กติดเทรนด์

### 4. ระบบช่วยคิด Prompt (AI Video Prompt Studio)
- เปลี่ยนไอเดียสั้นๆ ภาษาไทย ให้กลายเป็น Prompt ภาษาอังกฤษระดับสตูดิโอ Hollywood
- ปรับแต่งตาม Engine: **Google Flow / Veo 3.1** และ **Meta AI Movie Gen**
- ระบบเลือกมุมกล้อง (Camera Motion) และการจัดแสง (Lighting & Atmosphere) อัตโนมัติ
- ใส่ **Negative Prompt** ตัดความบิดเบี้ยว นิ้วเกิน หรือภาพเบลออัตโนมัติ
- ปุ่มส่งเข้าคิวสร้างคลิปได้ในคลิกเดียว

### 5. Engine สร้างวิดีโอ: Google Flow & Meta AI
- **Google Flow / Google Veo**: รองรับการสร้างวิดีโอผ่าน Google GenAI API (`veo-3.1-generate-preview`, `veo-2.0-generate-001`)
- **Meta AI (Movie Gen / Imagine Video)**: รองรับการเชื่อมต่อกับ Meta Movie Gen ผ่าน Browser Automation / Token
- **High-Speed Studio Simulation Mode**: โหมดจำลองในเครื่องด้วย FFmpeg + Pillow เร่งความเร็วด้วยชิป Apple Silicon (ARMv8 NEON) สร้างคลิป 9:16 คมชัด พร้อม Thumbnail ในเสี้ยววินาที สำหรับการทดสอบและพรีวิวโดยไม่ต้องหักเครดิต API จริง

### 6. ระบบจัดคิว & Auto Worker (Background Queue Engine)
- Background Worker ทำงานในเบื้องหลังตลอดเวลา
- จัดลำดับคิวตาม Priority
- แสดงความคืบหน้า 0% - 100% ของแต่ละงาน
- ระบบแจ้งเตือนไปยังหน้าจอ Mac ทันทีเมื่อสร้างคลิปเสร็จ ผ่าน **Native AppleScript Notifications**

### 7. ระบบ Calendar ช่วยสร้างแผนคอนเทนต์ (Content Planner)
- วางแผนปล่อยคลิปอัตโนมัติ **7 วัน / 14 วัน / 30 วัน** ในคลิกเดียว
- กำหนดวัน เวลาปล่อยคลิป (เช่น 19:00 น.), ช่องทางเป้าหมาย (TikTok, Reels, Shorts)
- **Auto-Gen Trigger**: เมื่อถึงวันและเวลาที่กำหนด ระบบจะดึงงานเข้าคิวและเรนเดอร์วิดีโอให้อัตโนมัติทันที
- ปุ่ม **"⚡ สั่งสร้างทั้งหมดตอนนี้ (Queue All Now)"** เพื่อแปลงทั้งแผนลงคิวทันที

---

## 💻 วิธีการเปิดใช้งานบน Mac OSX (3 วิธี)

### วิธีที่ 1: ดับเบิลคลิกเปิด macOS App (แนะนำที่สุด)
ในโฟลเดอร์โครงการ มีไฟล์แอปพลิเคชันสำหรับ Mac เตรียมไว้แล้ว:
```bash
open AIStudio.app
```
หรือสามารถเปิดผ่าน Finder แล้วดับเบิลคลิกที่ **`AIStudio.app`** ได้ทันที!

### วิธีที่ 2: รันผ่านสคริปต์ Terminal
```bash
./run_mac_app.sh
```
*หากต้องการเปิดผ่านเบราว์เซอร์เริ่มต้นของ Mac โดยตรง:*
```bash
./run_mac_app.sh --browser
```

### วิธีที่ 3: รันผ่านคำสั่ง npm
```bash
npm run mac-app
# หรือรันเซิร์ฟเวอร์เฉพาะ:
npm run auto-studio
```

เมื่อเปิดแอป ระบบจะรันที่ **`http://127.0.0.1:8888`** พร้อมหน้าต่าง Native Mac Glassmorphic สุดล้ำ

---

## 📁 โครงสร้างระบบ (Architecture Overview)

```
AIStudio/
├── AIStudio.app/                  # macOS Application Bundle (Click-to-run)
│   └── Contents/
│       ├── Info.plist             # macOS App metadata
│       └── MacOS/AIStudio         # macOS executable launcher
├── auto_studio/                   # โค้ดหลักระบบ Auto Gen Studio
│   ├── api.py                     # FastAPI REST API & Server
│   ├── db.py                      # SQLite database layer (WAL mode)
│   ├── queue_worker.py            # Background worker & auto-scheduler
│   ├── prompt_engine.py           # ช่วยคิด Prompt, Drama AI, UGC Generator
│   ├── calendar_service.py        # แผนงาน Calendar 7/14/30 วัน
│   ├── mac_launcher.py            # ตัวรัน Native Mac WebKit Desktop Window
│   ├── engines/
│   │   ├── google_flow.py         # Google Flow / Veo connector
│   │   ├── meta_ai.py             # Meta AI Movie Gen connector
│   │   └── video_renderer.py      # FFmpeg 9:16 vertical video compiler
│   ├── data/                      # ฐานข้อมูล auto_studio.db
│   ├── output/                    # ไฟล์วิดีโอ MP4 แนวตั้ง 9:16 ที่สร้างสำเร็จ
│   │   └── thumbnails/            # รูปภาพโปสเตอร์พรีวิว
│   └── static/                    # หน้าจอ macOS UI (HTML, CSS, JS)
├── run_mac_app.sh                 # เชลล์สคริปต์รันบน Mac
├── tests_auto_studio/             # ชุดทดสอบ Unit & Integration Tests (9 passed)
└── package.json                   # การตั้งค่าคำสั่ง npm
```

---

## 🧪 การทดสอบระบบ (Automated Tests)

รันชุดทดสอบความถูกต้องทั้งหมดด้วยคำสั่ง:
```bash
PYTHONPATH=. .venv/bin/pytest tests_auto_studio
```
ผลลัพธ์ผ่านครบทั้ง 9 รายการ (Database, Prompt Optimizer, Drama AI, UGC AI, Google Flow Engine, Meta AI Engine, Calendar Planner, Queue Worker, และ API Endpoints).
