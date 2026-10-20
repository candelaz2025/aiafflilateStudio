"""Database access layer for Auto Studio Pro.
Manages queue jobs, calendar plans, drama series, UGC campaigns, prompts, and settings.
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if os.environ.get("VERCEL"):
    DATA_DIR = Path("/tmp/auto_studio_data")
else:
    DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "auto_studio.db"
_LOCAL = threading.local()
_DB_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _DB_LOCK, get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS queue_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,          -- 'drama', 'ugc', 'prompt_gen', 'calendar_auto'
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            engine TEXT NOT NULL,             -- 'google_flow', 'meta_ai', 'veo_api'
            aspect_ratio TEXT NOT NULL DEFAULT '9:16',
            status TEXT NOT NULL DEFAULT 'queued', -- 'queued', 'prompt_crafting', 'dispatching', 'rendering', 'downloading', 'completed', 'failed'
            progress INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 3,
            logs TEXT NOT NULL DEFAULT '[]',
            video_path TEXT NOT NULL DEFAULT '',
            thumbnail_path TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0.0,
            calendar_id INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL,              -- 'drama', 'ugc', 'custom'
            scheduled_date TEXT NOT NULL,     -- 'YYYY-MM-DD'
            scheduled_time TEXT NOT NULL,     -- 'HH:MM'
            channel TEXT NOT NULL DEFAULT 'tiktok', -- 'tiktok', 'reels', 'shorts', 'all'
            prompt_idea TEXT NOT NULL,
            full_prompt TEXT NOT NULL DEFAULT '',
            engine TEXT NOT NULL DEFAULT 'google_flow',
            auto_gen INTEGER NOT NULL DEFAULT 1, -- 1 = auto generate when time arrives
            status TEXT NOT NULL DEFAULT 'scheduled', -- 'scheduled', 'queued', 'generating', 'completed', 'failed'
            job_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES queue_jobs(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS drama_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            genre TEXT NOT NULL,
            synopsis TEXT NOT NULL,
            characters TEXT NOT NULL DEFAULT '[]', -- JSON
            episodes TEXT NOT NULL DEFAULT '[]',   -- JSON
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ugc_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            niche TEXT NOT NULL,
            target_audience TEXT NOT NULL,
            hook_type TEXT NOT NULL,
            creator_persona TEXT NOT NULL,
            script_lines TEXT NOT NULL DEFAULT '[]',  -- JSON
            scene_prompts TEXT NOT NULL DEFAULT '[]', -- JSON
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prompt_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,  -- 'drama', 'ugc', 'cinematic', 'camera', 'lighting'
            engine TEXT NOT NULL,    -- 'google_flow', 'meta_ai', 'universal'
            prompt_text TEXT NOT NULL,
            negative_prompt TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """)

        # Seed initial settings if empty
        import os
        env_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
        defaults = {
            "auto_worker_enabled": "true",
            "default_engine": "google_flow",
            "gemini_api_key": env_gemini,
            "meta_ai_token": "",
            "meta_ai_cookies": "",
            "simulation_mode": "false" if env_gemini else "true",
            "concurrency_limit": "2",
            "notify_macos": "true",
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = CASE WHEN value = '' THEN excluded.value ELSE value END",
                (k, v, now_iso())
            )

        # Seed sample prompt templates if empty
        row = conn.execute("SELECT COUNT(*) FROM prompt_library").fetchone()
        if row and row[0] == 0:
            sample_prompts = [
                (
                    "Thai Short Drama - Dramatic Confrontation",
                    "drama",
                    "universal",
                    "Cinematic 9:16 vertical short drama scene, high-tension confrontation inside a luxury Bangkok penthouse, intense close-up on woman's tearful angry eyes, dramatic chiaroscuro lighting, subtle camera push-in, 4k ultra-realistic drama series aesthetic, 24fps film look.",
                    "cartoon, 3d render, blurry, distorted faces, low resolution, bad hands, oversaturated",
                    "drama, micro-drama, suspense, confrontation"
                ),
                (
                    "UGC TikTok Skincare Viral Review",
                    "ugc",
                    "google_flow",
                    "Authentic UGC style iPhone 15 Pro front camera selfie video, 25yo cheerful Thai female creator applying glowing serum to cheek, natural bathroom lighting, morning aesthetic, high-detail skin texture, genuine excitement expression, handheld micro-camera wobble, vertical 9:16.",
                    "studio lighting, artificial mannequin, fake smile, heavy cgi, static camera, watermark",
                    "ugc, skincare, authentic, tiktok, review"
                ),
                (
                    "Meta AI Movie Gen - High Speed Action Drama",
                    "drama",
                    "meta_ai",
                    "Movie Gen cinematic camera movement, fast-paced vertical thriller scene, rain droplets hitting neon-lit windshield in Bangkok alley at night, reflections of cyberpunk signs, shallow depth of field, anamorphic bokeh, photorealistic cinema.",
                    "blurry, low frame rate, plastic texture, bad anatomy",
                    "meta_ai, thriller, action, rain, cinematic"
                ),
                (
                    "UGC Problem-Solution Unboxing",
                    "ugc",
                    "universal",
                    "Close-up first-person POV hands unboxing a minimalist premium tech gadget packaging on clean wooden desk, sunlight casting soft natural shadows, macro focus on unsealing pull tab, tactile sound vibe, 9:16 vertical video.",
                    "blurry packaging, deformed fingers, extra fingers, noisy background",
                    "ugc, unboxing, gadget, pov, aesthetic"
                )
            ]
            for title, cat, eng, pt, neg, tags in sample_prompts:
                conn.execute(
                    """INSERT INTO prompt_library (title, category, engine, prompt_text, negative_prompt, tags, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (title, cat, eng, pt, neg, tags, now_iso())
                )
        conn.commit()


# --- Settings Helper ---
def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with _DB_LOCK, get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now_iso())
        )
        conn.commit()


def get_all_settings() -> Dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# --- Queue Jobs Helper ---
def add_job(
    task_type: str,
    title: str,
    prompt: str,
    engine: str = "google_flow",
    aspect_ratio: str = "9:16",
    priority: int = 3,
    calendar_id: Optional[int] = None
) -> int:
    initial_log = json.dumps([{"time": now_iso(), "stage": "queued", "message": f"Job queued for engine: {engine}"}])
    with _DB_LOCK, get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO queue_jobs 
               (task_type, title, prompt, engine, aspect_ratio, status, progress, priority, logs, calendar_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?)""",
            (task_type, title, prompt, engine, aspect_ratio, priority, initial_log, calendar_id, now_iso())
        )
        conn.commit()
        return cur.lastrowid


def update_job_stage(
    job_id: int,
    status: str,
    progress: int,
    log_message: str,
    video_path: str = "",
    thumbnail_path: str = "",
    duration: float = 0.0,
    error_message: Optional[str] = None
) -> None:
    with _DB_LOCK, get_connection() as conn:
        row = conn.execute("SELECT logs, started_at FROM queue_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return
        try:
            logs = json.loads(row["logs"] or "[]")
        except Exception:
            logs = []
        logs.append({"time": now_iso(), "stage": status, "message": log_message})

        started_at = row["started_at"]
        if not started_at and status in ("prompt_crafting", "dispatching", "rendering"):
            started_at = now_iso()

        completed_at = now_iso() if status in ("completed", "failed") else None

        conn.execute(
            """UPDATE queue_jobs SET 
               status = ?, progress = ?, logs = ?,
               video_path = CASE WHEN ? != '' THEN ? ELSE video_path END,
               thumbnail_path = CASE WHEN ? != '' THEN ? ELSE thumbnail_path END,
               duration = CASE WHEN ? > 0 THEN ? ELSE duration END,
               started_at = COALESCE(started_at, ?),
               completed_at = COALESCE(?, completed_at),
               error_message = ?
               WHERE id = ?""",
            (
                status, progress, json.dumps(logs),
                video_path, video_path,
                thumbnail_path, thumbnail_path,
                duration, duration,
                started_at, completed_at, error_message, job_id
            )
        )
        conn.commit()


def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM queue_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM queue_jobs WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM queue_jobs ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_next_queued_job() -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM queue_jobs 
               WHERE status = 'queued' 
               ORDER BY priority ASC, id ASC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None


def delete_job(job_id: int) -> bool:
    with _DB_LOCK, get_connection() as conn:
        conn.execute("DELETE FROM queue_jobs WHERE id = ?", (job_id,))
        conn.commit()
        return True


# --- Calendar Helper ---
def add_calendar_event(
    title: str,
    event_type: str,
    scheduled_date: str,
    scheduled_time: str,
    prompt_idea: str,
    full_prompt: str = "",
    channel: str = "tiktok",
    engine: str = "google_flow",
    auto_gen: bool = True
) -> int:
    with _DB_LOCK, get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO calendar_events 
               (title, type, scheduled_date, scheduled_time, channel, prompt_idea, full_prompt, engine, auto_gen, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)""",
            (title, event_type, scheduled_date, scheduled_time, channel, prompt_idea, full_prompt, engine, 1 if auto_gen else 0, now_iso())
        )
        conn.commit()
        return cur.lastrowid


def list_calendar_events(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT * FROM calendar_events WHERE scheduled_date BETWEEN ? AND ? ORDER BY scheduled_date ASC, scheduled_time ASC",
                (date_from, date_to)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM calendar_events ORDER BY scheduled_date ASC, scheduled_time ASC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_pending_due_calendar_events() -> List[Dict[str, Any]]:
    now_local = datetime.now()
    curr_date = now_local.strftime("%Y-%m-%d")
    curr_time = now_local.strftime("%H:%M")
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM calendar_events 
               WHERE auto_gen = 1 
                 AND status = 'scheduled'
                 AND (scheduled_date < ? OR (scheduled_date = ? AND scheduled_time <= ?))
               ORDER BY scheduled_date ASC, scheduled_time ASC""",
            (curr_date, curr_date, curr_time)
        ).fetchall()
        return [dict(r) for r in rows]


def update_calendar_event_status(event_id: int, status: str, job_id: Optional[int] = None) -> None:
    with _DB_LOCK, get_connection() as conn:
        if job_id:
            conn.execute(
                "UPDATE calendar_events SET status = ?, job_id = ? WHERE id = ?",
                (status, job_id, event_id)
            )
        else:
            conn.execute(
                "UPDATE calendar_events SET status = ? WHERE id = ?",
                (status, event_id)
            )
        conn.commit()


def delete_calendar_event(event_id: int) -> bool:
    with _DB_LOCK, get_connection() as conn:
        conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
        conn.commit()
        return True


# --- Drama Series Helper ---
def save_drama_series(title: str, genre: str, synopsis: str, characters: list, episodes: list) -> int:
    with _DB_LOCK, get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO drama_series (title, genre, synopsis, characters, episodes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, genre, synopsis, json.dumps(characters, ensure_ascii=False), json.dumps(episodes, ensure_ascii=False), now_iso())
        )
        conn.commit()
        return cur.lastrowid


def list_drama_series() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM drama_series ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["characters"] = json.loads(d["characters"])
                d["episodes"] = json.loads(d["episodes"])
            except Exception:
                pass
            result.append(d)
        return result


def get_drama_series(series_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM drama_series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["characters"] = json.loads(d["characters"])
            d["episodes"] = json.loads(d["episodes"])
        except Exception:
            pass
        return d


# --- UGC Campaigns Helper ---
def save_ugc_campaign(product_name: str, niche: str, target_audience: str, hook_type: str, creator_persona: str, script_lines: list, scene_prompts: list) -> int:
    with _DB_LOCK, get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO ugc_campaigns (product_name, niche, target_audience, hook_type, creator_persona, script_lines, scene_prompts, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_name, niche, target_audience, hook_type, creator_persona, json.dumps(script_lines, ensure_ascii=False), json.dumps(scene_prompts, ensure_ascii=False), now_iso())
        )
        conn.commit()
        return cur.lastrowid


def list_ugc_campaigns() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM ugc_campaigns ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["script_lines"] = json.loads(d["script_lines"])
                d["scene_prompts"] = json.loads(d["scene_prompts"])
            except Exception:
                pass
            result.append(d)
        return result


# Initialize DB upon import
init_db()
