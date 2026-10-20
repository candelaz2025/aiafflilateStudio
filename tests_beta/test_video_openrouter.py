"""OpenRouter video provider: no billable live calls; verify adapter contract and isolation."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app
from studio_v6 import openrouter_service as orv

PW='TestPassword123!'
JOB='gen-vid-1789480874-Ab3dEf9hIjKlMnOpQrSt'

def login(c,i):
    r=c.post('/api/register',json={'username':f'or_user_{i}','email':f'or_user_{i}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def draft(c,h):
    p=c.post('/api/my/products',json={'title':'Portable mini fan sample','platform':'shopee'},headers=h)
    assert p.status_code==200,p.text
    d=c.post('/api/my/drafts',json={'product_id':p.json()['id'],'style':'pov'},headers=h)
    assert d.status_code==200,d.text
    return d.json()['id']

def test_openrouter_api_contract():
    with patch('studio_v6.openrouter_service.requests.post') as post:
        post.return_value.status_code=202
        post.return_value.json.return_value={'id':JOB,'polling_url':f'/api/v1/videos/{JOB}','status':'pending'}
        jid=orv.start_video('PRIVATE_OR_KEY','POV hands demonstrating a mini fan',b'\x89PNGdata','image/png',model='google/veo-3.1-lite')
        assert jid==JOB
        kwargs=post.call_args.kwargs
        assert post.call_args.args[0]=='https://openrouter.ai/api/v1/videos'
        body=kwargs['json']
        assert body['model']=='google/veo-3.1-lite' and body['duration']==8
        assert body['aspect_ratio']=='9:16' and body['resolution']=='720p' and body['generate_audio'] is True
        frame=body['frame_images'][0]
        assert frame['frame_type']=='first_frame' and frame['image_url']['url'].startswith('data:image/png;base64,')
        assert kwargs['headers']['Authorization']=='Bearer PRIVATE_OR_KEY'
    with patch('studio_v6.openrouter_service.requests.post') as post:
        post.return_value.status_code=202
        post.return_value.json.return_value={'id':JOB,'status':'pending'}
        orv.start_video('k','prompt text here',model='x-ai/grok-imagine-video-1.5-lite')
        assert 'generate_audio' not in post.call_args.kwargs['json']
        assert 'frame_images' not in post.call_args.kwargs['json']
    with pytest.raises(orv.VideoProviderError): orv.start_video('k','prompt',model='openai/sora-2-pro')
    with patch('studio_v6.openrouter_service.requests.post') as post:
        post.return_value.status_code=202
        post.return_value.json.return_value={'id':'../../evil','status':'pending'}
        with pytest.raises(orv.VideoProviderError): orv.start_video('k','prompt',model='google/veo-3.1-lite')
    with patch('studio_v6.openrouter_service.requests.post') as post:
        post.return_value.status_code=402
        with pytest.raises(orv.VideoProviderError,match='เครดิต'): orv.start_video('k','prompt',model='google/veo-3.1-lite')

def test_openrouter_poll_states():
    def poll(status):
        with patch('studio_v6.openrouter_service.requests.get') as get:
            get.return_value.status_code=200
            # polling_url from the response must be ignored in favour of the fixed endpoint.
            get.return_value.json.return_value={'id':JOB,'status':status,'polling_url':'https://evil.example/x'}
            result=orv.poll_video('k',JOB)
            assert get.call_args.args[0]==f'https://openrouter.ai/api/v1/videos/{JOB}'
            return result
    assert poll('pending')==('running',None)
    assert poll('in_progress')==('running',None)
    assert poll('completed')==('ready',f'https://openrouter.ai/api/v1/videos/{JOB}/content?index=0')
    for bad in ('failed','cancelled','expired','weird'):
        with pytest.raises(orv.VideoProviderError): poll(bad)
    with pytest.raises(orv.VideoProviderError): orv.poll_video('k','../admin')

def test_openrouter_download_keeps_key_off_redirect_hosts(tmp_path):
    first=MagicMock(status_code=302,headers={'Location':'https://storage.example-cdn.com/v.mp4?sig=1'})
    second=MagicMock(status_code=200,headers={'Content-Length':'22'})
    second.iter_content.return_value=[b'\x00\x00\x00\x18ftypmp42VIDEO']
    for m in (first,second): m.__enter__.return_value=m
    with patch('studio_v6.openrouter_service.requests.get',side_effect=[first,second]) as get:
        dest=tmp_path/'v.mp4'
        orv.download_video('SECRET',f'https://openrouter.ai/api/v1/videos/{JOB}/content?index=0',dest)
        assert dest.read_bytes().startswith(b'\x00\x00\x00\x18ftyp')
        assert get.call_args_list[0].kwargs['headers']=={'Authorization':'Bearer SECRET'}
        assert get.call_args_list[1].kwargs['headers']=={}
    for url in ('http://openrouter.ai/api/v1/videos/x/content','https://openrouter.ai.evil.com/api/v1/videos/x','https://evil.com/api/v1/videos/x'):
        with pytest.raises(orv.VideoProviderError): orv.download_video('k',url,tmp_path/'x.mp4')
    for url in ('https://169.254.169.254/latest','https://localhost/x','http://cdn.example.com/x','https://a@cdn.example.com/x'):
        assert not orv._safe_redirect(url)

def test_openrouter_job_flow_and_isolation(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    a,b=TestClient(app),TestClient(app)
    ah,bh=login(a,1),login(b,2)
    did=draft(a,ah)
    conn=[p for p in a.get('/api/my/connections').json()['providers'] if p['id']=='openrouter'][0]
    assert conn['enabled'] and not conn['configured']
    r=a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'openrouter','model':'google/veo-3.1-lite','confirm_paid':'true'},headers=ah)
    assert r.status_code==400 and 'OpenRouter' in r.json()['detail']
    assert a.put('/api/my/keys/openrouter',json={'key':'SECRET_OR_MEMBER_A_TEST_1234'},headers=ah).status_code==200
    assert a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'openrouter','model':'grok-imagine-video-1.5-lite','confirm_paid':'true'},headers=ah).status_code==400
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB) as start:
        r=a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'openrouter','model':'google/veo-3.1-lite','confirm_paid':'true'},headers=ah)
        assert r.status_code==200,r.text
        jid=r.json()['id']
        assert start.call_args.args[0]=='SECRET_OR_MEMBER_A_TEST_1234'
        assert start.call_args.kwargs['model']=='google/veo-3.1-lite'
    mine=a.get('/api/my/video-jobs').json()[0]
    assert mine['provider']=='openrouter' and mine['model']=='google/veo-3.1-lite' and mine['duration']==8
    assert 'SECRET_OR' not in str(mine)
    assert b.get('/api/my/video-jobs').json()==[]
    assert b.post(f'/api/my/video-jobs/{jid}/refresh',headers=bh).status_code==404
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('UPDATE video_jobs SET checked_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds'),jid))
    def write_file(k,u,dest):
        assert k=='SECRET_OR_MEMBER_A_TEST_1234'
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(b'\x00\x00\x00\x18ftypmp42VIDEO_TEST')
        return 22
    content=f'https://openrouter.ai/api/v1/videos/{JOB}/content?index=0'
    with patch('studio_v6.openrouter_service.poll_video',return_value=('ready',content)), patch('studio_v6.openrouter_service.download_video',side_effect=write_file):
        r=a.post(f'/api/my/video-jobs/{jid}/refresh',headers=ah)
        assert r.status_code==200 and r.json()['status']=='ready',r.text
    f=a.get(f'/api/my/video-jobs/{jid}/file')
    assert f.status_code==200 and b'ftypmp4' in f.content
    assert b.get(f'/api/my/video-jobs/{jid}/file').status_code==404

def test_openrouter_transient_poll_error_stays_running(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    a=TestClient(app);ah=login(a,3);did=draft(a,ah)
    a.put('/api/my/keys/openrouter',json={'key':'SECRET_OR_MEMBER_C_TEST_1234'},headers=ah)
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        jid=a.post('/api/my/video-jobs',data={'draft_id':did,'provider':'openrouter','model':'alibaba/wan-3.0','confirm_paid':'true'},headers=ah).json()['id']
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('UPDATE video_jobs SET checked_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds'),jid))
    with patch('studio_v6.openrouter_service.poll_video',side_effect=orv.VideoProviderError('ตรวจสถานะ OpenRouter ไม่สำเร็จ')):
        assert a.post(f'/api/my/video-jobs/{jid}/refresh',headers=ah).json()['status']=='running'
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('UPDATE video_jobs SET checked_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds'),jid))
    with patch('studio_v6.openrouter_service.poll_video',side_effect=orv.VideoProviderError('OpenRouter สร้างคลิปไม่สำเร็จ (failed) กรุณาตรวจเนื้อหาและเครดิต')):
        assert a.post(f'/api/my/video-jobs/{jid}/refresh',headers=ah).json()['status']=='failed'
