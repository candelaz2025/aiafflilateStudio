from fastapi.testclient import TestClient
from community_app import create_app
from studio_v6.shopee_user_import import pasted_preview, report_preview, allowed_link

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PWD='StronglySecurePass123!'

def signup(client,username):
    r=client.post('/api/register',json={'username':username,'email':username+'@example.test','password':PWD})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}

def test_paste_parse_honest_extra_comm_and_link():
    d=pasted_preview('แก้วเก็บความเย็น 900ml\nราคา ฿299\nExtra Comm 8%\nhttps://s.shopee.co.th/abc')
    p=d['items'][0]
    assert p['title']=='แก้วเก็บความเย็น 900ml' and p['url']=='https://s.shopee.co.th/abc'
    assert p['extra_comm_rate_hint']==8 and p['price']==299 and p['verification']=='unverified'
    assert p['orders'] is None and p['commission_baht'] is None

def test_reject_phishing_and_untrusted_shopee_domain():
    for url in ('https://shopee.co.th.evil.test/a','http://shopee.co.th/a','https://user:pw@shopee.co.th/a','https://evil.test/x'):
        assert allowed_link(url)==''
    assert allowed_link('https://shopee.co.th/product/1/2')
    try:pasted_preview('สินค้าทดสอบ\nhttps://shopee.co.th.evil.test/foo')
    except ValueError: pass
    else: assert False

def test_csv_parsing_and_missing_product_name():
    csvtext='ชื่อสินค้า,ลิงก์สินค้า,จำนวนออเดอร์,ค่าคอมมิชชั่น\nแก้วเก็บความเย็น,https://shopee.co.th/product/1/2,3,12.50\nสินค้าไม่มีลิงก์,,1,3\n'
    d=report_preview(csvtext.encode('utf-8-sig'),'report.csv')
    assert len(d['items'])==2 and d['items'][0]['orders']==3
    assert d['items'][0]['commission_baht']==12.5 and d['items'][0]['verification']=='unverified'
    try:report_preview('วันที่,ยอดรวม\n2026-10-20,900\n'.encode(),'summary.csv')
    except ValueError:pass
    else: assert False

def test_signed_in_only_and_cannot_cross_accounts(tmp_path):
    a=TestClient(create_app(tmp_path,secret_key=KEY));b=TestClient(create_app(tmp_path,secret_key=KEY))
    ah=signup(a,'user_a');bh=signup(b,'user_b')
    payload={'content':'แก้วเก็บความเย็น\nExtra Comm 7%\nhttps://s.shopee.co.th/abc'}
    assert a.post('/api/my/shopee/preview',json=payload).status_code==403
    assert TestClient(create_app(tmp_path,secret_key=KEY)).post('/api/my/shopee/preview',json=payload).status_code==401
    r=a.post('/api/my/shopee/preview',json=payload,headers=ah)
    assert r.status_code==200,r.text
    item=r.json()['items'][0]
    assert a.post('/api/my/products',headers=ah,json={'title':item['title'],'url':item['url'],'platform':'shopee','extra_comm_checked':False}).status_code==200
    assert a.get('/api/my/products').json()[0]['extra_comm_checked']==0
    assert b.get('/api/my/products').json()==[]
    csv=b'Product Name,Product Link,Order Count,Commission\nCup,https://s.shopee.co.th/aaa,2,10\n'
    assert b.post('/api/my/shopee/report-preview',files={'file':('report.csv',csv,'text/csv')},headers=bh).status_code==200
    assert a.post('/api/my/shopee/report-preview',files={'file':('report.csv',csv,'text/csv')}).status_code==403
    assert len(a.get('/api/my/products').json())==1
    assert b.get('/api/my/products').json()==[]

def test_reject_oversized_and_non_csv(tmp_path):
    c=TestClient(create_app(tmp_path,secret_key=KEY));headers=signup(c,'user_c')
    assert c.post('/api/my/shopee/preview',json={'content':'x'*12001},headers=headers).status_code==422
    assert c.post('/api/my/shopee/report-preview',files={'file':('bad.exe',b'unsafe','application/octet-stream')},headers=headers).status_code==400
    assert c.post('/api/my/shopee/report-preview',files={'file':('long.csv',b'x'*(2*1024*1024+4),'text/csv')},headers=headers).status_code==400
