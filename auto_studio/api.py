"""FastAPI Web & Desktop API Service for Auto Studio Pro.
Coordinates the Dashboard, Drama AI, UGC, Prompt Assistant, Queue Worker,
Calendar Planner, and Video Streaming.
"""
from __future__ import annotations
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auto_studio import db
from auto_studio.calendar_service import generate_content_plan, queue_all_calendar_events
from auto_studio.engines.video_renderer import OUTPUT_DIR, THUMB_DIR, render_preview_video
from auto_studio.prompt_engine import (
    CAMERA_MOTIONS,
    LIGHTING_STYLES,
    VOICE_TONES,
    VISUAL_TONES,
    GENDERS,
    CHARACTER_PRESETS,
    TEMPLATES_30,
    build_character_lock_token,
    generate_storyboard,
    generate_drama_series,
    generate_ugc_campaign,
    optimize_prompt
)
from auto_studio.queue_worker import is_worker_running, start_worker, stop_worker

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI Studio Pro — Auto Gen & Video Creator",
    description="High-converting Drama AI, UGC Creator, Meta AI & Google Flow Automation with Queue & Calendar",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount video output and static folders
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Start worker automatically on launch
@app.on_event("startup")
def on_startup():
    db.init_db()
    if not os.environ.get("VERCEL"):
        start_worker()


# -------------------------------------------------------------
# Request Models
# -------------------------------------------------------------
class OptimizePromptRequest(BaseModel):
    raw_idea: str
    target_engine: str = "google_flow"
    aspect_ratio: str = "9:16"
    style_preference: Optional[str] = None
    camera_motion: Optional[str] = None
    lighting: Optional[str] = None


class DramaGenerateRequest(BaseModel):
    genre_key: str = "revenge_wealth"
    custom_title: Optional[str] = None
    total_episodes: int = 5
    custom_notes: str = ""


class UGCGenerateRequest(BaseModel):
    product_name: str
    niche: str = "skincare"
    target_audience: str = "วัยทำงาน 20-35 ปี"
    hook_type: str = "problem_solution"
    creator_persona: str = "ครีเอเตอร์สายป้ายยา จริงใจ"


class CreateJobRequest(BaseModel):
    task_type: str = "custom"
    title: str
    prompt: str
    engine: str = "google_flow"
    aspect_ratio: str = "9:16"
    priority: int = 3
    calendar_id: Optional[int] = None


class CalendarPlanRequest(BaseModel):
    campaign_type: str = "drama"  # 'drama' or 'ugc'
    topic_or_product: str
    days_count: int = 7
    start_date: Optional[str] = None
    preferred_time: str = "19:00"
    channel: str = "tiktok"
    engine: str = "google_flow"
    auto_gen: bool = True


class CalendarAddRequest(BaseModel):
    title: str
    event_type: str
    scheduled_date: str
    scheduled_time: str
    channel: str = "tiktok"
    prompt_idea: str
    full_prompt: str = ""
    engine: str = "google_flow"
    auto_gen: bool = True


class StoryboardGenerateRequest(BaseModel):
    topic_or_product: str
    template_id: Optional[str] = None
    campaign_type: str = "ugc"
    gender: str = "female"
    voice_tone_key: str = "authentic_friendly"
    visual_tone_key: str = "natural_daylight"
    character_name: Optional[str] = None
    total_scenes: int = 4


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]


class MetaCookieRequest(BaseModel):
    cookies: str


# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------

# 1. Dashboard & Worker
@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    all_jobs = db.list_jobs(limit=100)
    queued_count = sum(1 for j in all_jobs if j["status"] == "queued")
    running_count = sum(1 for j in all_jobs if j["status"] in ("prompt_crafting", "dispatching", "rendering", "downloading"))
    completed_count = sum(1 for j in all_jobs if j["status"] == "completed")
    failed_count = sum(1 for j in all_jobs if j["status"] == "failed")
    
    cal_events = db.list_calendar_events()
    scheduled_cal_count = sum(1 for c in cal_events if c["status"] == "scheduled")

    return {
        "status": "online",
        "worker_running": is_worker_running(),
        "queued_jobs": queued_count,
        "running_jobs": running_count,
        "completed_jobs": completed_count,
        "failed_jobs": failed_count,
        "calendar_scheduled": scheduled_cal_count,
        "default_engine": db.get_setting("default_engine", "google_flow"),
        "simulation_mode": db.get_setting("simulation_mode", "true").lower() == "true",
        "auto_worker_enabled": db.get_setting("auto_worker_enabled", "true").lower() == "true",
        "recent_jobs": all_jobs[:8]
    }


@app.post("/api/worker/toggle")
def toggle_worker():
    curr = db.get_setting("auto_worker_enabled", "true").lower() == "true"
    new_state = not curr
    db.set_setting("auto_worker_enabled", "true" if new_state else "false")
    if new_state and not is_worker_running():
        start_worker()
    return {"auto_worker_enabled": new_state, "worker_running": is_worker_running()}


# 2. Queue Management & Live Workflow
@app.get("/api/queue")
def get_queue(limit: int = 50, status: Optional[str] = None):
    jobs = db.list_jobs(limit=limit, status=status)
    for j in jobs:
        try:
            j["logs"] = json.loads(j.get("logs") or "[]")
        except Exception:
            j["logs"] = []
    return {"jobs": jobs}


@app.get("/api/queue/{job_id}")
def get_queue_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        job["logs"] = json.loads(job.get("logs") or "[]")
    except Exception:
        job["logs"] = []
    return job


@app.post("/api/queue")
def create_queue_job(req: CreateJobRequest):
    job_id = db.add_job(
        task_type=req.task_type,
        title=req.title,
        prompt=req.prompt,
        engine=req.engine,
        aspect_ratio=req.aspect_ratio,
        priority=req.priority,
        calendar_id=req.calendar_id
    )
    return {"success": True, "job_id": job_id}


@app.delete("/api/queue/{job_id}")
def delete_queue_job(job_id: int):
    success = db.delete_job(job_id)
    return {"success": success}


@app.post("/api/queue/{job_id}/retry")
def retry_queue_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.update_job_stage(job_id, "queued", 0, "Retried by user", error_message="")
    return {"success": True}


# 3. Templates & Character Lock System (30 Templates)
@app.get("/api/templates/all")
def api_get_all_templates():
    return {"templates": TEMPLATES_30, "total": len(TEMPLATES_30)}


@app.get("/api/character-lock/options")
def api_get_character_lock_options():
    return {
        "genders": GENDERS,
        "voice_tones": VOICE_TONES,
        "visual_tones": VISUAL_TONES,
        "character_presets": CHARACTER_PRESETS,
        "camera_motions": CAMERA_MOTIONS,
        "lighting_styles": LIGHTING_STYLES
    }


@app.post("/api/storyboard/generate")
def api_generate_storyboard(req: StoryboardGenerateRequest):
    return generate_storyboard(
        topic_or_product=req.topic_or_product,
        template_id=req.template_id,
        campaign_type=req.campaign_type,
        gender=req.gender,
        voice_tone_key=req.voice_tone_key,
        visual_tone_key=req.visual_tone_key,
        character_name=req.character_name,
        total_scenes=req.total_scenes
    )


# 4. Prompt Studio ("ช่วยคิด Prompt")
@app.post("/api/prompt/optimize")
def api_optimize_prompt(req: OptimizePromptRequest):
    result = optimize_prompt(
        raw_idea=req.raw_idea,
        target_engine=req.target_engine,
        aspect_ratio=req.aspect_ratio,
        style_preference=req.style_preference,
        camera_motion=req.camera_motion,
        lighting=req.lighting
    )
    return result


@app.get("/api/prompt/options")
def get_prompt_options():
    return {
        "camera_motions": CAMERA_MOTIONS,
        "lighting_styles": LIGHTING_STYLES,
        "voice_tones": VOICE_TONES,
        "visual_tones": VISUAL_TONES,
        "genders": GENDERS,
        "character_presets": CHARACTER_PRESETS,
        "ugc_templates": UGC_TEMPLATES
    }


# 4. Drama AI Studio
@app.post("/api/drama/generate")
def api_generate_drama(req: DramaGenerateRequest):
    result = generate_drama_series(
        genre_key=req.genre_key,
        custom_title=req.custom_title,
        total_episodes=req.total_episodes,
        custom_notes=req.custom_notes
    )
    return result


@app.post("/api/drama/save")
def api_save_drama(data: Dict[str, Any]):
    series_id = db.save_drama_series(
        title=data.get("title", "ละครสั้น"),
        genre=data.get("genre", "ดราม่า"),
        synopsis=data.get("synopsis", ""),
        characters=data.get("characters", []),
        episodes=data.get("episodes", [])
    )
    return {"success": True, "series_id": series_id}


@app.get("/api/drama/list")
def api_list_drama():
    return {"series": db.list_drama_series()}


@app.post("/api/drama/queue-episode")
def api_queue_drama_episode(data: Dict[str, Any]):
    title = data.get("title", "Drama Episode")
    prompt = data.get("prompt", "")
    engine = data.get("engine", "google_flow")
    job_id = db.add_job(
        task_type="drama",
        title=title,
        prompt=prompt,
        engine=engine,
        aspect_ratio="9:16"
    )
    return {"success": True, "job_id": job_id}


# 5. UGC Creator Studio
@app.post("/api/ugc/generate")
def api_generate_ugc(req: UGCGenerateRequest):
    result = generate_ugc_campaign(
        product_name=req.product_name,
        niche=req.niche,
        target_audience=req.target_audience,
        hook_type=req.hook_type,
        creator_persona=req.creator_persona
    )
    return result


@app.post("/api/ugc/save")
def api_save_ugc(data: Dict[str, Any]):
    camp_id = db.save_ugc_campaign(
        product_name=data.get("product_name", "สินค้า"),
        niche=data.get("niche", "general"),
        target_audience=data.get("target_audience", ""),
        hook_type=data.get("hook_type", ""),
        creator_persona=data.get("creator_persona", ""),
        script_lines=data.get("spoken_script", []),
        scene_prompts=data.get("scene_prompts", [])
    )
    return {"success": True, "campaign_id": camp_id}


@app.get("/api/ugc/list")
def api_list_ugc():
    return {"campaigns": db.list_ugc_campaigns()}


@app.post("/api/ugc/queue-scene")
def api_queue_ugc_scene(data: Dict[str, Any]):
    title = data.get("title", "UGC Video")
    prompt = data.get("prompt", "")
    engine = data.get("engine", "google_flow")
    job_id = db.add_job(
        task_type="ugc",
        title=title,
        prompt=prompt,
        engine=engine,
        aspect_ratio="9:16"
    )
    return {"success": True, "job_id": job_id}


# 6. Calendar & Content Planner
@app.get("/api/calendar/events")
def api_get_calendar_events(date_from: Optional[str] = None, date_to: Optional[str] = None):
    events = db.list_calendar_events(date_from, date_to)
    return {"events": events}


@app.post("/api/calendar/plan")
def api_generate_calendar_plan(req: CalendarPlanRequest):
    plan_items = generate_content_plan(
        campaign_type=req.campaign_type,
        topic_or_product=req.topic_or_product,
        days_count=req.days_count,
        start_date=req.start_date,
        preferred_time=req.preferred_time,
        channel=req.channel,
        engine=req.engine,
        auto_gen=req.auto_gen
    )
    return {"success": True, "count": len(plan_items), "plan": plan_items}


@app.post("/api/calendar/add")
def api_add_calendar_event(req: CalendarAddRequest):
    ev_id = db.add_calendar_event(
        title=req.title,
        event_type=req.event_type,
        scheduled_date=req.scheduled_date,
        scheduled_time=req.scheduled_time,
        channel=req.channel,
        prompt_idea=req.prompt_idea,
        full_prompt=req.full_prompt,
        engine=req.engine,
        auto_gen=req.auto_gen
    )
    return {"success": True, "event_id": ev_id}


@app.delete("/api/calendar/{event_id}")
def api_delete_calendar_event(event_id: int):
    success = db.delete_calendar_event(event_id)
    return {"success": success}


@app.post("/api/calendar/queue-now")
def api_queue_calendar_now(data: Dict[str, Any]):
    ids = data.get("event_ids", [])
    if not ids:
        # If no specific IDs passed, queue all pending scheduled events
        all_events = db.list_calendar_events()
        ids = [e["id"] for e in all_events if e["status"] == "scheduled"]
    job_ids = queue_all_calendar_events(ids)
    return {"success": True, "queued_jobs": job_ids}


# 7. Settings & Testing
@app.get("/api/settings")
def api_get_settings():
    s = db.get_all_settings()
    # Mask secret keys for UI safety
    masked = dict(s)
    if masked.get("gemini_api_key"):
        val = masked["gemini_api_key"]
        masked["gemini_api_key"] = val[:4] + "••••••••" + val[-4:] if len(val) > 8 else "••••••••"
    if masked.get("meta_ai_token"):
        val = masked["meta_ai_token"]
        masked["meta_ai_token"] = val[:4] + "••••••••" + val[-4:] if len(val) > 8 else "••••••••"
    if masked.get("meta_ai_cookies"):
        val = masked["meta_ai_cookies"]
        masked["meta_ai_cookies"] = val[:6] + "••••••••" if len(val) > 10 else "••••••••"
    return {"settings": masked}


# Meta AI Cookie Integration Endpoints
@app.post("/api/meta/upload-cookie-file")
async def api_upload_meta_cookie_file(file: UploadFile = File(...)):
    from auto_studio.engines.meta_ai import parse_meta_cookies, verify_meta_cookies
    try:
        content = await file.read()
        raw_text = content.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถอ่านไฟล์ได้: {str(e)}")

    cookies = parse_meta_cookies(raw_text)
    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="ไม่สามารถอ่านค่า Cookie จากไฟล์นี้ได้ โปรดใช้ไฟล์ .json ที่ Export จาก Cookie-Editor หรือ .txt จากเบราว์เซอร์"
        )

    db.set_setting("meta_ai_cookies", raw_text)
    verification = verify_meta_cookies(raw_text)
    return {
        "success": True,
        "filename": file.filename,
        "cookies_count": len(cookies),
        "keys": [c["name"] for c in cookies[:8]],
        "verification": verification
    }


@app.post("/api/meta/verify-cookies")
def api_verify_meta_cookies(req: MetaCookieRequest):
    from auto_studio.engines.meta_ai import verify_meta_cookies
    return verify_meta_cookies(req.cookies)


@app.post("/api/meta/save-cookies")
def api_save_meta_cookies(req: MetaCookieRequest):
    from auto_studio.engines.meta_ai import parse_meta_cookies, verify_meta_cookies
    cookies = parse_meta_cookies(req.cookies)
    if not cookies:
        raise HTTPException(status_code=400, detail="รูปแบบ Cookie ไม่ถูกต้อง โปรดใส่คุกกี้ที่คัดลอกมาจาก meta.ai")
    db.set_setting("meta_ai_cookies", req.cookies)
    verification = verify_meta_cookies(req.cookies)
    return {"success": True, "verification": verification}


@app.get("/api/meta/status")
def api_get_meta_status():
    raw = db.get_setting("meta_ai_cookies")
    from auto_studio.engines.meta_ai import parse_meta_cookies
    parsed = parse_meta_cookies(raw)
    return {
        "has_cookies": len(parsed) > 0,
        "cookies_count": len(parsed),
        "keys": [c["name"] for c in parsed[:6]]
    }


@app.post("/api/settings")
def api_update_settings(req: SettingsUpdateRequest):
    for k, v in req.settings.items():
        # Do not overwrite with masked values
        if "••••" in v:
            continue
        db.set_setting(k, v)
    return {"success": True}


@app.post("/api/test/generate-sample")
def api_generate_sample(engine: str = "google_flow"):
    job_id = db.add_job(
        task_type="drama" if engine == "google_flow" else "ugc",
        title=f"Sample Video Test ({engine})",
        prompt=f"Cinematic ultra-realistic 9:16 vertical test sequence rendered via {engine}.",
        engine=engine,
        aspect_ratio="9:16",
        priority=1
    )
    return {"success": True, "job_id": job_id}


# 8. Web Interface
@app.get("/")
def serve_ui():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>AI Studio Pro API is Running</h1>")
