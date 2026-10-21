"""Editing a product covers every field the add form collects."""
import io, sqlite3
import pytest
from fastapi.testclient import TestClient
KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 120

@pytest.fixture
def c(tmp_path):
    from community_app import create_app
    cl = TestClient(create_app(tmp_path, secret_key=KEY))
    r = cl.post('/api/register', json={'username':'kev','email':'k@e.com','password':'SecretPass12345'})
    return cl, {'X-CSRF-Token': r.json()['csrf']}, tmp_path

def add(cl, h, **kw):
    d = {'title':'พัดลมพกพา ไร้ใบพัด','url':'https://s.shopee.co.th/abc','platform':'shopee',
         'price':'199','commission_rate':'10','image_url':''}
    d.update(kw)
    r = cl.post('/api/my/products/manual', headers=h, data=d)
    assert r.status_code == 200, r.text
    return r.json()['id']

def get(cl, pid):
    return [p for p in cl.get('/api/my/products').json() if p['id']==pid][0]

def test_edit_every_field(c):
    cl,h,_ = c
    pid = add(cl,h)
    r = cl.put(f'/api/my/products/{pid}/manual', headers=h, data={
        'title':'พัดลมตั้งโต๊ะ USB รุ่นใหม่','url':'https://s.shopee.co.th/zzz','platform':'tiktok',
        'price':'349.50','commission_rate':'12.5','image_url':'https://cf.shopee.co.th/file/x.jpg','keep_image':'1'})
    assert r.status_code == 200, r.text
    p = get(cl,pid)
    assert p['title']=='พัดลมตั้งโต๊ะ USB รุ่นใหม่' and p['price']==349.5
    assert p['commission_rate']==12.5 and round(p['commission_baht'],2)==43.69
    assert p['offer_link']=='https://s.shopee.co.th/zzz'

def test_price_only_edit_keeps_the_photo(c):
    cl,h,tmp = c
    r = cl.post('/api/my/products/manual', headers=h,
                data={'title':'ของทดสอบมีรูป','platform':'shopee','price':'99','commission_rate':'5'},
                files={'image':('a.png', io.BytesIO(PNG), 'image/png')})
    pid = r.json()['id']
    before = get(cl,pid)['image_path']
    assert before, 'uploaded image should be served'
    cl.put(f'/api/my/products/{pid}/manual', headers=h,
           data={'title':'ของทดสอบมีรูป','platform':'shopee','price':'149','commission_rate':'5','keep_image':'1'})
    after = get(cl,pid)
    assert after['price']==149 and after['image_path']==before, 'editing the price must not drop the image'

def test_replacing_the_image_removes_the_old_file(c):
    cl,h,tmp = c
    r = cl.post('/api/my/products/manual', headers=h, data={'title':'สินค้ามีรูปเดิม','platform':'shopee'},
                files={'image':('a.png', io.BytesIO(PNG), 'image/png')})
    pid = r.json()['id']
    old = get(cl,pid)['image_path'].rsplit('/',1)[-1]
    cl.put(f'/api/my/products/{pid}/manual', headers=h, data={'title':'สินค้ามีรูปเดิม','platform':'shopee','keep_image':'1'},
           files={'image':('b.png', io.BytesIO(PNG+b'x'), 'image/png')})
    new = get(cl,pid)['image_path'].rsplit('/',1)[-1]
    assert new != old
    assert not (tmp/'media'/'products'/old).exists(), 'the replaced file should not linger'

def test_validation_matches_the_add_form(c):
    cl,h,_ = c
    pid = add(cl,h)
    bad = cl.put(f'/api/my/products/{pid}/manual', headers=h, data={'title':'ab','platform':'shopee'})
    assert bad.status_code==400 and '3-200' in bad.json()['detail']
    bad2 = cl.put(f'/api/my/products/{pid}/manual', headers=h, data={'title':'ชื่อถูกต้อง','platform':'shopee','price':'abc'})
    assert bad2.status_code==400 and 'ตัวเลข' in bad2.json()['detail']
    bad3 = cl.put(f'/api/my/products/{pid}/manual', headers=h, data={'title':'ชื่อถูกต้อง','platform':'mars'})
    assert bad3.status_code==400
    assert cl.put(f'/api/my/products/{pid}/manual', data={'title':'ชื่อถูกต้อง','platform':'shopee'}).status_code==403

def test_cannot_edit_someone_elses_product(c):
    cl,h,tmp = c
    pid = add(cl,h)
    from community_app import create_app
    other = TestClient(create_app(tmp, secret_key=KEY))
    r = other.post('/api/register', json={'username':'mal','email':'m@e.com','password':'SecretPass12345'})
    ho = {'X-CSRF-Token': r.json()['csrf']}
    assert other.put(f'/api/my/products/{pid}/manual', headers=ho,
                     data={'title':'ยึดสินค้า','platform':'shopee'}).status_code == 404
