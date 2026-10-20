"""Mock video provider (VIDEO_MOCK=1): the full job flow without calling any AI or spending credits.

A job id carries its start time, so polling reports "running" for VIDEO_MOCK_SECONDS and then
"ready". The finished clip is copied from assets/mock/videos/ (add your own MP4 sample clips there);
when that folder is empty the bundled assets/mock/default.mp4 is used. A prompt containing
MOCK_FAIL makes the job fail, to exercise the error path.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets' / 'mock'
FAIL_MARK = 'MOCK_FAIL'

class VideoProviderError(Exception):
    pass


def _delay():
    try:
        return max(0, int(os.getenv('VIDEO_MOCK_SECONDS', '20')))
    except ValueError:
        return 20


def is_mock_job(job_id):
    return isinstance(job_id, str) and job_id.startswith('mock-')


def _parse(job_id):
    m = re.fullmatch(r'mock-(\d{10})-([a-f0-9]{12})-(ok|fail)', job_id or '')
    if not m:
        raise VideoProviderError('รหัสงานจำลองไม่ถูกต้อง')
    return int(m.group(1)), m.group(2), m.group(3)


def start_video(api_key, prompt, image=None, mime=None, **_options):
    # Same validation as the real adapters so the mock exercises the same inputs.
    if image is not None and (mime not in ('image/jpeg', 'image/png') or not (0 < len(image) <= 5*1024*1024)):
        raise VideoProviderError('ภาพต้องเป็น JPG/PNG ไม่เกิน 5MB')
    outcome = 'fail' if FAIL_MARK in (prompt or '') else 'ok'
    return f'mock-{int(time.time()):010d}-{secrets.token_hex(6)}-{outcome}'


def poll_video(api_key, job_id):
    started, _, outcome = _parse(job_id)
    if time.time() - started < _delay():
        return 'running', None
    if outcome == 'fail':
        raise VideoProviderError('งานจำลองล้มเหลวตามที่ขอ (MOCK_FAIL)')
    return 'ready', f'mock://{job_id}'


def sample_clips():
    clips = sorted(p for p in (ASSETS / 'videos').glob('*.mp4') if p.is_file())
    default = ASSETS / 'default.mp4'
    return clips or ([default] if default.is_file() else [])


def download_video(api_key, uri, filepath):
    if not (isinstance(uri, str) and uri.startswith('mock://')):
        raise VideoProviderError('ลิงก์วิดีโอจำลองไม่ถูกต้อง')
    _, token, _ = _parse(uri[len('mock://'):])
    clips = sample_clips()
    if not clips:
        raise VideoProviderError('ไม่พบคลิปตัวอย่างใน assets/mock')
    # Stable pick per job, so a refresh never swaps the clip.
    source = clips[int(hashlib.sha256(token.encode()).hexdigest(), 16) % len(clips)]
    dest = Path(filepath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest.stat().st_size
