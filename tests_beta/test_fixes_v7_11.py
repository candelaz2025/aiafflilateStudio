"""Regression tests for bugs found in 0.7.10. No paid provider API is called."""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from community_app import create_app

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PASS='ExcellentPass123456'


def register(c,n):
    r=c.post('/api/register',json={'username':f'fix{n:04d}','email':f'fix{n:04d}@example.org','password':PASS})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}


def ago(**kw):
    return (datetime.now(timezone.utc)-timedelta(**kw)).isoformat(timespec='seconds')


def draft_with_key(c,h):
    p=c.post('/api/my/products',json={'title':'เครื่องดูดฝุ่นทดสอบ','platform':'shopee'},headers=h).json()['id']
    did=c.post('/api/my/drafts',json={'product_id':p,'style':'pov'},headers=h).json()['id']
    assert c.put('/api/my/keys/gemini',json={'key':'TEST_GOOGLE_KEY_NOT_REAL_123'},headers=h).status_code==200
    return did


def test_stale_submitting_job_does_not_block_member_forever(tmp_path):
    # A server crash between INSERT 'submitting' and the provider reply left the row behind.
    c=TestClient(create_app(tmp_path,secret_key=KEY));h=register(c,1)
    did=draft_with_key(c,h)
    with sqlite3.connect(tmp_path/'community.db') as db:
        uid=db.execute("SELECT id FROM users WHERE username='fix0001'").fetchone()[0]
        old=ago(minutes=30)
        cur=db.execute("INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,created_at,checked_at,updated_at) "
                       "VALUES(?,?,'gemini','veo-3.1-generate-preview',8,'stale prompt for test','submitting',?,?,?)",(uid,did,old,old,old))
        stale=cur.lastrowid
    r=c.post(f'/api/my/video-jobs/{stale}/refresh',headers=h)
    assert r.status_code==200 and r.json()['status']=='failed',r.text
    with patch('studio_v6.video_service.start_video',return_value='operations/afterstale1'):
        r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h)
    assert r.status_code==200,r.text


def test_stale_submitting_job_expires_on_new_request_too(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=KEY));h=register(c,2)
    did=draft_with_key(c,h)
    with sqlite3.connect(tmp_path/'community.db') as db:
        uid=db.execute("SELECT id FROM users WHERE username='fix0002'").fetchone()[0]
        old=ago(minutes=30)
        db.execute("INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,created_at,checked_at,updated_at) "
                   "VALUES(?,?,'gemini','veo-3.1-generate-preview',8,'stale prompt for test','submitting',?,?,?)",(uid,did,old,old,old))
    with patch('studio_v6.video_service.start_video',return_value='operations/afterstale2'):
        r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h)
    assert r.status_code==200,r.text
    jobs={j['status'] for j in c.get('/api/my/video-jobs').json()}
    assert jobs=={'failed','running'}


def test_fresh_submitting_job_still_blocks_duplicate_spend(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=KEY));h=register(c,3)
    did=draft_with_key(c,h)
    with sqlite3.connect(tmp_path/'community.db') as db:
        uid=db.execute("SELECT id FROM users WHERE username='fix0003'").fetchone()[0]
        fresh=ago(seconds=20)
        db.execute("INSERT INTO video_jobs(user_id,draft_id,provider,model,duration,prompt,status,created_at,checked_at,updated_at) "
                   "VALUES(?,?,'gemini','veo-3.1-generate-preview',8,'in flight prompt test','submitting',?,?,?)",(uid,did,fresh,fresh,fresh))
    with patch('studio_v6.video_service.start_video',return_value='operations/dup') as mocked:
        r=c.post('/api/my/video-jobs',data={'draft_id':did,'confirm_paid':'true'},headers=h)
    assert r.status_code==409 and mocked.call_count==0


def test_failed_logins_from_one_ip_do_not_lock_out_owner_elsewhere(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    attacker=TestClient(app,client=('203.0.113.9',50000))
    owner=TestClient(app,client=('198.51.100.7',50000))
    register(owner,4)
    for _ in range(8):
        assert attacker.post('/api/login',json={'email':'fix0004@example.org','password':'WrongPass123456'}).status_code==401
    assert attacker.post('/api/login',json={'email':'fix0004@example.org','password':PASS}).status_code==429
    assert owner.post('/api/login',json={'email':'fix0004@example.org','password':PASS}).status_code==200


def test_expired_login_failures_and_sessions_are_purged(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=KEY));register(c,5)
    with sqlite3.connect(tmp_path/'community.db') as db:
        uid=db.execute("SELECT id FROM users WHERE username='fix0005'").fetchone()[0]
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES('expiredhash',?,'x',?)",(uid,ago(days=1)))
        db.execute("INSERT INTO login_attempts(email,ip,attempts,reset_at) VALUES('nobody@example.org','203.0.113.1',3,?)",(ago(hours=1),))
    assert c.post('/api/login',json={'email':'fix0005@example.org','password':'WrongPass123456'}).status_code==401
    assert c.post('/api/login',json={'email':'fix0005@example.org','password':PASS}).status_code==200
    with sqlite3.connect(tmp_path/'community.db') as db:
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE token_hash='expiredhash'").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM login_attempts WHERE email='nobody@example.org'").fetchone()[0]==0
