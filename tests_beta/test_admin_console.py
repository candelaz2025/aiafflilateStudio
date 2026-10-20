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
