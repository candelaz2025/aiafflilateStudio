"""Comprehensive test suite for Auto Studio Pro.
Validates Database, Prompt Engine, Drama AI, UGC, Engines, Calendar Planner, and API routes.
"""
from __future__ import annotations
import os
import pytest
from starlette.testclient import TestClient

from auto_studio import db
from auto_studio.api import app
from auto_studio.calendar_service import generate_content_plan, queue_all_calendar_events
from auto_studio.engines.google_flow import GoogleFlowEngine
from auto_studio.engines.meta_ai import MetaAiEngine, parse_meta_cookies, verify_meta_cookies
from auto_studio.prompt_engine import (
    TEMPLATES_30,
    GENDERS,
    VOICE_TONES,
    VISUAL_TONES,
    CHARACTER_PRESETS,
    build_character_lock_token,
    generate_drama_series,
    generate_ugc_campaign,
    generate_storyboard,
    optimize_prompt
)
from auto_studio.queue_worker import process_single_job


@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()
    db.set_setting("simulation_mode", "true")
    db.set_setting("notify_macos", "false")  # silence desktop notifications during tests


def test_database_crud():
    # Settings
    db.set_setting("test_key", "test_val")
    assert db.get_setting("test_key") == "test_val"

    # Queue Jobs
    job_id = db.add_job(
        task_type="drama",
        title="Test Drama Episode",
        prompt="Dramatic confrontation scene in Bangkok penthouse",
        engine="google_flow"
    )
    assert job_id > 0
    job = db.get_job(job_id)
    assert job is not None
    assert job["title"] == "Test Drama Episode"
    assert job["status"] == "queued"

    # Stage update
    db.update_job_stage(job_id, "rendering", 50, "Rendering frames...")
    updated_job = db.get_job(job_id)
    assert updated_job["status"] == "rendering"
    assert updated_job["progress"] == 50

    # Calendar Events
    ev_id = db.add_calendar_event(
        title="Scheduled Drama Drop",
        event_type="drama",
        scheduled_date="2026-10-25",
        scheduled_time="19:00",
        prompt_idea="Grand opening reveal",
        auto_gen=True
    )
    assert ev_id > 0
    events = db.list_calendar_events()
    assert any(e["id"] == ev_id for e in events)


def test_prompt_optimizer():
    opt = optimize_prompt("สาวไทยทาครีมแล้วยิ้ม", target_engine="google_flow", aspect_ratio="9:16")
    assert "optimized_prompt" in opt
    assert "negative_prompt" in opt
    assert "camera_motion" in opt
    assert "lighting" in opt
    assert opt["target_engine"] == "google_flow"
    assert len(opt["optimized_prompt"]) > 20


def test_drama_ai_generator():
    drama = generate_drama_series(
        genre_key="revenge_wealth",
        custom_title="เศรษฐีพันล้านตัวจริง",
        total_episodes=3
    )
    assert drama["title"] == "เศรษฐีพันล้านตัวจริง"
    assert len(drama["episodes"]) == 3
    for ep in drama["episodes"]:
        assert "viral_hook" in ep
        assert "script_dialogue" in ep
        assert "cliffhanger" in ep
        assert "video_prompt" in ep
        assert len(ep["viral_hook"]) > 0


def test_ugc_ai_generator():
    ugc = generate_ugc_campaign(
        product_name="เซรั่มใบบัวบก",
        niche="skincare",
        hook_type="problem_solution"
    )
    assert ugc["product_name"] == "เซรั่มใบบัวบก"
    assert len(ugc["spoken_script"]) >= 4
    assert len(ugc["scene_prompts"]) >= 3
    for scene in ugc["scene_prompts"]:
        assert "prompt" in scene
        assert "camera_instruction" in scene


def test_google_flow_engine_generation():
    engine = GoogleFlowEngine()
    logs = []
    def on_prog(pct, msg):
        logs.append((pct, msg))

    video_path, thumb_path = engine.generate(
        title="Unit Test Veo Clip",
        prompt="A woman smiling in sunny cafe",
        task_type="ugc",
        aspect_ratio="9:16",
        on_progress=on_prog
    )
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 1000
    assert os.path.exists(thumb_path)
    assert len(logs) > 0


def test_meta_ai_engine_generation():
    engine = MetaAiEngine()
    logs = []
    def on_prog(pct, msg):
        logs.append((pct, msg))

    video_path, thumb_path = engine.generate(
        title="Unit Test Meta AI Clip",
        prompt="Moody neon street in Bangkok rain",
        task_type="drama",
        aspect_ratio="9:16",
        on_progress=on_prog
    )
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 1000
    assert os.path.exists(thumb_path)
    assert len(logs) > 0


def test_calendar_service_plan_generator():
    plan = generate_content_plan(
        campaign_type="drama",
        topic_or_product="ศึกสายเลือด",
        days_count=3,
        preferred_time="20:00",
        engine="google_flow"
    )
    assert len(plan) == 3
    assert plan[0]["engine"] == "google_flow"
    assert plan[0]["time"] == "20:00"

    # Queue all
    event_ids = [item["id"] for item in plan]
    queued_jobs = queue_all_calendar_events(event_ids)
    assert len(queued_jobs) == 3


def test_worker_job_processing():
    job_id = db.add_job(
        task_type="ugc",
        title="Worker Test Task",
        prompt="Authentic handheld review of wireless earbuds",
        engine="meta_ai"
    )
    job = db.get_job(job_id)
    assert job["status"] == "queued"

    process_single_job(job)

    completed_job = db.get_job(job_id)
    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 100
    assert completed_job["video_path"] != ""
    assert completed_job["thumbnail_path"] != ""


def test_api_endpoints():
    client = TestClient(app)

    # Dashboard Stats
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert "queued_jobs" in data
    assert "completed_jobs" in data

    # Prompt Optimize
    res = client.post("/api/prompt/optimize", json={"raw_idea": "ช็อตเด็ดเปิดกล่องของขวัญ", "target_engine": "google_flow"})
    assert res.status_code == 200
    assert "optimized_prompt" in res.json()

    # Drama Generate
    res = client.post("/api/drama/generate", json={"genre_key": "revenge_wealth", "total_episodes": 3})
    assert res.status_code == 200
    assert len(res.json()["episodes"]) == 3

    # UGC Generate
    res = client.post("/api/ugc/generate", json={"product_name": "แก้วน้ำอัจฉริยะ", "niche": "gadget"})
    assert res.status_code == 200
    assert "spoken_script" in res.json()

    # Queue API
    res = client.get("/api/queue")
    assert res.status_code == 200
    assert "jobs" in res.json()

    # Settings API
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert "settings" in res.json()


def test_meta_ai_cookie_parser_and_verification():
    # Test key=value string format
    raw_str = "c_user=1000987654; xs=38%3Axyz123; datr=abc_token;"
    cookies = parse_meta_cookies(raw_str)
    assert len(cookies) == 3
    names = {c["name"] for c in cookies}
    assert "c_user" in names
    assert "xs" in names
    assert "datr" in names

    # Test JSON array format (from Cookie-Editor extension)
    raw_json = '[{"name": "c_user", "value": "10001", "domain": ".meta.ai"}, {"name": "xs", "value": "xyz99"}]'
    cookies_json = parse_meta_cookies(raw_json)
    assert len(cookies_json) == 2
    assert cookies_json[0]["name"] == "c_user"
    assert cookies_json[0]["value"] == "10001"

    # Test Empty / Invalid
    assert parse_meta_cookies("") == []
    assert parse_meta_cookies("   ") == []

    # Verification function structure
    ver = verify_meta_cookies(raw_str)
    assert "valid" in ver
    assert "message" in ver
    assert "cookies_count" in ver
    assert ver["cookies_count"] == 3


def test_templates_30_and_character_lock():
    client = TestClient(app)

    # 1. 30 Templates API
    res = client.get("/api/templates/all")
    assert res.status_code == 200
    data = res.json()
    assert "templates" in data
    assert data["total"] == 30
    templates = data["templates"]
    ugc_templates = [t for t in templates if t["type"] == "ugc"]
    drama_templates = [t for t in templates if t["type"] == "drama"]
    assert len(ugc_templates) == 15
    assert len(drama_templates) == 15

    # 2. Character Lock Options API
    res = client.get("/api/character-lock/options")
    assert res.status_code == 200
    opts = res.json()
    assert len(opts["genders"]) >= 3
    assert len(opts["voice_tones"]) >= 6
    assert len(opts["visual_tones"]) >= 8
    assert len(opts["character_presets"]) >= 3

    # 3. Deterministic character token builder
    token = build_character_lock_token(
        name="อริน (Arin)",
        gender="female",
        age=24,
        role_or_outfit="signature modern aesthetic attire",
        distinct_feature="high-fidelity consistent facial identity"
    )
    assert "Consistent Subject Anchor" in token
    assert "อริน" in token
    assert "Thai woman" in token


def test_storyboard_generation_and_image_cards():
    client = TestClient(app)

    res = client.post("/api/storyboard/generate", json={
        "topic_or_product": "เซรั่มไฮยาหน้าฉ่ำ",
        "template_id": "ugc_01",
        "campaign_type": "ugc",
        "gender": "female",
        "voice_tone_key": "authentic_friendly",
        "visual_tone_key": "korean_aesthetic",
        "character_name": "อริน (Arin)",
        "total_scenes": 3
    })
    assert res.status_code == 200
    data = res.json()
    assert "character_lock" in data
    assert "scenes" in data
    assert len(data["scenes"]) == 3

    # Verify each scene contains script, camera shot, prompt, and image card
    for scene in data["scenes"]:
        assert "spoken_line" in scene
        assert "camera_shot" in scene
        assert "video_prompt" in scene
        assert "image_url" in scene
        assert scene["image_url"].startswith("/output/storyboards/")

        # Verify image card exists on disk
        card_rel = scene["image_url"].replace("/output/storyboards/", "")
        card_path = os.path.join("auto_studio", "output", "storyboards", card_rel)
        assert os.path.exists(card_path), f"Card file {card_path} should exist"
        assert os.path.getsize(card_path) > 1000


def test_meta_cookie_api_endpoints():
    client = TestClient(app)

    test_cookies = "c_user=1000555666; xs=42%3Asessionsecret; datr=browsercookie777;"
    # Save & Verify Cookies endpoint
    res = client.post("/api/meta/save-cookies", json={"cookies": test_cookies})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "verification" in data

    # Check Meta status endpoint
    res = client.get("/api/meta/status")
    assert res.status_code == 200
    status_data = res.json()
    assert status_data["has_cookies"] is True
    assert status_data["cookies_count"] == 3
    assert "c_user" in status_data["keys"]

