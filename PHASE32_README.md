# Stock Manager — Phase 3.2: Stock Movements

Built on Git commit `5d17f2b` (Phase 3.1 repository bridge).

## Install

Stop the Flask dev server, then from `~/Projects/gestion-stock`:

```bash
source .venv/bin/activate
unzip -o ~/Downloads/stock-manager-phase3.2-stock-movements.zip -d .
python -m pytest -q
python -m flask --app app routes
python -m flask --app app run --debug
```

This archive changes/creates 14 files and does not touch `instance/auth.json`, `requirements.txt`, or the LaTeX report. It uses packages already installed in Phase 2.

## Pages (admin only)

- `GET /admin` — Move Stock / History buttons for each active product.
- `GET /admin/stock/P001` — Entry, Exit, Adjustment form.
- `POST /admin/stock/P001` — CSRF-protected change, redirects (303) to product history.
- `GET /admin/stock/P001/history` — read-only history, including archived products.
- `GET /admin/movements` — all movements, newest first; filter by product using `?product=P001`.

Viewer accounts cannot access these pages or submit operations. Only actor ID and username taken from the server-authenticated Flask session are recorded.

### Operation semantics

- Entry `amount=N`, N > 0 — increases the balance by N.
- Exit `amount=N`, N > 0 — decreases the balance by N; never below zero.
- Adjustment `amount=N`, N >= 0 — sets the ACTUAL counted total. A non-empty reason is mandatory and the submitted `expected_quantity` must still match the stored balance. Stale counts fail without writing a movement.
- Product creation remains the only source of Initial movements.

Each successful operation records immutable movement type, signed delta, previous and resulting balances, original product name/code snapshot, actor, UTC time, and reason. Stock and history are updated in the same atomic repository transaction.

## Manual smoke test

Log in as `admin`. Go to Administration -> Manage Products -> Move Stock next to P001 (Wireless Mouse, initially 45 units):

1. Entry 10, reason `Supplier delivery` -> 55 units and +10 in history.
2. Exit 5, reason `Order` -> 50 units and -5 in history.
3. Adjustment 47, reason `Physical count` -> 47 units and -3 in history.
4. Exit 1000 -> blocked. Quantity remains 47; no new audit row.
5. Adjustment without a reason -> blocked.
6. In the Stock Movements tab, check all six original Initial entries and the three newly created entries; filter by P001.
7. Log out; log in as viewer; administration URLs return HTTP 403.

Avoid running Flask with multiple independent worker processes until Cosmos DB persistence is added: this local repository is process memory and is not shared across workers. Restarting the app resets products and movements to the seed data. Account login configuration is separate and remains saved.

## Tests

Our independent environment can execute non-Flask code and rendered Jinja templates but does not have Flask dependencies installed. Verified here:

- 65 backend/non-Flask tests passed, including 21 new Phase 3.2 tests.
- 21 parameterized subtests passed in that subset.
- All 15 Jinja templates parsed; new admin, form and history views rendered with mock data.
- Python compilation passed.

**Please run the full test suite on your own Ubuntu system.** Given the previous 74 passing tests, the 21 new backend tests and 10 new Flask tests, about 105 tests should be collected. Do not commit until it passes and the browser workflow is verified.
