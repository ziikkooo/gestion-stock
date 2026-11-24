"""Create two local development accounts without storing plaintext passwords."""
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4
from werkzeug.security import generate_password_hash


def password_for(username):
    while True:
        password = getpass(f'Choose a password for {username} (12+ characters): ')
        confirm = getpass('Confirm password: ')
        if password != confirm:
            print('Passwords do not match.')
        elif not 12 <= len(password) <= 256:
            print('Use 12 to 256 characters.')
        else:
            return generate_password_hash(password)


def main():
    path = Path(__file__).resolve().parent.parent / 'instance' / 'auth.json'
    if path.exists():
        raise SystemExit('Accounts already configured. Existing credentials were not changed.')
    path.parent.mkdir(mode=0o700, exist_ok=True)
    users = {}
    for username, role in [('admin', 'admin'), ('viewer', 'user')]:
        users[str(uuid4())] = {'username': username, 'role': role, 'active': True,
                              'password_hash': password_for(username)}
    config = {'secret_key': secrets.token_hex(32), 'users': users}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(config, stream, indent=2)
    print('Local accounts created: admin and viewer. Passwords were hashed, not stored in plaintext.')


if __name__ == '__main__':
    main()
