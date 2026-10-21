"""Admin member delete: confirmation, admin protection, ideas and clip files cleaned up."""
from __future__ import annotations
import sqlite3
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app

PW='TestPassword123!'

def register(c,name):
    r=c.post('/api/register',json={'username':name,'email':f'{name}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def promote(tmp_path,name):
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username=?",(name,))

def user_id(tmp_path,name):
    with sqlite3.connect(tmp_path/'community.db') as db:
        row=db.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
    return row[0] if row else None

def setup(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    admin,member=TestClient(app),TestClient(app)
    ah=register(admin,'boss')
    mh=register(member,'alice')
    promote(tmp_path,'boss')
    return admin,ah,member,mh

def test_delete_member_with_ideas_and_clips(tmp_path):
    admin,ah,member,mh=setup(tmp_path)
    r=member.post('/api/ideas',json={'kind':'feature','title':'Better clips','body':'Please add more clip styles'},headers=mh)
    assert r.status_code==200,r.text
    uid=user_id(tmp_path,'alice')
    clips=tmp_path/'videos'/str(uid)
    clips.mkdir(parents=True)
    (clips/'clip.mp4').write_bytes(b'x')

    r=admin.delete(f'/api/admin/users/{uid}',params={'confirm_username':'ALICE'},headers=ah)
    assert r.status_code==200,r.text
    assert user_id(tmp_path,'alice') is None
    assert not clips.exists()

def test_delete_requires_matching_username(tmp_path):
    admin,ah,_,_=setup(tmp_path)
    uid=user_id(tmp_path,'alice')
    for params in ({},{'confirm_username':'bob'}):
        assert admin.delete(f'/api/admin/users/{uid}',params=params,headers=ah).status_code==400
    assert user_id(tmp_path,'alice')==uid

def test_admin_cannot_delete_or_demote_another_admin(tmp_path):
    admin,ah,member,_=setup(tmp_path)
    promote(tmp_path,'alice')
    uid=user_id(tmp_path,'alice')
    assert admin.delete(f'/api/admin/users/{uid}',params={'confirm_username':'alice'},headers=ah).status_code==400
    assert admin.patch(f'/api/admin/users/{uid}/role',json={'role':'member'},headers=ah).status_code==400
    assert user_id(tmp_path,'alice')==uid

def test_missing_user_is_404(tmp_path):
    admin,ah,_,_=setup(tmp_path)
    assert admin.delete('/api/admin/users/9999',params={'confirm_username':'x'},headers=ah).status_code==404
