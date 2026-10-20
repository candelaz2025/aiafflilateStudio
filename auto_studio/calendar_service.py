"""Content Calendar and Automated Plan Generator.
Generates multi-day content campaigns (7-day, 14-day, 30-day) with scheduled dates,
viral hooks, visual prompts, and automated generation triggers.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from auto_studio.db import (
    add_calendar_event,
    add_job,
    get_setting,
    list_calendar_events,
    update_calendar_event_status
)
from auto_studio.prompt_engine import (
    _call_gemini_if_available,
    generate_drama_series,
    generate_ugc_campaign,
    optimize_prompt
)


def generate_content_plan(
    campaign_type: str,     # 'drama' or 'ugc'
    topic_or_product: str,
    days_count: int = 7,
    start_date: Optional[str] = None,
    preferred_time: str = "19:00",
    channel: str = "tiktok",
    engine: str = "google_flow",
    auto_gen: bool = True
) -> List[Dict[str, Any]]:
    """Generates an intelligent multi-day content schedule and creates calendar entries."""
    if not start_date:
        start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    plan_items = []

    if campaign_type == "drama":
        # Generate drama series with episodes
        series = generate_drama_series(
            genre_key="revenge_wealth",
            custom_title=topic_or_product,
            total_episodes=days_count
        )
        episodes = series.get("episodes", [])
        for idx in range(days_count):
            cur_dt = start_dt + timedelta(days=idx)
            cur_date_str = cur_dt.strftime("%Y-%m-%d")
            ep = episodes[idx] if idx < len(episodes) else {
                "episode_title": f"ตอนที่ {idx + 1}: จุดเปลี่ยนชะตา",
                "viral_hook": "ความลับที่ถูกเปิดเผย...",
                "video_prompt": f"Dramatic cinematic scene 9:16 vertical, Episode {idx+1} of {topic_or_product}."
            }

            event_id = add_calendar_event(
                title=f"{series['title']} - {ep.get('episode_title', f'EP {idx+1}')}",
                event_type="drama",
                scheduled_date=cur_date_str,
                scheduled_time=preferred_time,
                channel=channel,
                prompt_idea=ep.get("viral_hook", ""),
                full_prompt=ep.get("video_prompt", ""),
                engine=engine,
                auto_gen=auto_gen
            )

            plan_items.append({
                "id": event_id,
                "date": cur_date_str,
                "time": preferred_time,
                "title": f"{series['title']} - {ep.get('episode_title', f'EP {idx+1}')}",
                "type": "drama",
                "hook": ep.get("viral_hook", ""),
                "prompt": ep.get("video_prompt", ""),
                "channel": channel,
                "engine": engine,
                "auto_gen": auto_gen
            })

    else:
        # UGC Campaign Generator across multiple days with different hook angles
        hook_types = ["problem_solution", "unboxing_first_impression", "seven_day_challenge", "stop_scrolling_warning"]
        for idx in range(days_count):
            cur_dt = start_dt + timedelta(days=idx)
            cur_date_str = cur_dt.strftime("%Y-%m-%d")
            h_type = hook_types[idx % len(hook_types)]

            ugc = generate_ugc_campaign(
                product_name=topic_or_product,
                hook_type=h_type
            )
            title = f"UGC Day {idx+1}: {ugc.get('hook_type', 'รีวิว')} - {topic_or_product}"
            scenes = ugc.get("scene_prompts", [])
            primary_prompt = scenes[0].get("prompt", "") if scenes else f"Authentic UGC 9:16 vertical review of {topic_or_product}."

            event_id = add_calendar_event(
                title=title,
                event_type="ugc",
                scheduled_date=cur_date_str,
                scheduled_time=preferred_time,
                channel=channel,
                prompt_idea=ugc.get("spoken_script", [{}])[0].get("text", title),
                full_prompt=primary_prompt,
                engine=engine,
                auto_gen=auto_gen
            )

            plan_items.append({
                "id": event_id,
                "date": cur_date_str,
                "time": preferred_time,
                "title": title,
                "type": "ugc",
                "hook": ugc.get("spoken_script", [{}])[0].get("text", ""),
                "prompt": primary_prompt,
                "channel": channel,
                "engine": engine,
                "auto_gen": auto_gen
            })

    return plan_items


def queue_all_calendar_events(event_ids: List[int]) -> List[int]:
    """Immediately converts selected calendar events into queued jobs."""
    events = list_calendar_events()
    created_job_ids = []
    id_set = set(event_ids)

    for ev in events:
        if ev["id"] in id_set and ev["status"] == "scheduled":
            j_id = add_job(
                task_type=ev["type"],
                title=ev["title"],
                prompt=ev["full_prompt"] or ev["prompt_idea"],
                engine=ev["engine"],
                calendar_id=ev["id"]
            )
            update_calendar_event_status(ev["id"], "queued", j_id)
            created_job_ids.append(j_id)

    return created_job_ids
