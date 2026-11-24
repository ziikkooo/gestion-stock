# START HERE — Consolidated Stock Manager (up to first Azure service)

**First Azure service:** Azure Cosmos DB for NoSQL. None has been deployed by this ZIP; you must create the Azure account resource from the Portal.

### 1 — Preserve your current project first

Open your Ubuntu terminal, stop Flask (Ctrl+C), then:

```bash
cd ~/Projects/gestion-stock
source .venv/bin/activate
git status --short
```

If you have uncommitted code, keep a backup/commit before overwriting. Your existing `.git` history and `docs/rapport/` are not inside this ZIP and will not be overwritten. Never upload `instance/auth.json` or your `.env`.

### 2 — Install the whole application source

```bash
unzip -o ~/Downloads/stock-manager-complete-to-cosmos.zip -d .
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

This ZIP supersedes all the old partial update ZIP files.

### 3 — Run locally without Azure

```bash
python -m stock_manager.setup_auth  # only if instance/auth.json does not exist
python -m flask --app app run --debug
```

Open http://127.0.0.1:5000, sign in as `admin` with your own chosen password. Default local in-memory stock resets on restart.

### 4 — First Azure cloud service

Read [COSMOS_SETUP.md](COSMOS_SETUP.md). Create an **Azure Cosmos DB for NoSQL** account in Azure Portal, create a private `.env` using `.env.example`, and then:

```bash
set -a
source .env
set +a
python -m stock_manager.setup_cosmos
python -m flask --app app run --debug
```

Add a product or make a movement, stop Flask, and run:

```bash
python -m stock_manager.cosmos_check
```

Restart Flask: data should persist. The full test suite is **forced to local-memory mode** for safety so it cannot modify your cloud inventory.

### 5 — If tests fail

Paste the complete `python -m pytest -q` output into chat. Do not commit the update until it passes on Ubuntu.

### Important scope

**Implemented source:** authentication, categories, products, inventory, stock movements, history, archiving, Cosmos persistence adapter, setup and tests.
**Not implemented:** Azure App Service deployment, Azure Functions, Logic Apps, Azure Storage, automatic notifications, dashboard analytics, cloud identity/security hardening, and updated LaTeX report.

**Cosmos demo limitation:** The repository stores the entire small warehouse in a single versioned document (maximum application size ~1.7 MiB), with ETag conditional updates. This preserves atomic stock+history for the class demo but does not scale to large warehouses.
