"""AI Prompt Studio, Drama AI, UGC Content Generator, Character Lock & Storyboard System.
Provides 30 high-converting templates, Character Consistency Tokens, Voice & Visual Tones,
and visual storyboard frame rendering with Pillow.
"""
from __future__ import annotations
import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from auto_studio.db import get_setting

ROOT = Path(__file__).resolve().parent
if os.environ.get("VERCEL"):
    STORYBOARD_DIR = Path("/tmp/auto_studio_output/storyboards")
else:
    STORYBOARD_DIR = ROOT / "output" / "storyboards"
STORYBOARD_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# 1. Voice Tones & Visual Tones
# -------------------------------------------------------------
VOICE_TONES = [
    {"key": "authentic_friendly", "name": "เสียงจริงใจ เป็นกันเอง เข้าถึงง่าย (Authentic & Conversational)", "instruction": "Natural speaking tone, casual warm Thai pacing, relatable friend-to-friend advice"},
    {"key": "energetic_hype", "name": "เสียงตื่นเต้น เร้าใจ ดึงดูดไว (High-Energy Viral Hype)", "instruction": "Fast-paced enthusiastic cadence, high vocal energy, punchy syllable emphasis for TikTok"},
    {"key": "dramatic_intense", "name": "เสียงดุดัน จริงจัง เชือดเฉือนอารมณ์ (Dramatic & Intense)", "instruction": "Low pitch, measured tension pauses, cold authoritative cadence with emotional gravity"},
    {"key": "warm_storyteller", "name": "เสียงนุ่มนวล อบอุ่น เล่าเรื่องเพลิน (Warm & Narrative)", "instruction": "Gentle soothing bedtime/story cadence, melodious articulation, comforting empathy"},
    {"key": "luxury_seductive", "name": "เสียงหรูหรา สุขุม ชวนค้นหา (Luxury & Confident)", "instruction": "Smooth refined tone, sophisticated breath control, premium brand aesthetic"},
    {"key": "whisper_asmr", "name": "เสียงกระซิบ ASMR ระยะประชิด (Sensory Whisper ASMR)", "instruction": "Soft intimate whisper, crisp proximity microphone cues, sensory binaural vibes"}
]

VISUAL_TONES = [
    {"key": "cinematic_35mm", "name": "Cinematic 35mm Film Look (โทนหนังฟิล์มฮอลลีวูด คอนทราสต์ลึก)", "prompt_cue": "Shot on Arri Alexa 35mm anamorphic lens, deep cinematic contrast, subtle film grain, rich filmic color grading"},
    {"key": "cyberpunk_neon", "name": "Cyberpunk Neon Glow (แสงไฟนีออนฟ้า-ม่วง กรุงเทพฯ กลางคืน)", "prompt_cue": "Moody rain-slicked neon street aesthetic, vibrant cyan and magenta rim lighting, cyberpunk reflections"},
    {"key": "natural_daylight", "name": "Natural Daylight Clean POV (แสงธรรมชาติ ละมุน สไตล์ไอโฟน)", "prompt_cue": "Authentic iPhone 15 Pro natural morning window light, high dynamic range, crisp realistic skin texture"},
    {"key": "warm_golden_hour", "name": "Warm Golden Hour Sunlight (แสงแดดสีทองอบอุ่น ละมุนตา)", "prompt_cue": "Warm sunset amber backlighting, ethereal bokeh, romantic soft golden flare, cozy lifestyle cinema"},
    {"key": "korean_aesthetic", "name": "Korean Clean Minimalist (โทนเกาหลี คลีน ผิวกระจก คมชัด)", "prompt_cue": "Clean Seoul aesthetic, soft diffused ring light, glass-skin clarity, minimalist pastel modern interior"},
    {"key": "vintage_retro", "name": "Vintage 90s Film Grain (เรโทรย้อนยุค สีนวล อารมณ์คลาสสิก)", "prompt_cue": "Vintage 1990s color reversal film stock, nostalgic warm tones, soft halation around highlights"},
    {"key": "dark_noir", "name": "Moody Dark Chiaroscuro (ดาร์ก นัวร์ แสงเงาเชือดเฉือน ดราม่า)", "prompt_cue": "High-contrast dramatic chiaroscuro shadow play, mystery silhouette, moody noir atmosphere, 24fps"},
    {"key": "luxury_studio", "name": "High-End Commercial Studio (สตูดิโอไฮเอนด์ แสงสว่าง คมกริบ)", "prompt_cue": "Commercial advertising studio lighting, razor-sharp product details, ultra-clean commercial aesthetic"}
]

GENDERS = [
    {"key": "female", "name": "ผู้หญิง (Female Creator / Lead)"},
    {"key": "male", "name": "ผู้ชาย (Male Creator / Lead)"},
    {"key": "duo", "name": "คู่รัก / สองคน (Duo / Couple)"}
]

# Character Presets for Instant Locking
CHARACTER_PRESETS = [
    {
        "id": "char_arin",
        "gender": "female",
        "name": "อริน (Arin)",
        "age": 24,
        "role": "สาวเก่ง สู้ชีวิต / ครีเอเตอร์ป้ายยา",
        "anchor_token": "Consistent Subject: 24yo Thai woman named Arin, shoulder-length wavy dark brown hair, almond-shaped amber eyes, neat bangs, small beauty mark below right eye, cream casual blazer, identical facial structure across all scenes"
    },
    {
        "id": "char_phat",
        "gender": "male",
        "name": "ภัทร (Phat)",
        "age": 28,
        "role": "ประธานหนุ่มสุขุม / นักธุรกิจซ่อนคม",
        "anchor_token": "Consistent Subject: 28yo Thai man named Phat, sharp jawline, short styled side-part black hair, intense dark eyes, fitted navy charcoal tailored suit, identical facial features across all scenes"
    },
    {
        "id": "char_ploy",
        "gender": "female",
        "name": "พลอย (Ploy)",
        "age": 22,
        "role": "ครีเอเตอร์สายบิวตี้ / นักศึกษาสดใส",
        "anchor_token": "Consistent Subject: 22yo bright Thai female creator named Ploy, long straight glossy black hair with pink hairclip, cheerful smiling dimples, oversized pastel knit sweater, identical facial traits across shots"
    },
    {
        "id": "char_ken",
        "gender": "male",
        "name": "เคน (Ken)",
        "age": 25,
        "role": "ครีเอเตอร์สายไอที & แกดเจ็ต",
        "anchor_token": "Consistent Subject: 25yo modern Thai male tech reviewer named Ken, round tortoiseshell spectacles, messy fringe dark hair, black minimalist hoodie, identical facial anatomy across shots"
    }
]

CAMERA_MOTIONS = [
    "Handheld dynamic iPhone POV with subtle natural shake",
    "Slow cinematic push-in towards the subject's face",
    "Dramatic orbital 360-degree rotation around the subject",
    "Smooth steadycam tracking shot following subject forward",
    "Extreme macro close-up panning across texture details",
    "Low angle Dutch tilt emphasizing dramatic tension",
    "Fast whip pan transitioning into energetic action"
]

LIGHTING_STYLES = [
    "Natural soft morning window sunlight with gentle lens flare",
    "Dramatic high-contrast chiaroscuro with deep moody rim shadows",
    "Warm golden hour sunset glow, cinematic 35mm film grain",
    "Cool cyberpunk neon lighting with vibrant purple and cyan accents",
    "Clean studio softbox lighting, ultra-sharp realistic skin tone",
    "Overcast moody Scandinavian cinema aesthetic, desaturated tones"
]

NEGATIVE_PROMPTS = (
    "blurry, out of focus, distorted facial features, extra fingers, deformed hands, "
    "low resolution, low quality, cartoon, anime, 3d render, plastic skin, oversaturated, "
    "watermark, text overlay, bad anatomy, jumpy frames, glitch, noisy artifacts"
)


# -------------------------------------------------------------
# 2. Complete 30 High-Converting Templates (15 UGC + 15 Drama)
# -------------------------------------------------------------
TEMPLATES_30 = [
    # --- 15 UGC Templates ---
    {"id": "ugc_01", "type": "ugc", "category": "Problem-Solution", "title": "ปัญหาเรื้อรัง → ทางออกเปลี่ยนชีวิต", "hook": "ถ้าใครกำลังเจอปัญหานี้ อย่าเพิ่งเลื่อนผ่านเด็ดขาด!", "voice_tone": "authentic_friendly", "visual_tone": "natural_daylight", "summary": "เปิดด้วยปัญหาที่คนดูเจอทุกวัน ชี้จุดเจ็บปวด แล้วเฉลยสินค้าเป็นฮีโร่กู้ชีพ"},
    {"id": "ugc_02", "type": "ugc", "category": "Unboxing", "title": "POV แกะกล่องสด สัมผัสแรกแบบเรียล", "hook": "ของเพิ่งส่งถึงหน้าบ้านสดๆ มาดูกันว่าจะตรงปกไหม!", "voice_tone": "energetic_hype", "visual_tone": "natural_daylight", "summary": "มุมมอง POV มือฉีกซอง สัมผัสวัสดุ ให้ความรู้สึกตื่นเต้นเหมือนได้แกะเอง"},
    {"id": "ugc_03", "type": "ugc", "category": "Transformation", "title": "ท้าพิสูจน์ผลลัพธ์ 7 วัน ชัดเจน", "hook": "ทนกระแสไม่ไหวจนต้องลองเอง 7 วันเต็ม... ผลคือช็อกมาก!", "voice_tone": "warm_storyteller", "visual_tone": "korean_aesthetic", "summary": "บันทึกพัฒนาการ Day 1 ถึง Day 7 สร้างความน่าเชื่อถือด้วยผลลัพธ์จับต้องได้"},
    {"id": "ugc_04", "type": "ugc", "category": "Warning Hook", "title": "เตือนภัย! อย่าเพิ่งซื้อถ้ายังไม่รู้สิ่งนี้", "hook": "หยุด! ถ้ายังใช้วิธีเดิมๆ อยู่ คุณกำลังพลาดสิ่งนี้ไปเต็มๆ!", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "ใช้ Negative Hook ชะลอนิ้วโป้งคนดู เตือนข้อผิดพลาดก่อนเฉลยทางเลือกที่ดีกว่า"},
    {"id": "ugc_05", "type": "ugc", "category": "Comparison", "title": "เทียบตัวตายตัวแทน ถูกกว่า 5 เท่า (Dupe)", "hook": "ทำไมต้องจ่ายหลักพัน ในเมื่อตัวนี้คุณภาพเท่ากันแต่หลักร้อย!", "voice_tone": "authentic_friendly", "visual_tone": "luxury_studio", "summary": "เปรียบเทียบแบรนด์เนม vs ตัวเลือกสุดคุ้ม ป้ายยาสายประหยัดฉลาดเลือก"},
    {"id": "ugc_06", "type": "ugc", "category": "ASMR Sensory", "title": "ASMR สัมผัสเสียงและเนื้อสัมผัสระยะประชิด", "hook": "[เสียงกรีดกล่อง/ปาดเนื้อครีม] ฟังเสียงนี้สิทุกคน ฟินมาก!", "voice_tone": "whisper_asmr", "visual_tone": "warm_golden_hour", "summary": "เน้นเสียงรอบข้าง ปาดเนื้อสัมผัส ชวนฟิน ดึงดูดให้ดูจนจบด้วยความเพลิน"},
    {"id": "ugc_07", "type": "ugc", "category": "Honest Regret", "title": "รู้งี้ซื้อนานแล้ว! ทำไมเพิ่งมาเจอ", "hook": "สิ่งที่เสียดายที่สุดคือ... ทำไมฉันเพิ่งมารู้จักสิ่งนี้ปี 2026!", "voice_tone": "authentic_friendly", "visual_tone": "natural_daylight", "summary": "ใช้จิตวิทยาเสียดายโอกาส เปลี่ยนความลังเลของคนดูให้กลายเป็นอยากลอง"},
    {"id": "ugc_08", "type": "ugc", "category": "Before & After", "title": "รีแอ็กชันก่อน-หลังใช้แบบ Real", "hook": "ดูความต่างตรงนี้ชัดๆ ไม่ใช้ฟิลเตอร์แม้แต่นิดเดียว!", "voice_tone": "energetic_hype", "visual_tone": "korean_aesthetic", "summary": "โชว์ความแตกต่างแบบครึ่งหน้า หรือ Before-After แบบไม่จัดฉาก"},
    {"id": "ugc_09", "type": "ugc", "category": "Lifestyle Vlog", "title": "Vlog 1 วัน พกตัวนี้ไปด้วยทุกที่ (GRWM)", "hook": "พกอะไรในกระเป๋าบ้าง? ชิ้นนี้ขาดไม่ได้เลยในทุกๆ วัน", "voice_tone": "warm_storyteller", "visual_tone": "warm_golden_hour", "summary": "ผูกสินค้าเข้ากับกิจวัตรประจำวัน ทำให้สินค้าดูจำเป็นและกลมกลืนกับชีวิต"},
    {"id": "ugc_10", "type": "ugc", "category": "Education", "title": "3 ข้อผิดพลาดที่คนส่วนใหญ่ทำผิด", "hook": "เช็กด่วน! ใครทำ 3 ข้อนี้อยู่ ระวังพังไม่รู้ตัวนะ", "voice_tone": "dramatic_intense", "visual_tone": "luxury_studio", "summary": "ให้ความรู้ที่เป็นประโยชน์ ชี้ข้อผิดพลาด แล้วแนะนำวิธีแก้ด้วยสินค้า"},
    {"id": "ugc_11", "type": "ugc", "category": "Viral Testing", "title": "ลองของดังตามกระแส จะรอดหรือร่วง?", "hook": "เห็นในฟีดเป็นล้านวิว สั่งมาเทสต์ให้ดูจะจะ ว่าคุ้มจริงไหม!", "voice_tone": "energetic_hype", "visual_tone": "natural_daylight", "summary": "เกาะกระแสไวรัล ทดลองสินค้าที่คนกำลังสงสัย ช่วยตัดสินใจซื้อแทนคนดู"},
    {"id": "ugc_12", "type": "ugc", "category": "Speed Pitch", "title": "รีวิวเร็ว 15 วิ สรุปจุดเด่นทันที", "hook": "สรุปให้ใน 15 วิ ตัวนี้ดียังไง ทำไมขายดีอันดับ 1 ในตะกร้า!", "voice_tone": "energetic_hype", "visual_tone": "luxury_studio", "summary": "กระชับ ตรงประเด็น เหมาะกับคนสมาธิสั้น ปิดการขายไวภายใน 15-20 วินาที"},
    {"id": "ugc_13", "type": "ugc", "category": "Gift Idea", "title": "ป้ายยาของขวัญที่ใครได้ก็ต้องชอบ", "hook": "ถ้ากำลังหาของขวัญให้แฟน หรือให้เพื่อน เซฟคลิปนี้ไว้เลย!", "voice_tone": "warm_storyteller", "visual_tone": "warm_golden_hour", "summary": "ชูจุดเด่นความพรีเมียม แพ็กเกจหรู เหมาะกับการมอบเป็นของขวัญทุกโอกาส"},
    {"id": "ugc_14", "type": "ugc", "category": "Myth Buster", "title": "ตอบคำถามยอดฮิต เคลียร์ทุกข้อสงสัย", "hook": "หลายคนถามเข้ามาเยอะมากว่า ใช้แล้วเป็นยังไง วันนี้มาตอบให้หมด!", "voice_tone": "authentic_friendly", "visual_tone": "korean_aesthetic", "summary": "เคลียร์ข้อกังขาเรื่องความปลอดภัย คุณภาพ และวิธีใช้ สร้างความมั่นใจ 100%"},
    {"id": "ugc_15", "type": "ugc", "category": "Urgency Alert", "title": "แจ้งเตือนของเข้า รีบกดก่อนหมดตะกร้า", "hook": "ของเติมสต็อกแล้วทุกคน! รอบที่แล้วหมดใน 10 นาที รอบนี้อย่าช้า!", "voice_tone": "energetic_hype", "visual_tone": "natural_daylight", "summary": "สร้างความขาดแคลน (FOMO) กระตุ้นให้คนดูรีบกดตะกร้าสั่งซื้อทันที"},

    # --- 15 Drama AI Templates ---
    {"id": "drama_01", "type": "drama", "category": "Undercover Boss", "title": "ประธานหนุ่มปลอมตัวเป็นคนทำความสะอาด", "hook": "\"คนอย่างแก ไม่มีสิทธิ์แม้แต่จะเหยียบพรมของตึกนี้!\"", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "มหาเศรษฐีปลอมตัวถูกเหยียดหยาม ก่อนจะตลบหลังเปิดเผยฐานะสั่งปลดผู้จัดการ"},
    {"id": "drama_02", "type": "drama", "category": "Family Feud", "title": "สะใภ้ร้อยล้านที่ถูกแม่สามีขับไล่", "hook": "\"ตระกูลเราไม่ต้อนรับคนไร้หัวนอนปลายเท้าอย่างเธอ!\"", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "สะใภ้แสนดีถูกขับไล่ แต่แท้จริงเธอคือเจ้าของสัญญาเงินกู้ที่ค้ำจุนทั้งตระกูล"},
    {"id": "drama_03", "type": "drama", "category": "Secret Bodyguard", "title": "บอดี้การ์ดสาวผู้กุมความลับตระกูลดัง", "hook": "\"อย่าขยับ... กระสุนนัดนี้ เล็งไว้ที่หัวใจคุณนานแล้ว\"", "voice_tone": "dramatic_intense", "visual_tone": "dark_noir", "summary": "บอดี้การ์ดฝีมือพระกาฬที่แฝงตัวมาเพื่อปกป้องทายาทคนสุดท้ายจากการลอบสังหาร"},
    {"id": "drama_04", "type": "drama", "category": "Office Whistleblower", "title": "เด็กฝึกงานที่มาเพื่อล้างบางทุจริต", "hook": "\"คุณคิดว่าเอกสารลับแผ่นนี้ ถูกซ่อนมิดชิดแล้วจริงๆ เหรอ?\"", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "เด็กฝึกงานที่ถูกดูถูก แท้จริงคือผู้ตรวจสอบพิเศษจากสำนักงานใหญ่"},
    {"id": "drama_05", "type": "drama", "category": "Lost Heir", "title": "ทายาทตัวจริงกลับมาทวงบัลลังก์", "hook": "\"สิบปีที่แล้วพวกแกแย่งทุกอย่างไป วันนี้ฉันมาเอาคืนพร้อมดอกเบี้ย!\"", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "เด็กกำพร้าที่ถูกใส่ร้าย กลับมาพร้อมหลักฐาน DNA และอำนาจมหาศาล"},
    {"id": "drama_06", "type": "drama", "category": "Betrayal Exposed", "title": "จับโป๊ะชู้รักในห้องประชุมปิดตาย", "hook": "\"โปรเจกต์ที่เธอภูมิใจนักหนา... มันคือแผนล่อเสือออกจากถ้ำ!\"", "voice_tone": "dramatic_intense", "visual_tone": "dark_noir", "summary": "การเปิดโปงความสัมพันธ์ลับกลางงานแถลงข่าวใหญ่ ด้วยคลิปหลักฐานที่ซ่อนไว้"},
    {"id": "drama_07", "type": "drama", "category": "Countdown Revenge", "title": "แผนแก้แค้น 24 ชั่วโมง เอาคืนคนหักหลัง", "hook": "\"เหลือเวลาอีก 3 ชั่วโมง ก่อนที่หุ้นบริษัทแกจะกลายเป็นเศษกระดาษ!\"", "voice_tone": "dramatic_intense", "visual_tone": "cyberpunk_neon", "summary": "การเดินเกมการเงินและการเชือดเฉือนแบบนับถอยหลัง ลุ้นระทึกทุกวินาที"},
    {"id": "drama_08", "type": "drama", "category": "Incognito Doctor", "title": "หมอเทวดาผู้ซ่อนตัวอยู่ในคลินิกเก่า", "hook": "\"หมอโรงพยาบาลใหญ่บอกว่าหมดทางรักษา... แต่สำหรับฉัน นี่แค่เริ่มต้น\"", "voice_tone": "warm_storyteller", "visual_tone": "cinematic_35mm", "summary": "ศัลยแพทย์อัจฉริยะที่ถูกยึดใบอนุญาต กลับมาช่วยชีวิตมหาเศรษฐีด้วยวิธีปริศนา"},
    {"id": "drama_09", "type": "drama", "category": "Villainess Rebirth", "title": "นางร้ายกลับชาติมาเกิดใหม่เพื่อเอาคืน", "hook": "\"ในเมื่อชาติก่อนความใจดีฆ่าฉัน ชาตินี้ฉันจะเป็นฝันร้ายของพวกแกเอง!\"", "voice_tone": "luxury_seductive", "visual_tone": "dark_noir", "summary": "การเกิดใหม่ของหญิงสาวผู้รู้ล่วงหน้าทุกหมาก ปั่นหัวศัตรูให้พังทลายทีละคน"},
    {"id": "drama_10", "type": "drama", "category": "Double Agent", "title": "เลขาผู้เรียบร้อยแท้จริงคือแฮกเกอร์ระดับโลก", "hook": "\"ระบบรักษาความปลอดภัย 5 ชั้นของคุณ... ฉันเจาะผ่านตั้งแต่วินาทีแรกแล้ว\"", "voice_tone": "whisper_asmr", "visual_tone": "cyberpunk_neon", "summary": "เลขาหน้าห้องที่ดูไร้พิษสง แต่เบื้องหลังคือนักเจาะระบบที่คุมความลับทุกคนในเมือง"},
    {"id": "drama_11", "type": "drama", "category": "Royal Legacy", "title": "ตราประจำตระกูลที่หายไป 20 ปี", "hook": "\"ตราหยกชิ้นนี้... มีคนเดียวในโลกที่มีสิทธิ์ครอบครอง!\"", "voice_tone": "dramatic_intense", "visual_tone": "warm_golden_hour", "summary": "การประมูลของเก่าที่กลายเป็นเวทีประจานคนทรยศ เมื่อของสำคัญถูกเปิดเผย"},
    {"id": "drama_12", "type": "drama", "category": "Deadly Dinner", "title": "มื้อค่ำลวงโลก ทุกคนในโต๊ะคือผู้ต้องสงสัย", "hook": "\"ก่อนจะดื่มไวน์แก้วนี้... ใครจะสารภาพก่อนว่าใครตัดสายเบรกรถฉัน?\"", "voice_tone": "dramatic_intense", "visual_tone": "dark_noir", "summary": "อาหารค่ำในคฤหาสน์ปิดตายกลางพายุ ทุกคำพูดคือกับดักและคำสารภาพ"},
    {"id": "drama_13", "type": "drama", "category": "Contract Marriage", "title": "สัญญาแต่งงาน 1 ปี ที่ซ่อนความลับ", "hook": "\"สัญญาฉบับนี้มีข้อเดียว... ห้ามตกหลุมรักฉันเด็ดขาด\"", "voice_tone": "luxury_seductive", "visual_tone": "korean_aesthetic", "summary": "การแต่งงานเพื่อธุรกิจที่แฝงไปด้วยความรู้สึกจริง และเบื้องหลังแผนการใหญ่"},
    {"id": "drama_14", "type": "drama", "category": "Silent Guardian", "title": "เงาปริศนาที่คอยปกป้องนางเอกจากมุมมืด", "hook": "\"เธอไม่จำเป็นต้องรู้ว่าฉันเป็นใคร... รู้แค่ว่าใครแตะต้องเธอ มันต้องชดใช้\"", "voice_tone": "whisper_asmr", "visual_tone": "dark_noir", "summary": "อดีตมาเฟียที่คอยคุ้มครองหญิงสาวผู้มีพระคุณ โดยไม่ยอมให้เธอเห็นใบหน้า"},
    {"id": "drama_15", "type": "drama", "category": "Boardroom Climax", "title": "ศึกตัดสินในห้องประชุม ผู้ถือหุ้น 51% คนใหม่", "hook": "\"ขอโทษที่มาช้า... พอดีเพิ่งเซ็นซื้อตึกนี้เสร็จเมื่อ 5 นาทีที่แล้ว!\"", "voice_tone": "dramatic_intense", "visual_tone": "cinematic_35mm", "summary": "ฉากไคลแมกซ์การโหวตถอดถอน ที่ตัวเอกเดินเข้ามาพร้อมหุ้นเสียงข้างมาก"}
]


# -------------------------------------------------------------
# 3. Character Lock & Storyboard Generator
# -------------------------------------------------------------
def build_character_lock_token(
    name: str,
    gender: str = "female",
    age: int = 24,
    role_or_outfit: str = "cream suit",
    distinct_feature: str = "distinctive facial structure and eyes"
) -> str:
    """Builds a deterministic character lock token for consistent AI generation."""
    g_term = "Thai woman" if gender == "female" else ("Thai man" if gender == "male" else "Thai subject")
    return (
        f"Consistent Subject Anchor: [Character: {name}, {age}yo {g_term}, {role_or_outfit}, "
        f"{distinct_feature}, identical face geometry, facial symmetry, and signature appearance across all shots]"
    )


def generate_storyboard(
    topic_or_product: str,
    template_id: Optional[str] = None,
    campaign_type: str = "ugc",
    gender: str = "female",
    voice_tone_key: str = "authentic_friendly",
    visual_tone_key: str = "natural_daylight",
    character_name: Optional[str] = None,
    total_scenes: int = 4
) -> Dict[str, Any]:
    """Generates a complete scene-by-scene storyboard with character lock and visual frames."""
    # Resolve Template
    template = next((t for t in TEMPLATES_30 if t["id"] == template_id), None)
    if not template:
        template = TEMPLATES_30[0] if campaign_type == "ugc" else TEMPLATES_30[15]

    # Resolve Tones
    vtone = next((v for v in VISUAL_TONES if v["key"] == visual_tone_key), VISUAL_TONES[2])
    voice = next((v for v in VOICE_TONES if v["key"] == voice_tone_key), VOICE_TONES[0])

    # Resolve Character Lock
    c_name = character_name or ("อริน (Arin)" if gender == "female" else "ภัทร (Phat)")
    c_token = build_character_lock_token(
        name=c_name,
        gender=gender,
        age=24 if gender == "female" else 28,
        role_or_outfit="signature modern aesthetic attire",
        distinct_feature="high-fidelity consistent facial identity"
    )

    scenes = []
    sample_actions = [
        ("0s-3s (Hook)", "Close-up front camera face", template["hook"]),
        ("3s-7s (Conflict / Pain)", "Medium shot demonstrating product / conflict", f"ปัญหาที่เจอกับ {topic_or_product} สลับกับมุมมองที่น่าสนใจ"),
        ("7s-12s (Demonstration / Twist)", "First-person POV macro hands", f"สัมผัสจริงของ {topic_or_product} เนื้อสัมผัสและการใช้งานแบบชัดเจน"),
        ("12s-16s (Resolution & CTA)", "Smiling to camera, pointing to bottom left", f"ผลลัพธ์น่าพอใจ และชวนกดดูรายละเอียด {topic_or_product} ที่ตะกร้าซ้ายมือ")
    ]

    for idx in range(min(total_scenes, len(sample_actions))):
        time_slot, camera_shot, script_text = sample_actions[idx]
        scene_num = idx + 1
        
        # Complete video prompt combining Character Lock + Scene Action + Visual Tone
        video_prompt = (
            f"Scene {scene_num}: {time_slot}. {c_token}. "
            f"Action: {script_text}. Camera: {camera_shot}. {vtone['prompt_cue']}. "
            f"Vertical 9:16 aspect ratio, cinematic lighting, 24fps motion, photorealistic."
        )

        # Render Storyboard Card Image with Pillow
        card_filename = f"sb_{template['id']}_sc{scene_num}_{random.randint(1000, 9999)}.jpg"
        card_path = STORYBOARD_DIR / card_filename
        _render_storyboard_card_image(
            dest_path=card_path,
            scene_num=scene_num,
            time_slot=time_slot,
            character_name=c_name,
            gender=gender,
            voice_tone_name=voice["name"].split("(")[0].strip(),
            visual_tone_name=vtone["name"].split("(")[0].strip(),
            script_text=script_text,
            camera_shot=camera_shot,
            topic=topic_or_product
        )

        scenes.append({
            "scene_number": scene_num,
            "timing": time_slot,
            "camera_shot": camera_shot,
            "spoken_line": script_text,
            "video_prompt": video_prompt,
            "image_url": f"/output/storyboards/{card_filename}"
        })

    return {
        "title": f"{template['title']} — {topic_or_product}",
        "template_id": template["id"],
        "category": template["category"],
        "character_lock": {
            "name": c_name,
            "gender": gender,
            "token": c_token
        },
        "voice_tone": voice,
        "visual_tone": vtone,
        "scenes": scenes,
        "total_scenes": len(scenes)
    }


def _render_storyboard_card_image(
    dest_path: Path,
    scene_num: int,
    time_slot: str,
    character_name: str,
    gender: str,
    voice_tone_name: str,
    visual_tone_name: str,
    script_text: str,
    camera_shot: str,
    topic: str
):
    """Draws a professional, high-definition visual storyboard card image."""
    width, height = 720, 1080
    bg = (11, 19, 41)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # 1. Header Bar
    draw.rectangle([(30, 30), (width - 30, 95)], fill=(20, 30, 55))
    draw.rectangle([(30, 30), (40, 95)], fill=(56, 189, 248))
    draw.text((55, 42), f"STORYBOARD CARD · SCENE {scene_num:02d}", fill=(56, 189, 248))
    draw.text((55, 68), f"TIMING: {time_slot}", fill=(148, 163, 184))

    # 2. Character Lock & Tones Badge
    draw.rectangle([(30, 110), (width - 30, 190)], fill=(25, 18, 45))
    draw.rectangle([(30, 110), (40, 190)], fill=(168, 85, 247))
    draw.text((55, 122), f"🔒 CHARACTER LOCK: {character_name} ({gender.upper()})", fill=(192, 132, 252))
    draw.text((55, 146), f"🎙 โทนเสียง: {voice_tone_name}", fill=(220, 220, 220))
    draw.text((55, 166), f"🎨 โทนภาพ: {visual_tone_name}", fill=(56, 189, 248))

    # 3. Main Scene Frame Visualization Box
    frame_top = 210
    frame_bottom = 680
    fw, fh = width - 60, frame_bottom - frame_top
    draw.rectangle([(30, frame_top), (width - 30, frame_bottom)], fill=(5, 10, 20), outline=(56, 189, 248), width=2)

    # Load and composite REAL photorealistic character portrait if available
    char_dir = ROOT / "static" / "assets" / "characters"
    c_lower = (character_name or "").lower()
    if gender == "male" or "ภัทร" in c_lower or "phat" in c_lower:
        c_file = char_dir / "char_phat.jpg"
    elif "พลอย" in c_lower or "ploy" in c_lower:
        c_file = char_dir / "char_ploy.jpg"
    else:
        c_file = char_dir / "char_arin.jpg"

    pasted_photo = False
    if c_file.exists():
        try:
            with Image.open(c_file) as c_raw:
                c_rgb = c_raw.convert("RGB")
                cw, ch = c_rgb.size
                scale = max(fw / cw, fh / ch)
                nw, nh = int(cw * scale), int(ch * scale)
                c_resized = c_rgb.resize((nw, nh), Image.Resampling.LANCZOS)
                
                # Crop with focus on face / upper body
                left = (nw - fw) // 2
                top_offset = int(nh * 0.12) if "close-up" in camera_shot.lower() else int(nh * 0.05)
                top_offset = min(top_offset, max(0, nh - fh))
                cropped = c_resized.crop((left, top_offset, left + fw, top_offset + fh))
                img.paste(cropped, (30, frame_top))
                pasted_photo = True
        except Exception:
            pasted_photo = False

    if not pasted_photo:
        # Fallback silhouette representation
        cx, cy = width // 2, (frame_top + frame_bottom) // 2
        draw.ellipse([(cx - 70, cy - 130), (cx + 70, cy + 10)], fill=(35, 45, 75), outline=(56, 189, 248), width=2)
        draw.polygon([(cx - 130, cy + 160), (cx + 130, cy + 160), (cx + 80, cy + 20), (cx - 80, cy + 20)], fill=(25, 35, 60))

    # Draw cinematic camera composition guides (Rule of Thirds)
    third_w = fw // 3
    third_h = fh // 3
    for i in range(1, 3):
        draw.line([(30 + i * third_w, frame_top), (30 + i * third_w, frame_bottom)], fill=(56, 189, 248, 80))
        draw.line([(30, frame_top + i * third_h), (width - 30, frame_top + i * third_h)], fill=(56, 189, 248, 80))

    # Corner viewfinder brackets
    bracket_len = 25
    draw.line([(35, frame_top + 5), (35 + bracket_len, frame_top + 5)], fill=(56, 189, 248), width=2)
    draw.line([(35, frame_top + 5), (35, frame_top + 5 + bracket_len)], fill=(56, 189, 248), width=2)
    draw.line([(width - 35, frame_top + 5), (width - 35 - bracket_len, frame_top + 5)], fill=(56, 189, 248), width=2)
    draw.line([(width - 35, frame_top + 5), (width - 35, frame_top + 5 + bracket_len)], fill=(56, 189, 248), width=2)

    # Frame labels & HUD
    draw.rectangle([(40, frame_top + 12), (320, frame_top + 42)], fill=(0, 0, 0))
    draw.text((45, frame_top + 16), f"🔴 REC  00:0{scene_num}:18  [ {camera_shot.upper()[:22]} ]", fill=(239, 68, 68))
    draw.text((width - 240, frame_top + 16), "ISO 400 · f/1.8 · 24FPS", fill=(200, 200, 200))
    draw.text((50, frame_bottom - 40), f"SUBJECT: {topic[:30]}", fill=(148, 163, 184))

    # 4. Spoken Dialogue / Script Box
    draw.rectangle([(30, 700), (width - 30, 890)], fill=(15, 23, 42))
    draw.rectangle([(30, 700), (40, 890)], fill=(52, 211, 153))
    draw.text((55, 715), "🎙 บทพูด / คำบรรยาย (Spoken Script):", fill=(52, 211, 153))
    
    # Wrap script text
    words = script_text.split()
    line1 = " ".join(words[:8])
    line2 = " ".join(words[8:16]) if len(words) > 8 else ""
    line3 = " ".join(words[16:24]) if len(words) > 16 else ""
    draw.text((55, 750), f'"{line1}', fill=(255, 255, 255))
    if line2:
        draw.text((55, 780), line2, fill=(255, 255, 255))
    if line3:
        draw.text((55, 810), f'{line3}"', fill=(255, 255, 255))
    else:
        draw.text((55 + len(line1) * 8, 750), '"', fill=(255, 255, 255))

    # 5. Visual Prompt Blueprint
    draw.rectangle([(30, 910), (width - 30, 1040)], fill=(2, 6, 23))
    draw.text((55, 922), "🎬 AI PROMPT BLUEPRINT (FOR GOOGLE FLOW & META AI):", fill=(56, 189, 248))
    draw.text((55, 950), f"Prompt: {character_name} in {visual_tone_name.lower()} | 9:16 Vertical | 24fps film motion", fill=(148, 163, 184))
    draw.text((55, 980), f"Motion: {camera_shot} | Audio: {voice_tone_name}", fill=(100, 116, 139))
    draw.text((55, 1010), "AI STUDIO PRO · STORYBOARD ENGINE", fill=(71, 85, 105))

    img.save(dest_path, format="JPEG", quality=90)


# -------------------------------------------------------------
# 4. Helper Function: Prompt Optimizer & Live Gemini Brain
# -------------------------------------------------------------
def _call_gemini_json(system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
    """Calls Gemini 2.5 Flash with structured JSON mode for production-quality content generation."""
    api_key = get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{system_prompt}\n\nUser Request: {user_prompt}",
            config=dict(response_mime_type="application/json")
        )
        if response and response.text:
            return json.loads(response.text)
    except Exception as exc:
        print(f"Gemini JSON Engine Notice ({exc}). Using template fallback.")
    return None


def _call_gemini_if_available(system_prompt: str, user_prompt: str) -> Optional[str]:
    api_key = get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{system_prompt}\n\nUser Request: {user_prompt}"
        )
        if response and response.text:
            return response.text.strip()
    except Exception:
        pass
    return None


def optimize_prompt(
    raw_idea: str,
    target_engine: str = "google_flow",
    aspect_ratio: str = "9:16",
    style_preference: Optional[str] = None,
    camera_motion: Optional[str] = None,
    lighting: Optional[str] = None,
    character_lock_token: Optional[str] = None
) -> Dict[str, Any]:
    selected_motion = camera_motion or random.choice(CAMERA_MOTIONS)
    selected_lighting = lighting or random.choice(LIGHTING_STYLES)
    char_prefix = f"{character_lock_token}. " if character_lock_token else ""

    # Attempt Live Gemini Generation for Deep Cinematic Optimization
    gemini_prompt = (
        f"Target Engine: {target_engine}\n"
        f"Idea: {raw_idea}\n"
        f"Camera Motion: {selected_motion}\n"
        f"Lighting: {selected_lighting}\n"
        f"Aspect Ratio: {aspect_ratio}\n"
        f"Style: {style_preference or 'Cinematic photorealistic 24fps film motion'}"
    )
    ai_json = _call_gemini_json(
        system_prompt="You are an award-winning cinematic director and AI video prompt engineer specializing in Google Veo 3.1 and Meta AI Movie Gen. "
                      "Convert the user's idea into an ultra-realistic, descriptive prompt with lighting, camera optics, physics, and human expressions. "
                      "Output JSON with keys: 'optimized_prompt' (string in English), 'negative_prompt' (string), 'camera_motion' (string), 'lighting' (string).",
        user_prompt=gemini_prompt
    )

    if ai_json and "optimized_prompt" in ai_json:
        final_prompt = ai_json["optimized_prompt"]
        if character_lock_token and character_lock_token not in final_prompt:
            final_prompt = f"{char_prefix}{final_prompt}"
        return {
            "raw_idea": raw_idea,
            "target_engine": target_engine,
            "aspect_ratio": aspect_ratio,
            "optimized_prompt": final_prompt,
            "camera_motion": ai_json.get("camera_motion", selected_motion),
            "lighting": ai_json.get("lighting", selected_lighting),
            "character_lock": character_lock_token or "",
            "negative_prompt": ai_json.get("negative_prompt", NEGATIVE_PROMPTS),
            "suggested_duration_seconds": 8 if target_engine == "google_flow" else 10
        }

    engine_cues = ""
    if target_engine == "meta_ai":
        engine_cues = "Meta AI Movie Gen aesthetic, 24fps film motion, temporal coherence, realistic physics, rich depth of field"
    elif target_engine == "google_flow":
        engine_cues = "Google Veo Flow generation, photorealistic textures, dynamic environmental motion, cinematic volumetric lighting, 4K UHD"
    else:
        engine_cues = "Ultra-realistic cinematic footage, high detail, masterpiece quality, 8k resolution"

    enhanced_prompt = (
        f"{char_prefix}{raw_idea}. {selected_motion}. {selected_lighting}. "
        f"Vertical aspect ratio {aspect_ratio}. {engine_cues}. "
        f"Hyper-detailed, authentic human expressions, subtle cloth physics, cinematic atmosphere."
    )

    return {
        "raw_idea": raw_idea,
        "target_engine": target_engine,
        "aspect_ratio": aspect_ratio,
        "optimized_prompt": enhanced_prompt,
        "camera_motion": selected_motion,
        "lighting": selected_lighting,
        "character_lock": character_lock_token or "",
        "negative_prompt": NEGATIVE_PROMPTS,
        "suggested_duration_seconds": 8 if target_engine == "google_flow" else 10
    }


def generate_drama_series(
    genre_key: str,
    custom_title: Optional[str] = None,
    total_episodes: int = 5,
    custom_notes: str = "",
    character_lock_token: Optional[str] = None,
    voice_tone_key: str = "dramatic_intense",
    visual_tone_key: str = "cinematic_35mm"
) -> Dict[str, Any]:
    title = custom_title.strip() if custom_title else "ศึกตระกูลหมื่นล้าน"
    vtone = next((v for v in VISUAL_TONES if v["key"] == visual_tone_key), VISUAL_TONES[0])
    voice = next((v for v in VOICE_TONES if v["key"] == voice_tone_key), VOICE_TONES[2])
    c_token = character_lock_token or build_character_lock_token("ภัทร (Phat)", gender="male", age=28)

    # Attempt Live Gemini AI Screenwriter
    ai_drama = _call_gemini_json(
        system_prompt=(
            "คุณคือผู้กำกับและนักเขียนบทซีรีส์ละครสั้น (Micro-Drama / ละครคุณธรรม) อันดับหนึ่งของไทย "
            "จงสร้างโครงเรื่องและบทละครสั้นที่มีความขัดแย้งเข้มข้น คำพูดเชือดเฉือน และจุดหักมุมทิ้งท้ายตอนแบบหยุดดูไม่ได้ "
            "ตอบกลับเป็น JSON ภาษาไทยที่มีคีย์ดังนี้: "
            "{'title': 'ชื่อเรื่อง', 'genre': 'แนวละคร', 'synopsis': 'เรื่องย่อสั้นๆ', "
            "'characters': [{'name': 'ชื่อ', 'role': 'บทบาท', 'personality': 'ลักษณะนิสัย'}], "
            "'episodes': [{'episode_number': 1, 'episode_title': 'ชื่อตอน', 'viral_hook': 'คำพูดฮุคเปิดคลิป 3 วิแรก', "
            "'script_dialogue': 'บทพูดสั้นๆ เข้มข้น', 'cliffhanger': 'จุดหักมุมทิ้งท้ายตอน', 'video_prompt': 'Prompt ภาษาอังกฤษสำหรับ Veo/Meta AI'}]}"
        ),
        user_prompt=f"หมวดหมู่: {genre_key}, ชื่อเรื่องที่ต้องการ: {title}, จำนวนตอน: {total_episodes}, โน้ตเพิ่มเติม: {custom_notes}"
    )

    if ai_drama and "episodes" in ai_drama and len(ai_drama["episodes"]) > 0:
        # Inject Character Lock into AI video prompts
        for ep in ai_drama["episodes"]:
            if c_token not in ep.get("video_prompt", ""):
                ep["video_prompt"] = f"9:16 vertical video. {c_token}. {ep.get('video_prompt', '')}. {vtone['prompt_cue']}."
        return {
            "title": ai_drama.get("title", title),
            "genre": ai_drama.get("genre", "ดราม่าเชือดเฉือน"),
            "synopsis": ai_drama.get("synopsis", f"ซีรีส์สั้นดราม่าเข้มข้น '{title}'"),
            "characters": ai_drama.get("characters", [{"name": "ภัทร", "role": "ตัวเอก"}]),
            "character_lock": c_token,
            "voice_tone": voice,
            "visual_tone": vtone,
            "episodes": ai_drama["episodes"][:total_episodes]
        }

    characters = [
        {"name": "ภัทร", "role": "พระเอก (ตัวเอก)", "personality": "สุขุม ซ่อนความลับ ฉลาดเป็นกรด", "lock_token": c_token},
        {"name": "อริน", "role": "นางเอก", "personality": "จิตใจเข้มแข็ง กตัญญู ไม่ยอมก้มหัวให้ความอยุติธรรม"},
        {"name": "คุณหญิงดาริกา", "role": "ตัวร้าย (ผู้มีอิทธิพล)", "personality": "หยิ่งยโส มองคนด้วยเงินทอง"}
    ]

    episodes = []
    hooks = [
        "\"คนอย่างแก ไม่มีสิทธิ์แม้แต่จะเหยียบพรมของตึกนี้!\"",
        "\"แกคิดว่านามบัตรใบนี้จะช่วยชีวิตแกได้เหรอ?\"",
        "\"โทรศัพท์สายนี้... จะเปลี่ยนชีวิตแกไปตลอดกาล\"",
        "\"ถอยไปซะ ถ้าไม่อยากให้ตระกูลแกหมดตัวในชั่วข้ามคืน!\"",
        "\"ถึงเวลาเปิดหน้ากากแล้วสินะ... คุณผู้จัดการใหญ่!\""
    ]

    cliffhangers = [
        "เสียงซองเอกสารลับร่วงลงพื้น พร้อมภาพใบสั่งพักงานที่มีตราประทับสีแดงฉาน...",
        "สายตาคมกริบของภัทรจ้องตรงไปที่กล้องวงจรปิด พร้อมรอยยิ้มเยือกเย็น...",
        "โทรศัพท์ลึกลับดังขึ้น ปลายสายเอ่ยชื่อรหัสลับที่ทำให้ทุกคนหน้าซีดเผือด...",
        "ประตูห้องประชุมเปิดออก ชายสวมสูทหรูเดินเข้ามาพร้อมโค้งคำนับให้ภัทร..."
    ]

    for ep_num in range(1, total_episodes + 1):
        hook = hooks[(ep_num - 1) % len(hooks)]
        cliff = cliffhangers[(ep_num - 1) % len(cliffhangers)]
        ep_title = f"ตอนที่ {ep_num}: " + ("จุดเริ่มต้น" if ep_num == 1 else "ซ้อนกลล้างแค้น")

        prompt_scene = (
            f"Cinematic short drama 9:16 vertical video, Episode {ep_num} of '{title}'. {c_token}. "
            f"Scene: {hook}. Ultra-realistic Thai actors with intense facial expressions, "
            f"{vtone['prompt_cue']}, shallow depth of field, 24fps motion blur, "
            f"luxury boardroom setting, high emotional stakes, crisp filmic details."
        )

        episodes.append({
            "episode_number": ep_num,
            "episode_title": ep_title,
            "viral_hook": hook,
            "script_dialogue": f"[เสียงดนตรีระทึกขวัญ]\nตัวละคร: {hook}\nภัทร: (ยืนนิ่ง สายตาสงบเยือกเย็น) 'อย่าเพิ่งรีบตัดสินใจ ก่อนที่คุณจะได้เห็นสิ่งนี้'",
            "cliffhanger": cliff,
            "video_prompt": prompt_scene
        })

    return {
        "title": title,
        "genre": "ดราม่าลุ้นระทึก & เชือดเฉือน",
        "synopsis": f"เรื่องราวความแค้นและอำนาจมหาศาลที่ซ่อนอยู่ของ '{title}' สำหรับปล่อยบน TikTok / Reels",
        "characters": characters,
        "character_lock": c_token,
        "voice_tone": voice,
        "visual_tone": vtone,
        "episodes": episodes
    }


def generate_ugc_campaign(
    product_name: str,
    niche: str = "skincare",
    target_audience: str = "วัยทำงาน 20-35 ปี",
    hook_type: str = "problem_solution",
    creator_persona: str = "ครีเอเตอร์สายป้ายยา จริงใจ",
    character_lock_token: Optional[str] = None,
    voice_tone_key: str = "authentic_friendly",
    visual_tone_key: str = "natural_daylight"
) -> Dict[str, Any]:
    c_token = character_lock_token or build_character_lock_token("อริน (Arin)", gender="female", age=24)
    vtone = next((v for v in VISUAL_TONES if v["key"] == visual_tone_key), VISUAL_TONES[2])
    voice = next((v for v in VOICE_TONES if v["key"] == voice_tone_key), VOICE_TONES[0])

    # Attempt Live Gemini AI UGC Director
    ai_ugc = _call_gemini_json(
        system_prompt=(
            "คุณคือผู้กำกับคอนเทนต์และนักเขียนบท UGC (User Generated Content) ไวรัลบน TikTok และ Reels เบอร์หนึ่งของไทย "
            "จงสร้างแคมเปญ UGC ที่เน้นป้ายยาจริงใจ ไม่แข็งเป็นโฆษณา มีฮุค 3 วินาทีแรกที่หยุดนิ้วคนดู "
            "ตอบกลับเป็น JSON ภาษาไทยที่มีคีย์ดังนี้: "
            "{'hook_type': 'ชื่อประเภทฮุค', 'hook_text': 'คำพูดฮุค 3 วินาทีแรก', "
            "'spoken_script': [{'second': '0-3s', 'speaker': 'Creator', 'text': 'บทพูด', 'visual_action': 'ท่าทางและมุมกล้อง'}], "
            "'scene_prompts': [{'scene_number': 1, 'title': 'ชื่อช็อต', 'duration_sec': 4, 'camera_instruction': 'มุมกล้อง', 'prompt': 'Prompt อังกฤษสำหรับ Veo'}], "
            "'caption_hashtags': 'แคปชันและแฮชแท็กป้ายยา'}"
        ),
        user_prompt=f"สินค้า: {product_name}, หมวดหมู่: {niche}, กลุ่มเป้าหมาย: {target_audience}, สไตล์ฮุค: {hook_type}, โทนเสียง: {voice['name']}"
    )

    if ai_ugc and "spoken_script" in ai_ugc and len(ai_ugc["spoken_script"]) > 0:
        # Inject Character Lock into AI video scene prompts
        for sc in ai_ugc.get("scene_prompts", []):
            if c_token not in sc.get("prompt", ""):
                sc["prompt"] = f"Authentic UGC video, 9:16 vertical. {c_token}. {sc.get('prompt', '')}. {vtone['prompt_cue']}."

        return {
            "product_name": product_name,
            "niche": niche,
            "target_audience": target_audience,
            "hook_type": ai_ugc.get("hook_type", "ปัญหาเรื้อรัง → ทางออกเปลี่ยนชีวิต"),
            "creator_persona": creator_persona,
            "character_lock": c_token,
            "voice_tone": voice,
            "visual_tone": vtone,
            "spoken_script": ai_ugc["spoken_script"],
            "scene_prompts": ai_ugc.get("scene_prompts", []),
            "caption_hashtags": ai_ugc.get("caption_hashtags", f"ป้ายยาไอเทมเด็ด {product_name} #TikTokป้ายยา #ใช้ดีบอกต่อ")
        }

    hook_text = f"ถ้าใครกำลังเจอปัญหานี้ อย่าเพิ่งเลื่อนผ่านเด็ดขาด สำหรับคนที่อยากได้ {product_name}!"
    
    spoken_script = [
        {"second": "0-3s", "speaker": "Creator", "text": hook_text, "visual_action": "หน้ามองกล้องตรงๆ ถือสินค้าใกล้หน้า ทำหน้าตกใจ/ตื่นเต้น"},
        {"second": "3-7s", "speaker": "Creator", "text": f"ปกติเราเป็นคนที่เรื่องมากกับ {niche} มาก ลองมาเยอะจนถอดใจ แต่พอมาเจอตัวนี้...", "visual_action": "ซูมใกล้ให้เห็นปัญหาเดิม สลับกับหยิบสินค้าขึ้นมาโชว์"},
        {"second": "7-12s", "speaker": "Creator", "text": "ดูเนื้อเค้าสิทุกคน นุ่มละมุน ซึมไวมาก ไม่เหนียวเหนอะหนะเลย กลิ่นคือหอมพรีเมียมสุดๆ", "visual_action": "มุมมอง POV มือปาดเนื้อสัมผัส หรือสาธิตการใช้งานจริงแบบชัดๆ"},
        {"second": "12-16s", "speaker": "Creator", "text": "ใช้ต่อเนื่องมาแล้วรู้สึกได้เลยว่าต่างจริง มั่นใจขึ้นเยอะมาก คุ้มเกินราคาไปไกล", "visual_action": "ยิ้มสดใส ส่องกระจก โชว์ความพอใจกับผลลัพธ์แบบธรรมชาติ"},
        {"second": "16-20s", "speaker": "Creator", "text": "ใครอยากได้ แปะพิกัดพร้อมโค้ดลดไว้ที่ตะกร้าซ้ายมือด้านล่างแล้ว รีบกดก่อนของหมดนะ!", "visual_action": "ชี้มือไปที่มุมล่างซ้าย (จุดปักตะกร้า TikTok/Shopee) พร้อมรอยยิ้มป้ายยา"}
    ]

    scene_prompts = [
        {
            "scene_number": 1,
            "title": "Viral Hook - Face to Camera",
            "duration_sec": 4,
            "camera_instruction": "Front-facing iPhone camera, handheld subtle motion",
            "prompt": f"Authentic UGC video, 9:16 vertical. {c_token}. Holding {product_name} packaging close to the lens, shocked and excited facial expression, {vtone['prompt_cue']}."
        },
        {
            "scene_number": 2,
            "title": "POV Texture / Demonstration",
            "duration_sec": 5,
            "camera_instruction": "First-person POV macro lens, smooth focus pull",
            "prompt": f"Close-up first person POV hands gently demonstrating {product_name}, clean aesthetic background, {vtone['prompt_cue']}, 9:16 vertical."
        },
        {
            "scene_number": 3,
            "title": "Satisfied Reaction & CTA",
            "duration_sec": 4,
            "camera_instruction": "Medium close-up, smiling pointing to bottom left corner",
            "prompt": f"Authentic UGC creator smiling warmly, {c_token}, glowing radiant face, pointing down towards bottom left, {vtone['prompt_cue']}."
        }
    ]

    return {
        "product_name": product_name,
        "niche": niche,
        "target_audience": target_audience,
        "hook_type": "ปัญหาเรื้อรัง → ทางออกเปลี่ยนชีวิต",
        "creator_persona": creator_persona,
        "character_lock": c_token,
        "voice_tone": voice,
        "visual_tone": vtone,
        "spoken_script": spoken_script,
        "scene_prompts": scene_prompts,
        "caption_hashtags": f"ป้ายยาไอเทมเด็ด {product_name} ที่ทุกคนต้องมี! ใช้ดีจนต้องบอกต่อ ✨ #TikTokป้ายยา #รีวิวของดี #ใช้ดีบอกต่อ #{niche.replace(' ', '')}"
    }
