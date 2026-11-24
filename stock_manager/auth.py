"""Flask session authentication and authorization; local configuration for now."""
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
import json
import os
from pathlib import Path
import secrets

from flask import abort, current_app, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass(frozen=True)
class User(UserMixin):
    id: str
    username: str
    role: str


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def configure_auth(app):
    config_path = Path(app.instance_path) / 'auth.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    users = json.loads(os.environ['STOCK_USERS_JSON']) if 'STOCK_USERS_JSON' in os.environ else config.get('users', {})
    secret = os.environ.get('STOCK_SECRET_KEY') or config.get('secret_key')
    if users and (not isinstance(secret, str) or len(secret) < 32):
        raise RuntimeError('Configure a secret key of at least 32 characters before enabling accounts.')
    https_only = os.environ.get('STOCK_HTTPS_ONLY') == '1'
    app.config.update(
        SECRET_KEY=secret or secrets.token_hex(32),
        STOCK_USERS=users,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=https_only,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
    )
    manager = LoginManager(app)
    manager.login_view = 'login'
    manager.session_protection = 'strong'
    dummy_hash = generate_password_hash(secrets.token_hex(32))

    @manager.user_loader
    def load_user(user_id):
        record = current_app.config['STOCK_USERS'].get(user_id)
        if not record or not record.get('active', True) or record['role'] not in {'admin', 'user'}:
            return None
        return User(user_id, record['username'], record['role'])

    @app.before_request
    def require_authentication():
        if request.endpoint in {'login', 'static'}:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        # Defense in depth for current and future administration paths.
        if (request.path == '/admin' or request.path.startswith('/admin/')) and current_user.role != 'admin':
            abort(403)
        return None

    # CSRF is enabled globally for all state-changing methods.
    CSRFProtect(app)

    @app.after_request
    def prevent_sensitive_caching(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('home'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().casefold()
            password = request.form.get('password', '')
            if len(username) > 100 or len(password) > 256:
                return render_template('login.html', error='Invalid username or password.'), 401
            match = next(((uid, record) for uid, record in current_app.config['STOCK_USERS'].items()
                          if record['username'].casefold() == username), None)
            password_hash = match[1]['password_hash'] if match else dummy_hash
            valid = check_password_hash(password_hash, password)
            user = load_user(match[0]) if match else None
            if not valid or user is None:
                return render_template('login.html', error='Invalid username or password.'), 401
            session.clear()
            login_user(user, remember=False)
            # No untrusted redirect parameter is honored.
            return redirect(url_for('home'), code=303)
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        logout_user()
        session.clear()
        return redirect(url_for('login'), code=303)

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('access_error.html', heading='Access denied',
                               message='You do not have permission to access this page.'), 403

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('access_error.html', heading='Request rejected',
                               message='Your security token is missing or expired. Reopen the form and try again.'), 400
