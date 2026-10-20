"""Video V7.9: no billable live calls; verify xAI adapter contract and isolation."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app
from studio_v6 import grok_service as grok

PW='TestPassword123!'

def login(c,i):
    r=c.post('/api/register',json={'username':f'grok_user_{i}','email':f'grok_user_{i}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def draft(c,h):
    p=c.post('/api/my/products',json={'title':'Portable mini fan sample','platform':'shopee'},headers=h)
    assert p.status_code==200,p.text
    d=c.post('/api/my/drafts',json={'product_id':p.json()['id'],'style':'pov'},headers=h)
    assert d.status_code==200,d.text
    return d.json()['id']

def test_xai_api_contract_and_no_ssrf(tmp_path):
    with patch('studio_v6.grok_service.requests.post') as post:
        post.return_value.status_code=200
        post.return_value.json.return_value={'request_id':'41eb9a5f-cbd4-9f21-8d59-79005f1e61b7'}
        rid=grok.start_video('PRIVATE_XAI_API_KEY','POV hands demonstrating a mini fan',model='grok-imagine-video-1.5-lite',duration=10)
        assert rid=='41eb9a5f-cbd4-9f21-8d59-79005f1e61b7'
        kwargs=post.call_args.kwargs
        assert kwargs['json']['duration']==10 and kwargs['json']['aspect_ratio']=='9:16'
        assert kwargs['json']['model']=='grok-imagine-video-1.5-lite'
        assert kwargs['headers']['Authorization']=='Bearer PRIVATE_XAI_API_KEY'
    with patch('studio_v6.grok_service.requests.get') as get:
        get.return_value.status_code=200
        get.return_value.json.return_value={'status':'done','video':{'url':'https://vidgen.x.ai/storage/file.mp4','respect_moderation':True}}
        assert grok.poll_video('secret',rid)==('ready','https://vidgen.x.ai/storage/file.mp4')
    for url in ('http://vidgen.x.ai/a.mp4','https://vidgen.x.ai.evil.com/a','https://evil.com@vidgen.x.ai:8080/x','https://169.254.169.254/secret'):
        assert not grok._xai_host(url)
    assert grok._xai_host('https://vidgen.x.ai/x/file.mp4?token=foo')
    with patch('studio_v6.grok_service.requests.post') as post:
        post.return_value.status_code=200
        post.return_value.json.return_value={'request_id':'..\\evil'}
        import pytest
        with pytest.raises(grok.VideoProviderError): grok.start_video('private','prompt',model='grok-imagine-video-1.5-lite')

def test_dual_service_selection_isolation_and_queue(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    a,b=TestClient(app),TestClient(app)
    ah,bh=login(a,1),login(b,2)
    did=draft(a,ah)
    assert a.put('/api/my/keys/xai',json={'key':'SECRET_XAI_MEMBER_A_TEST_1234'},headers=ah).status_code==200
    assert b.put('/api/my/keys/xai',json={'key':'SECRET_XAI_MEMBER_B_TEST_1234'},headers=bh).status_code==200
    assert a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'xai','model':'veo-3.1-generate-preview','confirm_paid':'true'},headers=ah).status_code==400
    assert b.post('/api/my/video-jobs',data={'draft_id':did,'provider':'xai','model':'grok-imagine-video-1.5-lite','confirm_paid':'true'},headers=bh).status_code==404
    with patch('studio_v6.grok_service.start_video',return_value='41eb9a5f-cbd4-9f21-8d59-79005f1e61b7') as start:
        r=a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'xai','model':'grok-imagine-video-1.5-lite','confirm_paid':'true'},headers=ah)
        assert r.status_code==200,r.text
        jid=r.json()['id']
        assert start.call_args.args[0]=='SECRET_XAI_MEMBER_A_TEST_1234'
        assert start.call_args.kwargs['model']=='grok-imagine-video-1.5-lite'
        assert start.call_args.kwargs['duration']==10
    mine=a.get('/api/my/video-jobs').json()[0]
    assert mine['provider']=='xai' and mine['model']=='grok-imagine-video-1.5-lite' and mine['duration']==10
    assert b.get('/api/my/video-jobs').json()==[]
    assert 'SECRET_XAI' not in str(a.get('/api/my/video-jobs').json())
    assert b.post(f'/api/my/video-jobs/{jid}/refresh',headers=bh).status_code==404
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('UPDATE video_jobs SET checked_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds'),jid))
    def write_file(k,u,dest):
        assert k=='SECRET_XAI_MEMBER_A_TEST_1234'
        assert u=='https://vidgen.x.ai/abc/video.mp4'
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(b'\x00\x00\x00\x18ftypmp42VIDEO_TEST')
        return 22
    with patch('studio_v6.grok_service.poll_video',return_value=('ready','https://vidgen.x.ai/abc/video.mp4')) as poll, patch('studio_v6.grok_service.download_video',side_effect=write_file):
        r=a.post(f'/api/my/video-jobs/{jid}/refresh',headers=ah)
        assert r.status_code==200 and r.json()['status']=='ready',r.text
        assert poll.call_count==1
    assert a.get(f'/api/my/video-jobs/{jid}/file').status_code==200
    assert b.get(f'/api/my/video-jobs/{jid}/file').status_code==404
    q=a.post('/api/my/queue',json={'draft_id':did,'video_job_id':jid,'platform':'tiktok'},headers=ah)
    assert q.status_code==200,q.text
    assert a.get('/api/my/queue').json()[0]['video_url']==f'/api/my/video-jobs/{jid}/file'
    assert b.post('/api/my/queue',json={'draft_id':did,'video_job_id':jid,'platform':'tiktok'},headers=bh).status_code==404

def test_old_database_migrates_without_changing_old_jobs(tmp_path):
    key=Fernet.generate_key()
    a=create_app(tmp_path,secret_key=key)
    c=TestClient(a);h=login(c,5)
    did=draft(c,h)
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("INSERT INTO video_jobs(user_id,draft_id,provider,prompt,status,created_at,checked_at,updated_at) VALUES(1,?,?,?,'failed',?,?,?)",
                   (did,'gemini','An older job',datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
        # Simulate old V7.8 structure without model/duration by creating replacement table schema.
        db.execute('ALTER TABLE video_jobs DROP COLUMN model')
        db.execute('ALTER TABLE video_jobs DROP COLUMN duration')
    b=create_app(tmp_path,secret_key=key)
    jobs=TestClient(b).get('/api/my/video-jobs')
    assert jobs.status_code==401 # user login is in first client only
    with sqlite3.connect(tmp_path/'community.db') as db:
        v=db.execute('SELECT provider,model,duration FROM video_jobs').fetchone()
    assert v==('gemini','veo-3.1-generate-preview',8)
