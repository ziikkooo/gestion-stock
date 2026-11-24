# Stock Manager — Flask + Azure Cosmos DB (first Azure service)

This is the consolidated, tested course-project source for the **first Azure service: Azure Cosmos DB for NoSQL**.

### Included

- Administrator and viewer logins (no public registration); protected Flask sessions and CSRF.
- Inventory, categories (multiple per product), search, filters, product create/edit.
- Stock entry, exit, adjustment, and append-only movement history with actor and UTC timestamp.
- Product archiving/restoration with preserved history.
- Optional Azure Cosmos DB persistence using ETag optimistic concurrency.
- Six initial demo products and five categories, seeded **once per warehouse**.

### Local mode (no Azure account required)

```bash
cd ~/Projects/gestion-stock
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m stock_manager.setup_auth   # only once, if no accounts created
python -m pytest -q
python -m flask --app app run --debug
```

Open http://127.0.0.1:5000 and log in with the admin/viewer credentials you chose. **Memory mode resets stock on Flask restart.**

### Azure Cosmos DB (first cloud service)

See [COSMOS_SETUP.md](COSMOS_SETUP.md) for the account setup, pricing considerations and validation commands.

### Architecture and limitations

`app.py` → `services/catalogue.py` → `stock_manager/service.py` → `InMemoryRepository` or `CosmosWarehouseRepository`.

Cosmos uses one versioned JSON document per **small warehouse demo**, containing all products, categories and movement history. Updates replace the document with an **If-Match ETag** so an operation commits the balance and movement together, or retries on an ETag conflict. It is intentionally capped at ~1.7 MiB and is **not suitable for a large production warehouse**; larger deployments require a multi-document partitioned design and transactional batches. Authentication remains in `instance/auth.json` (local only), or environment-provided accounts; it is **not** yet integrated with a cloud identity provider. App Service, Azure Functions, Logic Apps, Storage, email alerts, dashboards and deployment are **future phases**, not included as implemented services.

Never commit `.env`, `instance/auth.json`, any Azure key or real customer data. Do not run Flask's debug server as a public production server.
