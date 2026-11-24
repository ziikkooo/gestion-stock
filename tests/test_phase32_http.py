"""Phase 3.2: full Flask, CSRF and role regression tests."""
import pytest
import app as application
from auth_helpers import TEST_CONFIG, csrf, sign_in
from services.catalogue import Catalogue


@pytest.fixture
def client(monkeypatch):
    warehouse = Catalogue()
    monkeypatch.setattr(application, 'catalogue', warehouse)
    for key, value in TEST_CONFIG.items():
        monkeypatch.setitem(application.app.config, key, value)
    yield application.app.test_client(), warehouse


def post(browser, path, data, *, with_csrf=True):
    payload = dict(data)
    if with_csrf:
        payload['csrf_token'] = csrf(browser, path)
    return browser.post(path, data=payload)


def test_stock_pages_protected_from_anonymous_visitors(client):
    browser, warehouse = client
    for path in ['/admin/stock/P001', '/admin/stock/P001/history', '/admin/movements']:
        response = browser.get(path)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']


def test_stock_pages_and_posts_forbidden_to_viewer(client):
    browser, warehouse = client
    assert sign_in(browser, 'viewer').status_code == 303
    for path in ['/admin/stock/P001', '/admin/stock/P001/history', '/admin/movements']:
        assert browser.get(path).status_code == 403
    response = browser.post('/admin/stock/P001', data={
        'kind': 'entry', 'amount': '5', 'actor': 'admin',
        'csrf_token': csrf(browser, '/'),
    })
    assert response.status_code == 403
    assert warehouse.get_product('P001')['quantity'] == 45
    assert len(warehouse.movement_rows()) == 6


def test_admin_pages_show_initial_history_and_navigation(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    admin_html = browser.get('/admin').data
    assert b'Move Stock' in admin_html and b'History' in admin_html
    form = browser.get('/admin/stock/P001')
    assert form.status_code == 200
    assert b'Wireless Mouse' in form.data
    assert b'expected_quantity' in form.data
    h = browser.get('/admin/stock/P001/history')
    assert h.status_code == 200
    assert b'system-seed' in h.data
    all_ = browser.get('/admin/movements')
    assert all_.status_code == 200
    assert b'6 records' in all_.data
    assert b'P001' in all_.data


def test_admin_entry_records_session_actor_and_updates_inventory(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    r = post(browser, '/admin/stock/P001', {
        'kind': 'entry', 'amount': '10', 'reason': 'Supplier delivered',
        'expected_quantity': '45', 'actor': 'forged-admin',
    })
    assert r.status_code == 303
    assert '/admin/stock/P001/history' in r.headers['Location']
    assert warehouse.get_product('P001')['quantity'] == 55
    row = warehouse.movement_rows('P001')[0]
    assert (row['kind'], row['delta'], row['resulting_quantity'], row['actor']) == ('entry',10,55,'admin')
    assert row['reason'] == 'Supplier delivered'
    assert warehouse.history('P001')[-1].actor_id == 'test-admin'
    assert b'55' in browser.get('/inventory').data


def test_exit_and_adjustment_and_history_filter(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    assert post(browser, '/admin/stock/P001', {'kind': 'exit', 'amount': '5', 'reason': ''}).status_code == 303
    assert warehouse.get_product('P001')['quantity'] == 40
    assert post(browser, '/admin/stock/P001', {
        'kind': 'adjustment', 'amount': '3', 'reason': 'Physical count', 'expected_quantity': '40',
    }).status_code == 303
    assert warehouse.get_product('P001')['quantity'] == 3
    assert warehouse.statistics()['low_stock'] == 3
    records = browser.get('/admin/movements?product=P001').data
    assert b'3 records' in records
    assert b'Physical count' in records
    assert b'P002' not in records.split(b'<tbody>')[1].split(b'</tbody>')[0]


def test_invalid_moves_do_not_modify_stock_or_history(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    before = warehouse.repository.read()
    bad = [
        {'kind':'initial','amount':'5'}, {'kind':'entry','amount':'0'},
        {'kind':'exit','amount':'1000'}, {'kind':'entry','amount':'1e3'},
        {'kind':'adjustment','amount':'6','expected_quantity':'45'},
        {'kind':'adjustment','amount':'6','expected_quantity':'44','reason':'Counted'},
        {'kind':'adjustment','amount':'45','expected_quantity':'45','reason':'Unchanged'},
    ]
    for data in bad:
        response = post(browser, '/admin/stock/P001', data)
        assert response.status_code == 400, (data, response.status_code)
        assert warehouse.repository.read() == before


def test_csrf_required_for_stock_changes(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    response = browser.post('/admin/stock/P001', data={'kind':'entry', 'amount':'10'})
    assert response.status_code == 400
    assert warehouse.get_product('P001')['quantity'] == 45


def test_stale_adjustment_detected_between_get_and_post(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    assert browser.get('/admin/stock/P001').status_code == 200
    assert post(browser, '/admin/stock/P001', {'kind': 'entry', 'amount':'1'}).status_code == 303
    response = post(browser, '/admin/stock/P001', {
        'kind':'adjustment','amount':'20','expected_quantity':'45','reason':'Counted'
    })
    assert response.status_code == 400
    assert b'Stock changed since counting' in response.data
    assert warehouse.get_product('P001')['quantity'] == 46
    assert len(warehouse.movement_rows('P001')) == 2


def test_unknown_products_404(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    for path in ['/admin/stock/P999', '/admin/stock/P999/history', '/admin/movements?product=P999']:
        assert browser.get(path).status_code == 404


def test_archived_product_history_remains_readable(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    uid = warehouse._product_uuid('P004')
    warehouse.service.set_archived(uid, True)
    assert browser.get('/admin/stock/P004').status_code == 404
    h = browser.get('/admin/stock/P004/history')
    assert h.status_code == 200
    assert b'Archived' in h.data
    assert b'system-seed' in h.data
    assert browser.get('/admin/movements?product=P004').status_code == 200
