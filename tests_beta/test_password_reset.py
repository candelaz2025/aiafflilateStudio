"""Forgotten password: server-side reset script, then change password in the web."""
from __future__ import annotations
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from community_app import create_app

ROOT=Path(__file__).resolve().parents[1]
PW='OriginalPassword123'

def register(c,name='forgetful'):
    r=c.post('/api/register',json={'username':name,'email':f'{name}@example.org','password':PW})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def run_reset(tmp_path,email):
    env=dict(os.environ,COMMUNITY_DATA_DIR=str(tmp_path))
    return subprocess.run([sys.executable,str(ROOT/'reset_password.py'),email],capture_output=True,text=True,env=env,encoding='utf-8')

def test_reset_script_issues_temporary_password_and_signs_out(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    old=TestClient(app);register(old)
    assert old.get('/api/me').status_code==200
    # A lockout from wrong guesses must not block the temporary password.
    for _ in range(9):
        TestClient(app).post('/api/login',json={'email':'forgetful@example.org','password':'WrongPassword999'})
    result=run_reset(tmp_path,'Forgetful@Example.org')
    assert result.returncode==0,result.stderr
    temp=re.search(r'Temporary password: (\S+)',result.stdout).group(1)
    assert len(temp)==16 and re.search('[A-Za-z]',temp) and re.search('[0-9]',temp)
    assert old.get('/api/me').status_code==401
    fresh=TestClient(app)
    assert fresh.post('/api/login',json={'email':'forgetful@example.org','password':PW}).status_code==401
    assert fresh.post('/api/login',json={'email':'forgetful@example.org','password':temp}).status_code==200
    assert run_reset(tmp_path,'nobody@example.org').returncode!=0

def test_change_password(tmp_path):
    app=create_app(tmp_path,secret_key=Fernet.generate_key())
    a,other=TestClient(app),TestClient(app)
    h=register(a)
    assert other.post('/api/login',json={'email':'forgetful@example.org','password':PW}).status_code==200
    def change(cur,new,headers=h):
        return a.post('/api/my/password',json={'current_password':cur,'new_password':new},headers=headers)
    assert a.post('/api/my/password',json={'current_password':PW,'new_password':'BrandNewPass456'}).status_code==403  # CSRF
    assert change('WrongCurrent123','BrandNewPass456').status_code==400
    assert change(PW,'onlyletterspassword').status_code==400
    assert change(PW,'short1').status_code==422
    assert change(PW,PW).status_code==400
    assert change(PW,'BrandNewPass456').status_code==200
    assert a.get('/api/me').status_code==200        # this device stays signed in
    assert other.get('/api/me').status_code==401    # other devices are signed out
    fresh=TestClient(app)
    assert fresh.post('/api/login',json={'email':'forgetful@example.org','password':PW}).status_code==401
    assert fresh.post('/api/login',json={'email':'forgetful@example.org','password':'BrandNewPass456'}).status_code==200
    with sqlite3.connect(tmp_path/'community.db') as db:
        assert 'BrandNewPass456' not in db.execute('SELECT password_hash FROM users').fetchone()[0]
