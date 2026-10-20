"""Donation is bank-transfer instructions plus manual review, never payment processing."""
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from community_app import create_app

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='

def make(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    return TestClient(app),TestClient(app)

def signup(client,name):
    r=client.post('/api/register',json={'username':name,'email':name+'@example.com','password':'SecurePassword2026'})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def test_public_bank_details_and_donation_page(tmp_path):
    a,b=make(tmp_path)
    r=a.get('/donate')
    assert r.status_code==200
    assert 'สนับสนุนการพัฒนา' in r.text
    d=b.get('/api/donate/info')
    assert d.status_code==200
    j=d.json()
    assert j['bank']=='ธนาคารไทยพาณิชย์ (SCB)'
    assert j['account_number']=='4210116946'
    assert j['account_name']=='นาย กฤตลักษณ์ สุขใส'
    assert 'ลดหย่อนภาษี' in j['notice']
    assert '<a class="support-link" href="/donate">' in a.get('/').text
    assert a.get('/api/my/donation-reports').status_code==401
    assert a.get('/api/admin/donation-reports').status_code==401

def test_donation_validation_and_reporting(tmp_path):
    a,b=make(tmp_path)
    ca=signup(a,'alice');cb=signup(b,'bob')
    payload={'amount_baht':'125.50','note':'Test voluntary transfer'}
    assert a.post('/api/my/donation-reports',json=payload).status_code==403
    result=a.post('/api/my/donation-reports',json=payload,headers=ca)
    assert result.status_code==200,result.text
    assert result.json()['status']=='pending'
    assert 'ไม่ใช่หลักฐาน' in result.json()['message']
    mine=a.get('/api/my/donation-reports').json()
    assert len(mine)==1 and mine[0]['amount_satang']==12550
    assert mine[0]['status']=='pending'
    assert b.get('/api/my/donation-reports').json()==[]
    assert b.get('/api/admin/donation-reports').status_code==403
    assert b.patch('/api/admin/donation-reports/'+str(result.json()['id']),json={'status':'confirmed'},headers=cb).status_code==403
    for invalid in ['0','-5','1000000.01','9.999','nan']:
        assert a.post('/api/my/donation-reports',json={'amount_baht':invalid,'note':''},headers=ca).status_code==422
    assert a.post('/api/my/donation-reports',json={'amount_baht':'1','note':'x'*201},headers=ca).status_code==422

def test_admin_review_and_one_way_confirmation(tmp_path):
    admin,member=make(tmp_path)
    ca=signup(admin,'owner');cm=signup(member,'member')
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username='owner'")
    report=member.post('/api/my/donation-reports',json={'amount_baht':'850.00','note':'โอนเงินเพื่อพัฒนา'},headers=cm)
    assert report.status_code==200
    report_id=report.json()['id']
    review=admin.get('/api/admin/donation-reports')
    assert review.status_code==200 and len(review.json())==1
    assert review.json()[0]['member']=='member'
    assert review.json()[0]['amount_satang']==85000
    assert admin.patch(f'/api/admin/donation-reports/{report_id}',json={'status':'confirmed'}).status_code==403
    assert admin.patch(f'/api/admin/donation-reports/{report_id}',json={'status':'pending'},headers=ca).status_code==400
    ok=admin.patch(f'/api/admin/donation-reports/{report_id}',json={'status':'confirmed'},headers=ca)
    assert ok.status_code==200,ok.text
    assert ok.json()['status']=='confirmed'
    assert member.get('/api/my/donation-reports').json()[0]['status']=='confirmed'
    assert admin.patch(f'/api/admin/donation-reports/{report_id}',json={'status':'rejected'},headers=ca).status_code==409
    assert admin.patch('/api/admin/donation-reports/9999',json={'status':'confirmed'},headers=ca).status_code==409
    assert admin.get('/api/admin/donation-reports').json()[0]['status']=='confirmed'
    assert 'credentials' not in admin.get('/api/admin/donation-reports').text

def test_existing_v7_data_survives_upgrade(tmp_path):
    first=create_app(tmp_path,secret_key=KEY)
    client=TestClient(first)
    reg=client.post('/api/register',json={'username':'retained','email':'old@example.com','password':'SecurePassword2026'})
    assert reg.status_code==200
    second=create_app(tmp_path,secret_key=KEY)
    newer=TestClient(second)
    assert newer.post('/api/login',json={'email':'old@example.com','password':'SecurePassword2026'}).status_code==200
    assert newer.get('/api/donate/info').json()['account_number']=='4210116946'
