"""Mock mode (VIDEO_MOCK=1): the whole clip flow with no AI calls and no credits."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app
from studio_v6 import mock_video_service as mock_video

PW='TestPassword123!'

@pytest.fixture
def mock_env(monkeypatch):
    for name in ('PLATFORM_OPENROUTER_API_KEY','PLATFORM_MODELS','PLATFORM_CLIPS_PER_USER','PLATFORM_QUOTA_PERIOD','PLATFORM_DAILY_BUDGET_USD'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.delenv('ENABLED_VIDEO_MODELS',raising=False)
    monkeypatch.setenv('VIDEO_MOCK','1')
    monkeypatch.setenv('VIDEO_MOCK_SECONDS','0')
    return monkeypatch

def setup(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()))
    h={'X-CSRF-Token':c.post('/api/register',json={'username':'mocker','email':'mocker@example.org','password':PW}).json()['csrf']}
    p=c.post('/api/my/products',json={'title':'mini fan','platform':'shopee'},headers=h).json()
    did=c.post('/api/my/drafts',json={'product_id':p['id'],'style':'pov'},headers=h).json()['id']
    return c,h,did

def age_checks(tmp_path):
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('UPDATE video_jobs SET checked_at=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds'),))

def create(c,h,did,prompt=''):
    return c.post('/api/my/video-jobs',data={'draft_id':did,'provider':'platform','model':'google/veo-3.1-lite','prompt':prompt},headers=h)

def test_full_flow_without_any_key_or_network(tmp_path,mock_env):
    c,h,did=setup(tmp_path)
    q=c.get('/api/my/video-quota').json()
    assert q['mock'] is True and q['platform']['enabled'] and q['platform']['remaining']==3
    # Any real provider call would be a bug in mock mode.
    with patch('studio_v6.openrouter_service.requests.post',side_effect=AssertionError('network')), \
         patch('studio_v6.openrouter_service.requests.get',side_effect=AssertionError('network')):
        r=create(c,h,did)
        assert r.status_code==200,r.text
        jid=r.json()['id']
        age_checks(tmp_path)
        r=c.post(f'/api/my/video-jobs/{jid}/refresh',headers=h)
        assert r.status_code==200 and r.json()['status']=='ready',r.text
    f=c.get(f'/api/my/video-jobs/{jid}/file')
    assert f.status_code==200 and b'ftyp' in f.content[:16]
    # Quota and estimated spend behave as in real free mode.
    assert c.get('/api/my/video-quota').json()['platform']['remaining']==2
    q=c.post('/api/my/queue',json={'draft_id':did,'video_job_id':jid,'platform':'tiktok'},headers=h)
    assert q.status_code==200,q.text

def test_running_then_ready_and_failure_path(tmp_path,mock_env):
    mock_env.setenv('VIDEO_MOCK_SECONDS','3600')
    c,h,did=setup(tmp_path)
    jid=create(c,h,did).json()['id']
    age_checks(tmp_path)
    assert c.post(f'/api/my/video-jobs/{jid}/refresh',headers=h).json()['status']=='running'
    mock_env.setenv('VIDEO_MOCK_SECONDS','0')
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE video_jobs SET status='ready'")
    jid=create(c,h,did,'POV hands using a mini fan MOCK_FAIL').json()['id']
    age_checks(tmp_path)
    r=c.post(f'/api/my/video-jobs/{jid}/refresh',headers=h).json()
    assert r['status']=='failed' and 'MOCK_FAIL' in r['notice']
    # Failed jobs never use quota.
    assert c.get('/api/my/video-quota').json()['platform']['remaining']==2

def test_mock_jobs_finish_after_mock_is_switched_off(tmp_path,mock_env):
    key=Fernet.generate_key()
    c=TestClient(create_app(tmp_path,secret_key=key))
    h={'X-CSRF-Token':c.post('/api/register',json={'username':'mocker','email':'mocker@example.org','password':PW}).json()['csrf']}
    p=c.post('/api/my/products',json={'title':'mini fan','platform':'shopee'},headers=h).json()
    did=c.post('/api/my/drafts',json={'product_id':p['id'],'style':'pov'},headers=h).json()['id']
    jid=create(c,h,did).json()['id']
    # Restart with mock off and an owner key: the mock job must not be sent to OpenRouter.
    mock_env.delenv('VIDEO_MOCK')
    mock_env.setenv('PLATFORM_OPENROUTER_API_KEY','sk-or-real-owner-key')
    c2=TestClient(create_app(tmp_path,secret_key=key))
    h2={'X-CSRF-Token':c2.post('/api/login',json={'email':'mocker@example.org','password':PW}).json()['csrf']}
    assert c2.get('/api/my/video-quota').json()['mock'] is False
    age_checks(tmp_path)
    with patch('studio_v6.openrouter_service.requests.get',side_effect=AssertionError('network')):
        r=c2.post(f'/api/my/video-jobs/{jid}/refresh',headers=h2)
    assert r.status_code==200 and r.json()['status']=='ready',r.text

def test_user_clips_take_priority(tmp_path,monkeypatch):
    assets=tmp_path/'assets'
    (assets/'videos').mkdir(parents=True)
    (assets/'default.mp4').write_bytes(b'DEFAULT-CLIP-xxxxxxxx')
    monkeypatch.setattr(mock_video,'ASSETS',assets)
    job=mock_video.start_video('k','prompt')
    dest=tmp_path/'out.mp4'
    mock_video.download_video('k',f'mock://{job}',dest)
    assert dest.read_bytes().startswith(b'DEFAULT')
    (assets/'videos'/'mine.mp4').write_bytes(b'MY-OWN-CLIP-xxxxxxxx')
    mock_video.download_video('k',f'mock://{job}',dest)
    assert dest.read_bytes().startswith(b'MY-OWN')
    with pytest.raises(mock_video.VideoProviderError):
        mock_video.download_video('k','https://evil.example/x.mp4',dest)
    with pytest.raises(mock_video.VideoProviderError):
        mock_video.poll_video('k','mock-../../etc')

def test_mock_off_by_default(tmp_path,monkeypatch):
    monkeypatch.delenv('VIDEO_MOCK',raising=False)
    monkeypatch.delenv('PLATFORM_OPENROUTER_API_KEY',raising=False)
    c,h,did=setup(tmp_path)
    q=c.get('/api/my/video-quota').json()
    assert q['mock'] is False and q['platform']=={'enabled':False}
