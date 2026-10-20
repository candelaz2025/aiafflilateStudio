"""Admin console: read-only member overview, admin-only, no secrets in any response."""
from __future__ import annotations
import csv
import io
import sqlite3
from unittest.mock import patch
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app

PW='TestPassword123!'
OWNER_KEY='sk-or-OWNER_PLATFORM_KEY_DO_NOT_LEAK'
JOB='gen-vid-1789480874-Ab3dEf9hIjKlMnOpQrSt'

def register(c,name,email=None):
    r=c.post('/api/register',json={'username':name,'email':email or f'{name}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def promote(tmp_path,name):
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username=?",(name,))

def test_admin_apis_require_admin(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    anon,member=TestClient(app),TestClient(app)
    register(member,'plain_member')
    for path in ('/api/admin/overview','/api/admin/members','/api/admin/members.csv'):
        assert anon.get(path).status_code==401
        assert member.get(path).status_code==403
    page=anon.get('/admin')
    assert page.status_code==200 and 'admin.js' in page.text and page.headers['cache-control']=='no-store'

def test_admin_overview_members_and_csv(tmp_path,monkeypatch):
    monkeypatch.setenv('PLATFORM_OPENROUTER_API_KEY',OWNER_KEY)
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    admin,member=TestClient(app),TestClient(app)
    register(admin,'boss')
    mh=register(member,'alice')
    member.put('/api/my/keys/openrouter',json={'key':'SECRET_MEMBER_OR_KEY_1234'},headers=mh)
    p=member.post('/api/my/products',json={'title':'=HYPERLINK("x")','platform':'shopee'},headers=mh).json()
    did=member.post('/api/my/drafts',json={'product_id':p['id'],'style':'pov'},headers=mh).json()['id']
    with patch('studio_v6.openrouter_service.start_video',return_value=JOB):
        assert member.post('/api/my/video-jobs',data={'draft_id':did,'provider':'platform','model':'google/veo-3.1-lite'},headers=mh).status_code==200
    promote(tmp_path,'boss')

    o=admin.get('/api/admin/overview').json()
    assert o['members']==2 and o['admins']==1 and o['seat_limit']==100
    assert o['free_mode']['enabled'] and o['free_mode']['clips_this_month']==1 and o['free_mode']['spent_today_usd']==0.24
    assert o['video_jobs']=={'running':1}

    rows={r['username']:r for r in admin.get('/api/admin/members').json()}
    a=rows['alice']
    assert (a['products'],a['drafts'],a['clips'],a['free_used'],a['free_limit'])==(1,1,1,1,3)
    assert a['free_cost_month_usd']==0.24 and a['own_keys']==['openrouter'] and a['last_login_at']
    assert rows['boss']['role']=='admin' and rows['boss']['own_keys']==[]

    for path in ('/api/admin/overview','/api/admin/members','/api/admin/members.csv'):
        body=admin.get(path).text
        for secret in (OWNER_KEY,'SECRET_MEMBER_OR_KEY_1234','argon2','password_hash','encrypted','csrf'):
            assert secret not in body,(path,secret)

    r=admin.get('/api/admin/members.csv')
    assert r.status_code==200 and r.headers['content-type'].startswith('text/csv')
    assert 'attachment; filename="members-' in r.headers['content-disposition']
    table=list(csv.DictReader(io.StringIO(r.text.lstrip('﻿'))))
    assert [t['username'] for t in table]==['boss','alice'] and table[1]['own_keys']=='openrouter'

def test_csv_neutralises_formulas(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    admin=TestClient(app);register(admin,'boss');promote(tmp_path,'boss')
    with sqlite3.connect(tmp_path/'community.db') as db:
        # Emails are only loosely validated, so treat stored values as untrusted.
        db.execute("UPDATE users SET email='=HYPERLINK(\"http://x\")@example.org' WHERE username='boss'")
    row=list(csv.DictReader(io.StringIO(admin.get('/api/admin/members.csv').text.lstrip('﻿'))))[0]
    assert row['email'].startswith("'=")

def _setup_three(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    boss,alice,root=TestClient(app),TestClient(app),TestClient(app)
    bh=register(boss,'boss');ah=register(alice,'alice');register(root,'root2')
    promote(tmp_path,'boss');promote(tmp_path,'root2')
    ids={r['username']:r['id'] for r in boss.get('/api/admin/members').json()}
    return app,boss,bh,alice,ah,ids

def test_admin_reset_password(tmp_path):
    app,boss,bh,alice,ah,ids=_setup_three(tmp_path)
    url=f"/api/admin/members/{ids['alice']}/reset-password"
    assert boss.post(url).status_code==403                       # no CSRF token
    assert alice.post(f"/api/admin/members/{ids['boss']}/reset-password",headers=ah).status_code==403
    assert boss.post(f"/api/admin/members/{ids['boss']}/reset-password",headers=bh).status_code==400   # self
    assert boss.post(f"/api/admin/members/{ids['root2']}/reset-password",headers=bh).status_code==400  # other admin
    assert boss.post('/api/admin/members/9999/reset-password',headers=bh).status_code==404
    r=boss.post(url,headers=bh)
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    temp=r.json()['temporary_password']
    assert alice.get('/api/me').status_code==401                 # signed out everywhere
    fresh=TestClient(app)
    assert fresh.post('/api/login',json={'email':'alice@example.org','password':PW}).status_code==401
    assert fresh.post('/api/login',json={'email':'alice@example.org','password':temp}).status_code==200
    log=boss.get('/api/admin/audit').json()
    assert log[0]['action']=='reset_password' and log[0]['target_username']=='alice' and log[0]['admin_username']=='boss'
    assert temp not in str(log) and temp not in boss.get('/api/admin/members').text

def test_admin_delete_member_removes_everything(tmp_path):
    app,boss,bh,alice,ah,ids=_setup_three(tmp_path)
    aid=ids['alice']
    # Content that must go with the account, including an idea (no ON DELETE CASCADE) with a vote on it.
    alice.put('/api/my/keys/openrouter',json={'key':'SECRET_MEMBER_OR_KEY_1234'},headers=ah)
    p=alice.post('/api/my/products',json={'title':'mini fan','platform':'shopee'},headers=ah).json()
    alice.post('/api/my/drafts',json={'product_id':p['id'],'style':'pov'},headers=ah)
    idea=alice.post('/api/ideas',json={'kind':'feature','title':'Please add export','body':'Export my drafts to a file'},headers=ah)
    assert idea.status_code==200,idea.text
    iid=idea.json()['id']
    boss.post(f'/api/ideas/{iid}/vote',headers=bh)
    video_dir=tmp_path/'videos'/str(aid);video_dir.mkdir(parents=True);(video_dir/'1.mp4').write_bytes(b'x'*20)
    url=f'/api/admin/members/{aid}/delete'
    assert boss.post(url,json={'confirm_username':'alice'}).status_code==403                    # no CSRF
    assert alice.post(f"/api/admin/members/{ids['boss']}/delete",json={'confirm_username':'boss'},headers=ah).status_code==403
    assert boss.post(f"/api/admin/members/{ids['root2']}/delete",json={'confirm_username':'root2'},headers=bh).status_code==400
    assert boss.post(url,json={'confirm_username':'alicia'},headers=bh).status_code==400        # wrong confirmation
    r=boss.post(url,json={'confirm_username':'ALICE'},headers=bh)
    assert r.status_code==200,r.text
    assert alice.get('/api/me').status_code==401
    assert not video_dir.exists()
    with sqlite3.connect(tmp_path/'community.db') as db:
        for table in ('users','sessions','credentials','products','drafts','ideas','votes'):
            col='id' if table=='users' else 'user_id'
            if table=='votes':
                assert db.execute('SELECT COUNT(*) FROM votes WHERE idea_id=?',(iid,)).fetchone()[0]==0
            else:
                assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE {col}=?',(aid,)).fetchone()[0]==0,table
    assert [m['username'] for m in boss.get('/api/admin/members').json()]==['boss','root2']
    assert TestClient(app).get('/api/beta/capacity').json()['registered']==2
    log=boss.get('/api/admin/audit').json()
    assert log[0]['action']=='delete_member' and log[0]['target_email']=='alice@example.org'
