"""Free mode: the owner's server-side OpenRouter key, per-member quota and daily budget cap."""
from __future__ import annotations
import sqlite3
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app
from studio_v6 import openrouter_service as orv

PW='TestPassword123!'
OWNER_KEY='sk-or-OWNER_PLATFORM_KEY_DO_NOT_LEAK'
JOB='gen-vid-1789480874-Ab3dEf9hIjKlMnOpQrSt'

@pytest.fixture(autouse=True)
def platform_env(monkeypatch):
    for name in ('PLATFORM_OPENROUTER_API_KEY','PLATFORM_MODELS','PLATFORM_CLIPS_PER_USER','PLATFORM_QUOTA_PERIOD','PLATFORM_DAILY_BUDGET_USD'):
        monkeypatch.delenv(name,raising=False)
    return monkeypatch

def login(c,i):
    r=c.post('/api/register',json={'username':f'free_user_{i}','email':f'free_user_{i}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def draft(c,h):
    p=c.post('/api/my/products',json={'title':'Portable mini fan sample','platform':'shopee'},headers=h)
    d=c.post('/api/my/drafts',json={'product_id':p.json()['id'],'style':'pov'},headers=h)
    return d.json()['id']

def finish(tmp_path,status='ready'):
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE video_jobs SET status=? WHERE status IN ('submitting','running')",(status,))

def create(c,h,did,model='google/veo-3.1-lite'):
    # No confirm_paid: free mode must not ask the member to accept charges.
    return c.post('/api/my/video-jobs',data={'draft_id':did,'provider':'platform','model':model},headers=h)

def test_free_mode_off_by_default(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()));h=login(c,1);did=draft(c,h)
    assert c.get('/api/my/video-quota').json()['platform']=={'enabled':False}
    r=create(c,h,did)
    assert r.status_code==400 and 'โหมดฟรี' in r.json()['detail']

def test_free_mode_uses_owner_key_without_leaking_it(tmp_path,platform_env):
    platform_env.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()));h=login(c,1);did=draft(c,h)
    q=c.get('/api/my/video-quota').json()['platform']
    assert q['enabled'] and q['remaining']==3 and q['period']=='month' and q['budget_available']
    assert [m['id'] for m in q['models']]==['google/veo-3.1-lite']
    assert c.post('/api/my/video-jobs',data={'draft_id':did,'provider':'platform','model':'google/veo-3.1-fast'},headers=h).status_code==400
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB) as start:
        r=create(c,h,did)
        assert r.status_code==200,r.text
        assert start.call_args.args[0]==OWNER_KEY
        assert start.call_args.kwargs['audio'] is False
        assert start.call_args.kwargs['user']=='aas-1'
    for body in (r.text,c.get('/api/my/video-jobs').text,c.get('/api/my/video-quota').text,c.get('/api/my/connections').text):
        assert OWNER_KEY not in body
    assert c.get('/api/my/video-quota').json()['platform']['remaining']==2
    with sqlite3.connect(tmp_path/'community.db') as db:
        assert db.execute('SELECT provider,est_cost_usd FROM video_jobs').fetchone()==('platform',0.24)

def test_quota_counts_only_non_failed_jobs(tmp_path,platform_env):
    platform_env.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    platform_env.setenv('PLATFORM_CLIPS_PER_USER','2')
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()));h=login(c,1);did=draft(c,h)
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        assert create(c,h,did).status_code==200; finish(tmp_path,'failed')
        assert c.get('/api/my/video-quota').json()['platform']['remaining']==2
        assert create(c,h,did).status_code==200; finish(tmp_path)
        assert create(c,h,did).status_code==200; finish(tmp_path)
    # Drop the failed row so the 3/day Beta cap (which counts every job) does not answer first.
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("DELETE FROM video_jobs WHERE status='failed'")
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        r=create(c,h,did)
        assert r.status_code==429 and 'โควตาฟรีเดือนนี้ครบ 2' in r.json()['detail']
    q=c.get('/api/my/video-quota').json()['platform']
    assert q['remaining']==0
    # The member can still continue with their own key.
    c.put('/api/my/keys/openrouter',json={'key':'SECRET_OR_MEMBER_TEST_1234'},headers=h)

def test_daily_budget_cap_is_shared_across_members(tmp_path,platform_env):
    platform_env.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    platform_env.setenv('PLATFORM_DAILY_BUDGET_USD','0.30')
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    a,b=TestClient(app),TestClient(app)
    ah,bh=login(a,1),login(b,2)
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        assert create(a,ah,draft(a,ah)).status_code==200
        r=create(b,bh,draft(b,bh))
        assert r.status_code==429 and 'งบโหมดฟรี' in r.json()['detail']
    assert b.get('/api/my/video-quota').json()['platform']['budget_available'] is False

def test_owner_credit_errors_are_hidden_from_members(tmp_path,platform_env):
    platform_env.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()));h=login(c,1);did=draft(c,h)
    with patch('studio_v6.openrouter_service.start_video',side_effect=orv.VideoProviderError('เครดิต OpenRouter ไม่พอ เติมเครดิตที่ openrouter.ai/credits')):
        r=create(c,h,did)
    assert r.status_code==502 and r.json()['detail']=='โหมดฟรีของระบบใช้งานไม่ได้ชั่วคราว กรุณาลองใหม่ภายหลัง'
    assert c.get('/api/my/video-quota').json()['platform']['remaining']==3

def test_audio_flag_in_payload():
    with patch('studio_v6.openrouter_service.requests.post') as post:
        post.return_value.status_code=202
        post.return_value.json.return_value={'id':JOB,'status':'pending'}
        orv.start_video('k','prompt text',model='google/veo-3.1-lite',audio=False,user='aas-7')
        body=post.call_args.kwargs['json']
        assert body['generate_audio'] is False and body['user']=='aas-7'
    assert orv.estimated_cost('google/veo-3.1-lite',False)==0.24 and orv.estimated_cost('google/veo-3.1-lite')==0.40

def test_default_allows_only_openrouter_veo_lite(tmp_path,platform_env):
    platform_env.delenv('ENABLED_VIDEO_MODELS',raising=False)
    platform_env.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    platform_env.setenv('PLATFORM_MODELS','google/veo-3.1-lite,x-ai/grok-imagine-video-1.5-lite')
    c=TestClient(create_app(tmp_path,secret_key=Fernet.generate_key()));h=login(c,1);did=draft(c,h)
    q=c.get('/api/my/video-quota').json()
    assert q['enabled_models']=={'gemini':[],'xai':[],'openrouter':['google/veo-3.1-lite']}
    # PLATFORM_MODELS cannot re-open a model that is switched off.
    assert [m['id'] for m in q['platform']['models']]==['google/veo-3.1-lite']
    for key in ('gemini','xai','openrouter'):
        c.put(f'/api/my/keys/{key}',json={'key':'SECRET_MEMBER_KEY_TEST_1234'},headers=h)
    for provider,model in (('gemini','veo-3.1-generate-preview'),('xai','grok-imagine-video-1.5-lite'),
                           ('openrouter','alibaba/wan-3.0'),('platform','x-ai/grok-imagine-video-1.5-lite')):
        r=c.post('/api/my/video-jobs',data={'draft_id':did,'provider':provider,'model':model,'confirm_paid':'true'},headers=h)
        assert r.status_code==400,(provider,model,r.text)
    cards={p['id']:p['supports'] for p in c.get('/api/my/connections').json()['providers']}
    assert 'ปิดใช้งานชั่วคราว' in cards['gemini'] and 'ปิดใช้งานชั่วคราว' in cards['xai']
    assert 'เปิดเฉพาะ google/veo-3.1-lite' in cards['openrouter']
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        r=c.post('/api/my/video-jobs',data={'draft_id':did,'provider':'openrouter','model':'google/veo-3.1-lite','confirm_paid':'true'},headers=h)
        assert r.status_code==200,r.text
        finish(tmp_path)
        assert create(c,h,did).status_code==200
