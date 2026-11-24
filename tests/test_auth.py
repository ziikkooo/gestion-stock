"""Authentication, access control and CSRF regression tests."""
import pytest
from app import app
from auth_helpers import TEST_CONFIG, PASSWORD, csrf, sign_in


@pytest.fixture
def client(monkeypatch):
    for k, v in TEST_CONFIG.items():
        monkeypatch.setitem(app.config, k, v)
    return app.test_client()


@pytest.mark.parametrize('path', ['/', '/inventory', '/admin', '/admin/add', '/admin/categories', '/admin/edit/P001'])
def test_anonymous_redirected(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_valid_login(client):
    response = sign_in(client)
    assert response.status_code == 303
    assert client.get('/admin').status_code == 200
    assert client.get('/inventory').status_code == 200
    assert b'Admin panel' in client.get('/').data


@pytest.mark.parametrize('username,password', [('admin', 'wrong-password'), ('unknown', PASSWORD)])
def test_invalid_login(client, username, password):
    response = sign_in(client, username, password)
    assert response.status_code == 401
    assert b'Invalid username or password.' in response.data
    assert client.get('/inventory').status_code == 302


def test_viewer_can_read_but_not_admin(client):
    assert sign_in(client, 'viewer').status_code == 303
    assert client.get('/inventory').status_code == 200
    page = client.get('/').data
    assert b'Admin panel' not in page and b'href="/admin"' not in page
    assert client.get('/admin').status_code == 403
    assert client.get('/admin/categories').status_code == 403
    assert client.get('/admin/edit/P001').status_code == 403
    assert client.post('/admin/categories', data={'name': 'Forbidden', 'csrf_token': csrf(client)}).status_code == 403


def test_login_requires_csrf(client):
    assert client.post('/login', data={'username': 'admin', 'password': PASSWORD}).status_code == 400
    assert client.get('/').status_code == 302


@pytest.mark.parametrize('path', ['/admin/add', '/admin/categories', '/admin/categories/C001/rename', '/admin/categories/C001/delete', '/admin/edit/P001', '/logout'])
def test_mutating_routes_require_csrf(client, path):
    assert sign_in(client).status_code == 303
    assert client.post(path, data={}).status_code == 400
    assert client.post(path, data={'csrf_token': 'invalid'}).status_code == 400


def test_logout_is_post_and_invalidates_access(client):
    assert sign_in(client).status_code == 303
    assert client.get('/logout').status_code == 405
    assert client.post('/logout', data={'csrf_token': csrf(client)}).status_code == 303
    assert client.get('/admin').status_code == 302


def test_session_cookie_flags(client):
    response = sign_in(client)
    cookie = response.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert client.get('/inventory').headers['Cache-Control'] == 'no-store'


def test_login_ignores_external_redirect(client):
    response = client.post('/login?next=https://example.invalid', data={
        'username': 'admin', 'password': PASSWORD, 'csrf_token': csrf(client, '/login')})
    assert response.status_code == 303 and response.headers['Location'] == '/'
