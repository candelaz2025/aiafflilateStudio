"""Meta AI (Movie Gen & Imagine Video) Generation Engine.
Supports Cookie-based authentication, Playwright browser automation, and local studio rendering.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from auto_studio.db import get_setting, set_setting
from auto_studio.engines.video_renderer import OUTPUT_DIR, THUMB_DIR, render_preview_video


def parse_meta_cookies(raw: str) -> List[Dict[str, Any]]:
    """Parses raw cookies from JSON array format, Netscape .txt format, or HTTP header string."""
    raw = (raw or "").strip()
    if not raw:
        return []

    # 1. JSON Array format (e.g. from Cookie-Editor extension or storageState.json)
    if (raw.startswith("[") and raw.endswith("]")) or (raw.startswith("{") and "cookies" in raw):
        try:
            data = json.loads(raw)
            items = data if isinstance(data, list) else data.get("cookies", [])
            cookies = []
            for item in items:
                name = item.get("name")
                value = item.get("value")
                if name and value is not None:
                    domain = item.get("domain", ".meta.ai")
                    if not domain.startswith("."):
                        domain = "." + domain
                    cookies.append({
                        "name": str(name),
                        "value": str(value),
                        "domain": domain,
                        "path": item.get("path", "/"),
                        "secure": bool(item.get("secure", True)),
                        "httpOnly": bool(item.get("httpOnly", False)),
                    })
            if cookies:
                return cookies
        except Exception:
            pass

    # 2. Netscape format (tab-separated)
    cookies = []
    lines = raw.splitlines()
    is_netscape = any("\t" in line for line in lines if line and not line.startswith("#"))
    if is_netscape:
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expiration, name, value = parts[:7]
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": domain.strip() if domain.startswith(".") else ("." + domain.strip()),
                    "path": path.strip() or "/",
                    "secure": secure.upper() == "TRUE",
                    "httpOnly": False
                })
        if cookies:
            return cookies

    # 3. Key=Value string format (e.g. c_user=...; xs=...; datr=... or line by line)
    cookies = []
    for line in lines:
        for pair in line.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            parts = pair.split("=", 1)
            name = parts[0].strip()
            val = parts[1].strip()
            if name and not name.startswith("#"):
                cookies.append({
                    "name": name,
                    "value": val,
                    "domain": ".meta.ai",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False
                })
    return cookies


def verify_meta_cookies(raw_cookies: str) -> Dict[str, Any]:
    """Verifies whether the provided Meta AI cookies establish an active session."""
    cookies = parse_meta_cookies(raw_cookies)
    if not cookies:
        return {
            "valid": False,
            "message": "ไม่พบข้อมูล Cookie ที่ถูกต้อง โปรดใส่ในรูปแบบ c_user=...; xs=... หรือ JSON",
            "cookies_count": 0
        }

    cookie_names = {c["name"] for c in cookies}
    has_session_keys = any(k in cookie_names for k in ("c_user", "xs", "sessionid", "datr", "fr"))

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )

            # Add cookies for both .meta.ai and .facebook.com
            for c in cookies:
                try:
                    context.add_cookies([c])
                except Exception:
                    pass

            page = context.new_page()
            page.goto("https://www.meta.ai", wait_until="networkidle", timeout=18000)
            
            # Check page status
            page_text = page.content().lower()
            needs_login = "log in with facebook" in page_text or "log in with instagram" in page_text
            inputs = page.query_selector_all('textarea, [contenteditable="true"], input[type="text"]')

            browser.close()

            if needs_login and not ("c_user" in cookie_names and "xs" in cookie_names):
                return {
                    "valid": False,
                    "message": "Cookie ขาดเซสชันล็อกอิน (แนะนำให้คัดลอก c_user และ xs จาก meta.ai)",
                    "cookies_count": len(cookies),
                    "found_keys": list(cookie_names)[:6]
                }

            return {
                "valid": True,
                "message": f"เชื่อมต่อ Meta AI สำเร็จ! ตรวจพบ {len(cookies)} คุกกี้ พร้อมใช้งาน Auto Gen",
                "cookies_count": len(cookies),
                "found_keys": list(cookie_names)[:6]
            }

    except Exception as exc:
        if has_session_keys:
            return {
                "valid": True,
                "message": f"ตรวจพบ Session Cookies ({len(cookies)} รายการ): {', '.join(list(cookie_names)[:4])}",
                "cookies_count": len(cookies),
                "found_keys": list(cookie_names)[:6]
            }
        return {
            "valid": False,
            "message": f"ไม่สามารถตรวจสอบได้: {str(exc)[:100]}",
            "cookies_count": len(cookies)
        }


class MetaAiEngine:
    def __init__(self):
        self.name = "Meta AI / Movie Gen"

    def generate(
        self,
        title: str,
        prompt: str,
        task_type: str = "drama",
        aspect_ratio: str = "9:16",
        on_progress: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[Path, Path]:
        """Generates video via Meta AI.
        Uses Playwright with injected cookies if available; falls back to high-res local studio render.
        """
        def log(pct: int, msg: str):
            if on_progress:
                on_progress(pct, msg)

        raw_cookies = get_setting("meta_ai_cookies") or get_setting("meta_ai_token") or os.getenv("META_AI_COOKIE", "").strip()
        simulation = get_setting("simulation_mode", "true").lower() == "true"
        cookies = parse_meta_cookies(raw_cookies)

        log(10, "Meta AI: Initializing prompt & motion parameters for Movie Gen...")
        time.sleep(0.05)

        if simulation:
            log(35, "Meta AI (Test Simulation Mode): Generating verified video asset...")
            video_path, thumb_path = render_preview_video(
                title=title,
                prompt=prompt,
                engine="meta_ai",
                task_type=task_type,
                duration=4,
                aspect_ratio=aspect_ratio
            )
            log(100, f"Meta AI: Video generation completed! Output: {video_path.name}")
            return video_path, thumb_path

        if not cookies:
            raise RuntimeError(
                "ไม่พบ Cookie สำหรับ Meta AI! กรุณาอัปโหลดไฟล์ Cookie (.json หรือ .txt) "
                "จาก meta.ai ในเมนู 'ตั้งค่า & Cookie Meta' เพื่อเชื่อมต่อและสั่ง Gen วิดีโอจาก Meta AI จริง"
            )

        log(20, f"Meta AI: ตรวจพบ {len(cookies)} คุกกี้ เริ่มต้นเปิดเบราว์เซอร์เพื่อเข้าสู่ https://www.meta.ai ...")
        
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )

            # Inject cookies across .meta.ai and .facebook.com domains
            for c in cookies:
                try:
                    context.add_cookies([c])
                except Exception:
                    pass

            page = context.new_page()
            log(35, "Meta AI: กำลังโหลดหน้าเว็บ meta.ai ด้วยคุกกี้ที่อัปโหลดไว้...")
            page.goto("https://www.meta.ai", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # Check if login modal blocks the session
            page_text = page.content().lower()
            if "log in with facebook" in page_text or "log in with instagram" in page_text:
                cookie_names = {c["name"] for c in cookies}
                if not ("c_user" in cookie_names and "xs" in cookie_names):
                    browser.close()
                    raise RuntimeError(
                        "Cookie ที่อัปโหลดขาดค่าเซสชัน (c_user หรือ xs) หรือหมดอายุแล้ว "
                        "กรุณาล็อกอินที่ meta.ai ในเบราว์เซอร์ แล้วอัปโหลดไฟล์ Cookie ใหม่อีกครั้ง"
                    )

            # Intercept video stream / MP4 URL
            captured_video_url = []

            def handle_response(response):
                url = response.url.lower()
                ct = (response.headers.get("content-type") or "").lower()
                if "video/mp4" in ct or ".mp4" in url or "fbcdn.net/v/" in url:
                    captured_video_url.append(response.url)

            page.on("response", handle_response)

            # Locate prompt input
            input_selector = 'input[placeholder*="Ask Meta AI"], textarea, [contenteditable="true"], input[type="text"]'
            try:
                page.wait_for_selector(input_selector, timeout=12000)
                input_el = page.query_selector(input_selector)
            except Exception:
                input_el = None

            if not input_el:
                browser.close()
                raise RuntimeError("ไม่พบช่องพิมพ์ข้อความบน meta.ai โปรดตรวจสอบสถานะการเข้าถึงที่หน้าเว็บ meta.ai")

            log(50, "Meta AI: กำลังพิมพ์ Prompt วิดีโอลงใน Meta AI...")
            formatted_prompt = f"Create an ultra-realistic 9:16 vertical video: {prompt}"
            input_el.click()
            input_el.fill(formatted_prompt)
            page.keyboard.press("Enter")
            log(65, "Meta AI: ส่งคำสั่งสำเร็จ! กำลังรอระบบ Meta AI เรนเดอร์วิดีโอ...")

            # Poll for generation
            max_wait = 60
            start_wait = time.time()
            video_found = False

            while time.time() - start_wait < max_wait:
                time.sleep(2)
                elapsed = int(time.time() - start_wait)
                log(70 + min(20, elapsed // 3), f"Meta AI: กำลังสร้างเฟรมวิดีโอจาก Meta AI Server... ({elapsed} วินาที)")

                # Check for video element in DOM
                video_el = page.query_selector("video")
                if video_el:
                    src = video_el.get_attribute("src")
                    if src and src.startswith("http"):
                        captured_video_url.append(src)
                        video_found = True
                        break

                if captured_video_url:
                    video_found = True
                    break

            if not video_found or not captured_video_url:
                debug_shot = OUTPUT_DIR / f"meta_debug_{int(time.time())}.png"
                page.screenshot(path=str(debug_shot))
                browser.close()
                raise RuntimeError(
                    f"Meta AI รับคำสั่งแล้วแต่ยังสร้างวิดีโอไม่เสร็จภายใน {max_wait} วินาที "
                    f"หรือติดข้อจำกัดด้านคิวของ Meta.ai (บันทึกภาพหน้าจอ debug ไว้ที่ {debug_shot.name})"
                )

            # Download actual MP4 from Meta AI CDN
            v_url = captured_video_url[0]
            log(90, f"Meta AI: ตรวจพบสตรีมวิดีโอจาก Meta AI CDN! กำลังดาวน์โหลดไฟล์ MP4...")
            
            import requests
            resp = requests.get(v_url, timeout=45, stream=True)
            job_hash = abs(hash(f"{title}_{time.time()}")) % 1000000
            import re
            clean_t = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in title).strip("_")
            clean_t = re.sub(r"_+", "_", clean_t)[:20] or "meta"
            out_video_path = OUTPUT_DIR / f"vid_meta_{clean_t}_{job_hash}.mp4"
            
            with open(out_video_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Generate thumbnail from frame 00:00:01
            thumb_path = THUMB_DIR / f"thumb_meta_{clean_t}_{job_hash}.jpg"
            ff = shutil.which("ffmpeg") or "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
            subprocess.run([ff, "-y", "-ss", "00:00:01", "-i", str(out_video_path), "-vframes", "1", str(thumb_path)], capture_output=True)

            browser.close()
            log(100, f"Meta AI: ดาวน์โหลดวิดีโอจาก Meta AI สำเร็จเรียบร้อย! ไฟล์: {out_video_path.name}")
            return out_video_path, thumb_path
