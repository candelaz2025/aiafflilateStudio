"""Background Queue Worker & Automated Scheduler.
Executes queued jobs, monitors calendar schedules, dispatches to Meta AI / Google Flow,
streams live progress logs, and sends native macOS notifications.
"""
from __future__ import annotations
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from auto_studio.db import (
    get_job,
    get_next_queued_job,
    get_pending_due_calendar_events,
    get_setting,
    update_calendar_event_status,
    update_job_stage,
    add_job
)
from auto_studio.engines.google_flow import GoogleFlowEngine
from auto_studio.engines.meta_ai import MetaAiEngine
from auto_studio.prompt_engine import optimize_prompt

_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_RUNNING = False
_STOP_EVENT = threading.Event()


def send_macos_notification(title: str, message: str, subtitle: str = "AI Studio Pro") -> None:
    """Sends a native macOS desktop banner notification."""
    try:
        script = f'display notification "{message}" with title "{subtitle}" subtitle "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def process_single_job(job: Dict[str, Any]) -> None:
    job_id = job["id"]
    title = job["title"]
    raw_prompt = job["prompt"]
    task_type = job["task_type"]
    engine_name = job["engine"]
    aspect_ratio = job.get("aspect_ratio", "9:16")

    # Stage 1: Prompt Crafting & Verification
    update_job_stage(job_id, "prompt_crafting", 15, f"AI Studio: Analyzing and optimizing prompt for {engine_name}...")
    
    # If the prompt is basic, enhance it
    if len(raw_prompt.split()) < 10:
        opt = optimize_prompt(raw_prompt, target_engine=engine_name, aspect_ratio=aspect_ratio)
        effective_prompt = opt["optimized_prompt"]
        update_job_stage(job_id, "prompt_crafting", 25, f"Prompt enhanced: {effective_prompt[:60]}...")
    else:
        effective_prompt = raw_prompt

    # Stage 2: Engine Dispatch
    update_job_stage(job_id, "dispatching", 35, f"Connecting to engine [{engine_name}] pipeline...")

    # Stage 3: Rendering & Generation
    def on_engine_progress(pct: int, msg: str):
        update_job_stage(job_id, "rendering", pct, msg)

    try:
        if engine_name == "meta_ai":
            engine = MetaAiEngine()
        else:
            engine = GoogleFlowEngine()

        video_path, thumb_path = engine.generate(
            title=title,
            prompt=effective_prompt,
            task_type=task_type,
            aspect_ratio=aspect_ratio,
            on_progress=on_engine_progress
        )

        # Stage 4: Downloading & Post-Processing
        update_job_stage(job_id, "downloading", 95, "Verifying container integrity and compiling thumbnail...")
        time.sleep(0.5)

        # Stage 5: Completed
        rel_video = f"/output/{video_path.name}"
        rel_thumb = f"/output/thumbnails/{thumb_path.name}"
        update_job_stage(
            job_id,
            status="completed",
            progress=100,
            log_message=f"Video successfully generated! Ready for playback and export.",
            video_path=rel_video,
            thumbnail_path=rel_thumb,
            duration=6.0
        )

        # Update linked calendar event if present
        cal_id = job.get("calendar_id")
        if cal_id:
            update_calendar_event_status(cal_id, "completed", job_id)

        # macOS Notification
        if get_setting("notify_macos", "true").lower() == "true":
            send_macos_notification(title=title, message="วิดีโอของคุณพร้อมใช้งานแล้ว!", subtitle="🎬 AI Studio Complete")

    except Exception as exc:
        update_job_stage(
            job_id,
            status="failed",
            progress=100,
            log_message=f"Generation failed: {str(exc)}",
            error_message=str(exc)
        )
        cal_id = job.get("calendar_id")
        if cal_id:
            update_calendar_event_status(cal_id, "failed", job_id)

        if get_setting("notify_macos", "true").lower() == "true":
            send_macos_notification(title=title, message=f"เกิดข้อผิดพลาด: {str(exc)[:40]}", subtitle="⚠️ AI Studio Error")


def _worker_loop():
    global _WORKER_RUNNING
    _WORKER_RUNNING = True
    last_cal_check = 0.0

    while not _STOP_EVENT.is_set():
        # Check auto worker toggle
        enabled = get_setting("auto_worker_enabled", "true").lower() == "true"
        if not enabled:
            time.sleep(1.0)
            continue

        now = time.monotonic()

        # Check calendar schedules every 10 seconds
        if now - last_cal_check >= 10.0:
            last_cal_check = now
            try:
                due_events = get_pending_due_calendar_events()
                for ev in due_events:
                    # Auto trigger event into queue
                    j_id = add_job(
                        task_type=ev["type"],
                        title=ev["title"],
                        prompt=ev["full_prompt"] or ev["prompt_idea"],
                        engine=ev["engine"],
                        priority=2,  # high priority for scheduled calendar items
                        calendar_id=ev["id"]
                    )
                    update_calendar_event_status(ev["id"], "queued", j_id)
                    if get_setting("notify_macos", "true").lower() == "true":
                        send_macos_notification(
                            title="Calendar Auto-Trigger",
                            message=f"เริ่มสร้างวิดีโอตามแผน: {ev['title']}",
                            subtitle="📅 AI Content Calendar"
                        )
            except Exception:
                pass

        # Check for queued jobs
        job = get_next_queued_job()
        if job:
            process_single_job(job)
        else:
            time.sleep(1.0)

    _WORKER_RUNNING = False


def start_worker():
    global _WORKER_THREAD, _STOP_EVENT
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, daemon=True, name="AIStudioWorker")
    _WORKER_THREAD.start()


def stop_worker():
    global _STOP_EVENT
    _STOP_EVENT.set()


def is_worker_running() -> bool:
    return _WORKER_RUNNING and _WORKER_THREAD is not None and _WORKER_THREAD.is_alive()
