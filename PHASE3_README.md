# Phase 3.1 - Repository integration (no new UI)

The current Flask app now reads and writes products and categories through
WarehouseService and InMemoryRepository, using services/catalogue.py as a
compatibility adapter for existing templates and tests. There are no independent
mutable product/category lists anymore.

## Public IDs and internal IDs

The UI, existing routes, and forms retain P001/C001 style codes. The domain
repository holds UUID identifiers and integer-centime prices. The adapter
translates codes to UUIDs at the boundary and exposes Decimal price values
only for display (not for arithmetic).

## Initial data and audit trail

At application startup, the same five categories and six example products
are seeded through WarehouseService. Each example product gets exactly one
INITIAL movement attributed to `system-seed`. These records represent demo
initialization, NOT evidence of real historical warehouse activity.

New products created via the Flask administrator form pass the authenticated
current_user ID and username to the domain service. Direct local Catalogue
unit-test calls without a user actor are marked `local-unit-test`, not admin.

## Safety and limitations

This is a local single-process in-memory prototype. A Flask restart resets the
inventory and generated history; configured login accounts remain unchanged.
Running multiple WSGI worker processes would produce inconsistent independent
states. Do not deploy this repository to Azure as production storage.

This patch DOES NOT add stock entry, exit, adjustment, archive or movement
history web pages. Those are the next phase once route and security
regressions pass.

## Verification

Run `python -m pytest -q`. Expect 62 previous test cases plus 8 pure bridge
tests and 4 HTTP integration tests (74 total), and 16 previous subtests.
If the total differs, inspect the test discovery output; never commit broken
files or auth secrets. In particular: ensure `instance/auth.json` is ignored.
