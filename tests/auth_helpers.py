"""Test-only identities and form helper. Never use these passwords outside tests."""
import re
from werkzeug.security import generate_password_hash

PASSWORD = 'test-only-password-123'
_HASH = generate_password_hash(PASSWORD)
TEST_CONFIG = {
    'TESTING': True, 'SECRET_KEY': 'test-only-secret-not-for-deployment-123456789',
    'SESSION_COOKIE_SECURE': False, 'WTF_CSRF_ENABLED': True,
    'STOCK_USERS': {
        'test-admin': {'username': 'admin', 'password_hash': _HASH, 'role': 'admin', 'active': True},
        'test-viewer': {'username': 'viewer', 'password_hash': _HASH, 'role': 'user', 'active': True},
    },
}


def csrf(client, path='/'):
    response = client.get(path)
    assert response.status_code == 200
    token = re.search(rb'name="csrf_token" value="([^\"]+)"', response.data)
    assert token is not None, 'Missing CSRF field in rendered page'
    return token.group(1).decode()


def sign_in(client, username='admin', password=PASSWORD):
    return client.post('/login', data={'username': username, 'password': password,
                                      'csrf_token': csrf(client, '/login')})
