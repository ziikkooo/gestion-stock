# Local authentication milestone

This update protects the existing catalogue routes while the new domain service remains independent. It does not implement Cosmos DB, persistent inventory storage, stock movement routes, account management, or alert delivery.

Install Flask-Login and Flask-WTF, ignore `/instance/` in Git, then run `python -m stock_manager.setup_auth` to create the `admin` and `viewer` development accounts. It generates a secret key and stores password hashes and stable user IDs in `instance/auth.json`, with file mode 0600. There are no default passwords. Without configured accounts sign-in fails closed. Do not commit or share the file. The setup command refuses to overwrite existing accounts.

`STOCK_SECRET_KEY` and `STOCK_USERS_JSON` can override local values for controlled deployment configuration. `STOCK_HTTPS_ONLY=1` enables secure session cookies; leave unset for localhost HTTP. Before cloud deployment implement persistent account storage, HTTPS-only configuration, login throttling and production server configuration. The current implementation has no self-service account registration or password recovery.

Run the full suite using `python -m pytest -v`. The legacy route tests now use authenticated requests with genuine CSRF tokens. Tests use isolated test-only credentials. Python and Jinja syntax were verified during package preparation; Flask HTTP tests need to run in the user's installed environment.
