"""Integration checks without invoking the paid Google API."""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from community_app import create_app
from studio_v6 import video_service

KEY=Fernet.generate_key()
PASSWORD='TestPassword123!'

def signup(client, num):
    r=client.post('/api/register',json={'username':f'veo_member{num}', 'email':f'veo_member{num}@test.dev','password':PASSWORD})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def draft(client, headers):
    r=client.post('/api/my/products',json={'title':'หลอดไฟ LED สำหรับทดสอบ','platform':'shopee'},headers=headers)
    assert r.status_code==200,r.text
    r=client.post('/api/my/drafts',json={'product_id':r.json()['id'],'style':'pov'},headers=headers)
    assert r.status_code==200,r.text
    return r.json()['id']


def test_connection_cards_and_no_key_leaks(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    c=TestClient(app);h=signup(c,1)
    connections=c.get('/api/my/connections').json()['providers']
    assert [x['id'] for x in connections] == ['gemini','xai','brave','openai','tiktok','shopee']
    assert not any(x['configured'] for x in connections)
    assert not any(x['enabled'] for x in connections[4:])
    assert c.put('/api/my/keys/gemini',json={'key':'API_KEY_FAKE_NOT_FOR_GOOGLE_12345'},headers=h).status_code==200
    connections=c.get('/api/my/connections').json()['providers']
    assert connections[0]['configured'] and not connections[0]['verified']
    assert 'API_KEY_FAKE' not in str(c.get('/api/my/keys').json())
    assert 'API_KEY_FAKE' not in str(c.get('/api/my/connections').json())
    assert c.put('/api/my/keys/tiktok',json={'key':'wrong_secret_key'},headers=h).status_code==400


def test_full_private_video_cycle_and_queue(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    a=TestClient(app);b=TestClient(app)
    ah=signup(a,2);bh=signup(b,3)
    did=draft(a,ah)
    assert a.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=ah).status_code==400
    a.put('/api/my/keys/gemini',json={'key':'TEST_GOOGLE_KEY_FOR_A_PRIVATE_123'},headers=ah)
    b.put('/api/my/keys/gemini',json={'key':'TEST_GOOGLE_KEY_FOR_B_PRIVATE_123'},headers=bh)
    assert a.post('/api/my/video-jobs',data={'draft_id':did},headers=ah).status_code==400
    assert a.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'}).status_code==403
    assert b.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=bh).status_code==404
    def begin(key,prompt,image,mime):
        assert key=='TEST_GOOGLE_KEY_FOR_A_PRIVATE_123'
        assert '9:16' in prompt
        assert image is None
        return 'operations/testjob9'
    with patch('studio_v6.video_service.start_video',side_effect=begin) as mocked:
        response=a.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=ah)
    assert response.status_code==200,response.text
    assert mocked.call_count == 1
    jid=response.json()['id']
    assert a.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=ah).status_code==409
    assert b.get('/api/my/video-jobs').json()==[]
    assert b.get(f'/api/my/video-jobs/{jid}/file').status_code==404
    assert b.post(f'/api/my/video-jobs/{jid}/refresh',headers=bh).status_code==404
    assert a.get(f'/api/my/video-jobs/{jid}/file').status_code==404
    # Advance the timestamp to permit a provider check.
    with sqlite3.connect(tmp_path/'community.db') as db:
        earlier=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(timespec='seconds')
        db.execute('UPDATE video_jobs SET checked_at=? WHERE id=?',(earlier,jid))
    def download(key, uri, target):
        assert key=='TEST_GOOGLE_KEY_FOR_A_PRIVATE_123'
        assert uri=='https://generativelanguage.googleapis.com/files/abc'
        Path(target).parent.mkdir(parents=True,exist_ok=True)
        Path(target).write_bytes(b'\x00\x00\x00\x18ftypmp42TESTVIDEO')
        return 20
    with patch('studio_v6.video_service.poll_video',return_value=('ready','https://generativelanguage.googleapis.com/files/abc')) as polled, \
         patch('studio_v6.video_service.download_video',side_effect=download):
        r=a.post(f'/api/my/video-jobs/{jid}/refresh',headers=ah)
    assert r.status_code==200 and r.json()['status']=='ready',r.text
    assert polled.call_count==1
    f=a.get(f'/api/my/video-jobs/{jid}/file')
    assert f.status_code==200 and b'ftypmp4' in f.content
    assert f.headers['content-type'].startswith('video/mp4')
    assert b.get(f'/api/my/video-jobs/{jid}/file').status_code==404
    ready=a.get('/api/my/video-jobs').json()[0]
    assert ready['status']=='ready'
    assert 'operation_name' not in ready and 'encrypted' not in str(ready)
    q=a.post('/api/my/queue',json={'draft_id':did,'platform':'shopee','video_job_id':jid},headers=ah)
    assert q.status_code==200,q.text
    assert a.get('/api/my/queue').json()[0]['video_url']==f'/api/my/video-jobs/{jid}/file'
    assert b.post('/api/my/queue',json={'draft_id':did,'platform':'shopee','video_job_id':jid},headers=bh).status_code==404


def test_input_cost_limits_and_failing_api(tmp_path):
    app=create_app(tmp_path,secret_key=KEY); c=TestClient(app);h=signup(c,4)
    did=draft(c,h)
    assert c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h).status_code==400
    c.put('/api/my/keys/gemini',json={'key':'TEST_FAKE_VEO_KEY_ABCDEFGHI'},headers=h)
    r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},files={'image':('sneaky.jpg',b'not a real jpeg','image/jpeg')},headers=h)
    assert r.status_code==400
    r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},files={'image':('huge.jpg',b'a'* (5*1024*1024+1),'image/jpeg')},headers=h)
    assert r.status_code==400
    with patch('studio_v6.video_service.start_video',side_effect=video_service.VideoProviderError('เครดิต/โควตา API ไม่เพียงพอ หรือมีคำขอมากเกินไป')):
        for _ in range(3):
            r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h)
            assert r.status_code==502
        assert c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h).status_code==429
    assert len(c.get('/api/my/video-jobs').json())==3


def test_provider_url_validation_and_operation_shape():
    assert video_service._google_host('https://generativelanguage.googleapis.com/v1beta/files/abc')
    assert video_service._google_host('https://storage.googleapis.com/example')
    assert not video_service._google_host('https://googleapis.com.evil.com/download')
    assert not video_service._google_host('http://generativelanguage.googleapis.com')
    assert not video_service._google_host('https://example.com@evil.com/file')
    assert video_service._valid_operation('models/veo-3.1-generate-preview/operations/abc123')
    assert not video_service._valid_operation('../../private')
    with patch('studio_v6.video_service.requests.post') as req:
        req.return_value.status_code=200
        req.return_value.json.return_value={'name':'models/veo-3.1-generate-preview/operations/abc123'}
        operation=video_service.start_video('safe_test_key','A natural POV video showing hands holding a fan')
        assert operation.endswith('/abc123')
        payload=req.call_args.kwargs['json']
        assert payload['parameters']['aspectRatio']=='9:16'
        assert payload['parameters']['durationSeconds']=='8'
        assert req.call_args.kwargs['headers']['x-goog-api-key']=='safe_test_key'
    with patch('studio_v6.video_service.requests.get') as req:
        req.return_value.status_code=200
        req.return_value.json.return_value={'done':True,'response':{'generateVideoResponse':{'generatedSamples':[{'video':{'uri':'https://generativelanguage.googleapis.com/file/test'}}]}}}
        assert video_service.poll_video('testkey','operations/testop')[0]=='ready'
