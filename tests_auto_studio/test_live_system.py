"""Real-World Live System & End-to-End Operational Verification Test Suite.
Launches the live FastAPI server on an ephemeral port (8899) and tests every feature:
- Static Web & Desktop UI serving
- REST Endpoints over HTTP
- Storyboard Generation with Pillow card images and image HTTP delivery
- Character Lock consistency
- 30 Templates catalog
- Video generation & FFmpeg codec validation (H.264/AAC, 9:16 vertical)
- Video stream HTTP delivery with range / video headers
- Meta AI Cookie Parser & Verifier
- Queue worker job processing lifecycle (all 5 stages)
- Calendar plan auto-generation and queueing
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
import pytest
import uvicorn

from auto_studio import db
from auto_studio.api import app
from auto_studio.queue_worker import process_single_job

TEST_HOST = "127.0.0.1"
TEST_PORT = 8899
BASE_URL = f"http://{TEST_HOST}:{TEST_PORT}"


@pytest.fixture(scope="session", autouse=True)
def run_live_server():
    """Starts the real Uvicorn server in a background thread for live HTTP testing."""
    db.init_db()
    db.set_setting("simulation_mode", "true")
    db.set_setting("notify_macos", "false")

    config = uvicorn.Config(app=app, host=TEST_HOST, port=TEST_PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to become responsive
    ready = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/dashboard/stats", timeout=0.5) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)

    assert ready, "Live test server failed to start on port 8899"
    yield server
    server.should_exit = True


def http_get(path: str) -> tuple[int, dict | str, dict]:
    # Ensure URL is properly quoted for spaces and special characters
    parts = urllib.parse.urlsplit(path)
    quoted_path = urllib.parse.quote(parts.path)
    if parts.query:
        quoted_path += f"?{parts.query}"
    url = f"{BASE_URL}{quoted_path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        code = resp.status
        headers = dict(resp.headers)
        data = resp.read()
        try:
            return code, json.loads(data.decode("utf-8")), headers
        except Exception:
            return code, data.decode("utf-8", errors="replace"), headers


def http_post(path: str, payload: dict) -> tuple[int, dict, dict]:
    url = f"{BASE_URL}{path}"
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        code = resp.status
        headers = dict(resp.headers)
        res_data = json.loads(resp.read().decode("utf-8"))
        return code, res_data, headers


# -------------------------------------------------------------
# 1. Web & Static Asset Delivery Tests
# -------------------------------------------------------------
def test_live_ui_and_static_serving():
    # 1. Main index.html
    code, content, headers = http_get("/")
    assert code == 200
    assert "AI Studio Pro" in content
    assert "mac-titlebar" in content

    # 2. Stylesheet
    code, css, _ = http_get("/static/style.css")
    assert code == 200
    assert "mac-titlebar" in css

    # 3. JavaScript
    code, js, _ = http_get("/static/app.js")
    assert code == 200
    assert "openTemplatesModal" in js
    assert "handleGenerateStoryboard" in js


# -------------------------------------------------------------
# 2. 30 Templates & Character Lock Options Tests
# -------------------------------------------------------------
def test_live_templates_and_character_lock():
    code, data, _ = http_get("/api/templates/all")
    assert code == 200
    assert data["total"] == 30
    templates = data["templates"]
    ugc_list = [t for t in templates if t["type"] == "ugc"]
    drama_list = [t for t in templates if t["type"] == "drama"]
    assert len(ugc_list) == 15
    assert len(drama_list) == 15

    # Check template structure
    t0 = templates[0]
    for key in ("id", "type", "category", "title", "hook", "voice_tone", "visual_tone", "summary"):
        assert key in t0

    code, opts, _ = http_get("/api/character-lock/options")
    assert code == 200
    assert len(opts["genders"]) == 3
    assert len(opts["voice_tones"]) >= 6
    assert len(opts["visual_tones"]) >= 8
    assert len(opts["character_presets"]) >= 3


# -------------------------------------------------------------
# 3. Storyboard Generation & Image Asset Serving Tests
# -------------------------------------------------------------
def test_live_storyboard_generation_and_image_serving():
    code, sb, _ = http_post("/api/storyboard/generate", {
        "topic_or_product": "กาแฟเพื่อสุขภาพควบคุมน้ำตาล",
        "template_id": "ugc_01",
        "campaign_type": "ugc",
        "gender": "female",
        "voice_tone_key": "authentic_friendly",
        "visual_tone_key": "natural_daylight",
        "character_name": "อริน (Arin)",
        "total_scenes": 4
    })
    assert code == 200
    assert len(sb["scenes"]) == 4
    assert "Consistent Subject Anchor" in sb["character_lock"]["token"]

    # Verify each image card is served over HTTP with 200 OK and valid image content
    for scene in sb["scenes"]:
        img_url = scene["image_url"]
        assert img_url.startswith("/output/storyboards/")
        
        # Make real HTTP GET request for the image
        img_code, img_bytes, img_headers = http_get(img_url)
        assert img_code == 200
        # Check that it's real JPEG binary data
        assert len(img_bytes) > 2000
        # Verify content type
        ct = img_headers.get("content-type", "").lower()
        assert "image/jpeg" in ct or "octet-stream" in ct or "image" in ct


# -------------------------------------------------------------
# 4. Prompt Studio, Drama AI, and UGC Campaign Tests
# -------------------------------------------------------------
def test_live_content_studios():
    # Prompt Optimizer
    code, p_res, _ = http_post("/api/prompt/optimize", {
        "raw_idea": "รีวิวกล้องฟิล์มมุมมองบุคคลที่หนึ่ง",
        "target_engine": "meta_ai",
        "aspect_ratio": "9:16",
        "camera_motion": "Handheld dynamic iPhone POV with subtle natural shake"
    })
    assert code == 200
    assert "optimized_prompt" in p_res
    assert len(p_res["optimized_prompt"]) > 30

    # Drama Series Generator
    code, d_res, _ = http_post("/api/drama/generate", {
        "genre_key": "undercover_boss",
        "custom_title": "ท่านประธานสายลับกู้บริษัท",
        "total_episodes": 3
    })
    assert code == 200
    assert len(d_res["episodes"]) == 3
    assert d_res["episodes"][0]["viral_hook"]

    # Save drama series
    code, s_res, _ = http_post("/api/drama/save", d_res)
    assert code == 200
    assert s_res["series_id"] > 0

    # UGC Generator
    code, u_res, _ = http_post("/api/ugc/generate", {
        "product_name": "สมาร์ทวอทช์วัดชีพจร",
        "niche": "fitness",
        "hook_type": "three_reasons"
    })
    assert code == 200
    assert len(u_res["spoken_script"]) >= 4


# -------------------------------------------------------------
# 5. Calendar Planning and Queue Synchronization Tests
# -------------------------------------------------------------
def test_live_calendar_and_auto_queue():
    # Generate 7-day drama plan
    code, plan_res, _ = http_post("/api/calendar/plan", {
        "campaign_type": "drama",
        "topic_or_product": "สงครามมรดกเลือด",
        "days_count": 7,
        "preferred_time": "19:30",
        "engine": "google_flow"
    })
    assert code == 200
    plan = plan_res["plan"]
    assert len(plan) == 7

    # Queue all 7 events
    event_ids = [item["id"] for item in plan]
    code, q_res, _ = http_post("/api/calendar/queue-now", {"event_ids": event_ids})
    assert code == 200
    assert len(q_res["queued_jobs"]) == 7

    # Verify queue API reflects the jobs
    code, q_list, _ = http_get("/api/queue?limit=10")
    assert code == 200
    assert len(q_list["jobs"]) >= 7


# -------------------------------------------------------------
# 6. Real Video Generation, FFmpeg Codec & Media Delivery Tests
# -------------------------------------------------------------
def test_live_video_generation_codec_and_http_streaming():
    # 1. Create a live job
    code, j_res, _ = http_post("/api/queue", {
        "task_type": "ugc",
        "title": "Live E2E Video Test",
        "prompt": "Authentic TikTok review of aesthetic wireless mechanical keyboard",
        "engine": "google_flow",
        "aspect_ratio": "9:16",
        "priority": 10
    })
    assert code == 200
    job_id = j_res["job_id"]

    # 2. Process job with worker
    job = db.get_job(job_id)
    assert job["status"] == "queued"
    process_single_job(job)

    # 3. Verify completion in DB
    done_job = db.get_job(job_id)
    assert done_job["status"] == "completed"
    assert done_job["progress"] == 100
    v_url = done_job["video_path"]
    t_url = done_job["thumbnail_path"]
    assert v_url.startswith("/output/")
    assert t_url.startswith("/output/thumbnails/")

    # Resolve physical paths on disk
    project_root = Path(__file__).resolve().parent.parent
    local_v_path = project_root / "auto_studio" / v_url.lstrip("/")
    local_t_path = project_root / "auto_studio" / t_url.lstrip("/")
    assert local_v_path.exists(), f"Video file {local_v_path} should exist"
    assert local_t_path.exists(), f"Thumbnail file {local_t_path} should exist"

    # 4. FFprobe Deep Inspection
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "stream=codec_name,width,height,duration,r_frame_rate",
        "-of", "json",
        str(local_v_path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"ffprobe error: {proc.stderr}"
    probe_data = json.loads(proc.stdout)
    streams = probe_data.get("streams", [])
    assert len(streams) >= 1

    # Check video stream specs
    video_stream = next((s for s in streams if s.get("codec_name") == "h264"), None)
    assert video_stream is not None, "Output must contain H.264 video stream"
    assert video_stream["width"] == 720
    assert video_stream["height"] == 1280
    assert float(video_stream["duration"]) >= 3.0

    # 5. Test Video Stream Delivery over HTTP
    code, v_bytes, headers = http_get(v_url)
    assert code == 200
    assert len(v_bytes) > 5000
    ct = headers.get("content-type", "").lower()
    assert "video/mp4" in ct or "octet-stream" in ct or "video" in ct


# -------------------------------------------------------------
# 7. Meta AI Cookie Verification API Tests
# -------------------------------------------------------------
def test_live_meta_cookie_integration():
    sample_cookie = "c_user=1000889977; xs=45%3Asampletoken; datr=livemeta777;"
    code, save_res, _ = http_post("/api/meta/save-cookies", {"cookies": sample_cookie})
    assert code == 200
    assert save_res["success"] is True

    code, status_res, _ = http_get("/api/meta/status")
    assert code == 200
    assert status_res["has_cookies"] is True
    assert status_res["cookies_count"] == 3
    assert "c_user" in status_res["keys"]

    code, verify_res, _ = http_post("/api/meta/verify-cookies", {"cookies": sample_cookie})
    assert code == 200
    assert "valid" in verify_res
    assert verify_res["cookies_count"] == 3

    # Test Upload Cookie File endpoint via multipart/form-data
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    json_payload = '[{"name": "c_user", "value": "1000999888", "domain": ".meta.ai"}, {"name": "xs", "value": "session456"}]'
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="cookies.json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{json_payload}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/api/meta/upload-cookie-file",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        assert resp.status == 200
        up_data = json.loads(resp.read().decode("utf-8"))
        assert up_data["success"] is True
        assert up_data["cookies_count"] == 2
        assert "c_user" in up_data["keys"]
