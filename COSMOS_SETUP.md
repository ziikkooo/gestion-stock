# First Azure service — Cosmos DB for NoSQL

## 0. Before starting

You currently have **zero deployed Azure services verified**. The application can run fully in local `memory` mode without spending Azure credits. Creating a Cosmos account and provisioned container can incur charges. Check the Azure subscription's active offers/credits, region availability and free tier eligibility before provisioning.

Microsoft docs:
- https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-create-account
- https://learn.microsoft.com/en-us/azure/cosmos-db/free-tier
- https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/quickstart-python
- https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch

## 1. Azure Portal — Create Cosmos account

1. Sign into https://portal.azure.com and choose your Azure for Students subscription.
2. Create a Resource Group (e.g. `rg-stock-manager`) in your supported region.
3. Create **Azure Cosmos DB for NoSQL** (NOT MongoDB, Cassandra, PostgreSQL, etc.). Choose a unique account name and one supported region. Where eligible, explicitly enable the free-tier discount. Avoid multi-region and unnecessary extras to control cost.
4. Once deployed, open Cosmos DB account > **Keys** and copy its **URI** and **PRIMARY KEY** privately. **Never paste the key into chat/GitHub**.

## 2. Configure environment privately on Ubuntu

```bash
cd ~/Projects/gestion-stock
cp -n .env.example .env
code .env
```

Change the `.env` values to match your account, e.g.:

```bash
STOCK_BACKEND=cosmos
COSMOS_ENDPOINT=https://YOUR-ACCOUNT.documents.azure.com:443/
COSMOS_KEY=YOUR_REAL_PRIVATE_KEY
COSMOS_DATABASE=stockmanager
COSMOS_CONTAINER=warehouses
STOCK_WAREHOUSE_ID=main
STOCK_HTTPS_ONLY=0
```

Save. `.env` is excluded by `.gitignore` but must be kept private. Load it into the terminal for this session:

```bash
set -a
source .env
set +a
```

## 3. Install packages and initialize the database/container

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m stock_manager.setup_cosmos
```

This command intentionally provisions a database and a `warehouses` container with partition key `/warehouse_id` and **400 RU/s manual throughput**. Charges can apply if your account is not covered by free tier/credit. It doesn't create a Cosmos account; you must create one using the Azure Portal first.

If the database/container already exist, their configured partition key must match exactly `/warehouse_id`.

## 4. Start application with persistence

```bash
python -m pytest -q
python -m flask --app app run --debug
```

Sign in as **admin** using your existing `instance/auth.json` credentials. Add a new product or make a stock movement, and stop the server with Ctrl+C. Run:

```bash
python -m stock_manager.cosmos_check
```

This should show the modified product count and quantities. Start Flask again and verify that the inventory is **unchanged after restart**.

## 5. Restore local mode without deleting cloud data

```bash
export STOCK_BACKEND=memory
python -m flask --app app run --debug
```

A new local-memory warehouse starts with six seeded demo products. This **does not remove** anything in Cosmos DB.

## Troubleshooting

- `ModuleNotFoundError: azure` → `python -m pip install -r requirements.txt` in your active `.venv`.
- `401/403` → check URI and secret key in `.env`; do not share secrets.
- `404` → run `python -m stock_manager.setup_cosmos` to create database/container.
- `429` → Cosmos throttling; wait and retry or inspect RU usage and account limits.
- Connection blocked → review Cosmos account networking/firewall settings and Azure service health.
- App startup must **fail loudly** if Cosmos configuration is wrong; it must never silently switch to memory or pretend persistence works.
- Current design has a size/performance limit (one warehouse state document, ~1.7 MiB); suitable for a coursework demonstration with a small catalogue, not a production deployment.

## Security and deployment reminders

- The local `instance/auth.json` is NOT copied into cloud hosting. Before App Service deployment, use App Service settings / secret-management facilities to provide `STOCK_SECRET_KEY`, `STOCK_USERS_JSON` and Cosmos access securely.
- `STOCK_HTTPS_ONLY=1` must be enabled behind real HTTPS for secure session cookies; never expose Flask `--debug` to the public internet.
- Configure billing alerts and review Azure costs.
