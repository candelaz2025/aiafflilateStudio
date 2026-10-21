"""Import products from a user-supplied CSV / Excel file (no Shopee login, no cookies)."""
import io
import openpyxl
import pytest
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


@pytest.fixture
def client(tmp_path):
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}


def _csv():
    return ('﻿ชื่อสินค้า,ราคา,ลิงก์ affiliate,รหัสสินค้า\n'
            'หูฟัง TWS,199,https://s.shopee.co.th/abc,111\n'
            'เซรั่ม,390,https://evil.com/x,222\n'
            'Total,,,\n').encode('utf-8')


def test_preview_guesses_columns(client):
    c, h = client
    r = c.post('/api/my/products/import-file/preview', headers=h,
               files={'file': ('p.csv', _csv(), 'text/csv')})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['total'] == 3 and j['guess']['title'] == 'ชื่อสินค้า' and j['guess']['item_id'] == 'รหัสสินค้า'


def test_commit_inserts_dedups_and_filters_links(client):
    c, h = client
    mp = '{"title":"ชื่อสินค้า","price":"ราคา","aff_link":"ลิงก์ affiliate","item_id":"รหัสสินค้า"}'
    r = c.post('/api/my/products/import-file/commit', headers=h,
               data={'mapping': mp, 'download_images': '0'},
               files={'file': ('p.csv', _csv(), 'text/csv')}).json()
    assert r['added'] == 2 and r['skipped'] == 1  # "Total" row skipped
    prods = c.get('/api/my/products').json()
    assert len(prods) == 2
    tws = next(p for p in prods if p['title'] == 'หูฟัง TWS')
    assert tws['price'] == 199 and tws['source'] == 'file_import' and tws['offer_link'] == 'https://s.shopee.co.th/abc'
    serum = next(p for p in prods if p['title'] == 'เซรั่ม')
    assert serum['offer_link'] == ''  # evil.com link dropped
    # re-import updates in place (same item_id), no duplicates
    r2 = c.post('/api/my/products/import-file/commit', headers=h,
                data={'mapping': mp, 'download_images': '0'},
                files={'file': ('p.csv', _csv(), 'text/csv')}).json()
    assert r2['added'] == 0 and r2['updated'] == 2
    assert len(c.get('/api/my/products').json()) == 2


def test_xlsx_import(client):
    c, h = client
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(['ชื่อสินค้า', 'ราคา', 'อัตราค่าคอมมิชชัน'])
    ws.append(['ครีมกันแดด', 250, '8'])
    buf = io.BytesIO(); wb.save(buf)
    pv = c.post('/api/my/products/import-file/preview', headers=h,
                files={'file': ('x.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}).json()
    assert pv['guess']['commission_rate'] == 'อัตราค่าคอมมิชชัน'
    r = c.post('/api/my/products/import-file/commit', headers=h,
               data={'mapping': '{"title":"ชื่อสินค้า","price":"ราคา","commission_rate":"อัตราค่าคอมมิชชัน"}', 'download_images': '0'},
               files={'file': ('x.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}).json()
    assert r['added'] == 1
    p = c.get('/api/my/products').json()[0]
    assert p['commission_rate'] == 8 and p['commission_baht'] == 20  # 250*8%


def test_title_required_and_empty_rejected(client):
    c, h = client
    assert c.post('/api/my/products/import-file/commit', headers=h,
                  data={'mapping': '{}', 'download_images': '0'},
                  files={'file': ('p.csv', _csv(), 'text/csv')}).status_code == 400
    assert c.post('/api/my/products/import-file/preview', headers=h,
                  files={'file': ('e.csv', b'a,b\n', 'text/csv')}).status_code == 400
