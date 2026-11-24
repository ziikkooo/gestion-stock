"""Phase 3.3: Flask session, role, CSRF and archive UI regression tests."""
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
    return application.app.test_client(), warehouse


def signed_post(client, path, data=None, *, token=True):
    payload = dict(data or {})
    if token:
        payload['csrf_token'] = csrf(client, '/admin/archived')
    return client.post(path, data=payload)


def test_archive_list_and_buttons_work_for_admin(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    active = browser.get('/admin')
    assert active.status_code == 200
    assert b'Archived Products' in active.data
    assert b'/admin/archive/P004' in active.data
    assert b'Archive requires 0 stock' in active.data
    result = browser.get('/admin/archived')
    assert result.status_code == 200
    assert b'No archived products' in result.data


def test_archive_then_restore_changes_active_views_but_not_history(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    history_before = store.history('P004')
    result = signed_post(browser, '/admin/archive/P004')
    assert result.status_code == 303 and '/admin/archived' in result.headers['Location']
    assert store.get_product('P004') is None
    archive = browser.get('/admin/archived')
    assert archive.status_code == 200
    assert b'P004' in archive.data and b'Restore' in archive.data
    inventory = browser.get('/inventory').data
    assert b'P004' not in inventory
    assert b'Showing 5 of 5 products' in inventory
    assert browser.get('/admin/stock/P004/history').status_code == 200
    assert b'system-seed' in browser.get('/admin/stock/P004/history').data
    assert store.history('P004') == history_before
    restore = signed_post(browser, '/admin/archived/P004/restore')
    assert restore.status_code == 303 and '/admin' in restore.headers['Location']
    assert store.get_product('P004')['quantity'] == 0
    assert store.history('P004') == history_before
    assert b'P004' in browser.get('/inventory').data


def test_positive_stock_archive_rejected_with_visible_error(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    before = store.repository.read()
    result = signed_post(browser, '/admin/archive/P001')
    assert result.status_code == 409
    assert b'Only products with zero stock can be archived' in result.data
    assert store.repository.read() == before


def test_repeated_transition_returns_conflict_not_duplicate_operation(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    assert signed_post(browser, '/admin/archive/P004').status_code == 303
    result = signed_post(browser, '/admin/archive/P004')
    assert result.status_code == 409 and b'already archived' in result.data
    assert signed_post(browser, '/admin/archived/P004/restore').status_code == 303
    result = signed_post(browser, '/admin/archived/P004/restore')
    assert result.status_code == 409 and b'already active' in result.data


def test_archive_and_restore_require_post_and_valid_csrf(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    assert browser.get('/admin/archive/P004').status_code == 405
    assert browser.get('/admin/archived/P004/restore').status_code == 405
    before = store.repository.read()
    assert signed_post(browser, '/admin/archive/P004', token=False).status_code == 400
    assert browser.post('/admin/archive/P004', data={'csrf_token': 'invalid'}).status_code == 400
    assert store.repository.read() == before
    assert signed_post(browser, '/admin/archive/P004').status_code == 303
    after_archive = store.repository.read()
    assert signed_post(browser, '/admin/archived/P004/restore', token=False).status_code == 400
    assert browser.post('/admin/archived/P004/restore', data={'csrf_token': 'bad'}).status_code == 400
    assert store.repository.read() == after_archive


def test_anonymous_cannot_access_archive_pages_or_post(client):
    browser, store = client
    for path in ['/admin/archived', '/admin/archive/P004', '/admin/archived/P004/restore']:
        assert browser.get(path).status_code in {302, 405}
    assert browser.post('/admin/archive/P004').status_code in {302, 400}
    assert browser.post('/admin/archived/P004/restore').status_code in {302, 400}
    assert store.get_product('P004') is not None


def test_viewer_forbidden_even_with_valid_csrf(client):
    browser, store = client
    assert sign_in(browser, 'viewer').status_code == 303
    assert browser.get('/admin/archived').status_code == 403
    valid_csrf = csrf(browser, '/')
    assert browser.post('/admin/archive/P004', data={'csrf_token': valid_csrf}).status_code == 403
    assert browser.post('/admin/archived/P004/restore', data={'csrf_token': valid_csrf}).status_code == 403
    assert store.get_product('P004') is not None
    assert b'Archived Products' not in browser.get('/').data


def test_archived_product_cannot_use_edit_stock_routes(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    signed_post(browser, '/admin/archive/P004')
    assert browser.get('/admin/edit/P004').status_code == 404
    assert browser.get('/admin/stock/P004').status_code == 404
    assert browser.get('/admin/stock/P004/history').status_code == 200
    assert browser.get('/admin/movements?product=P004').status_code == 200


def test_unknown_product_returns_404(client):
    browser, store = client
    assert sign_in(browser).status_code == 303
    assert signed_post(browser, '/admin/archive/P999').status_code == 404
    assert signed_post(browser, '/admin/archived/P999/restore').status_code == 404
