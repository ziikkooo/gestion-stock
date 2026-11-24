# Phase 3.3 — Product Archiving and Restoration

Prerequisite: Phase 3.2 (`stock-manager-phase3.2-stock-movements.zip`) already installed.

## Features
- Administrator-only `/admin/archived` view and archive/restore POST routes.
- Archive a product **only if quantity = 0**; archive is a soft flag, never deletion.
- Archived records are absent from active Inventory, Manage Products, counts and filters.
- IDs, category links and immutable stock movement history are retained.
- Restoring brings the product back to active inventory under its original P### ID.
- Archived products are not editable and cannot receive stock movements.
- Categories cannot be deleted while assigned to an archived product.
- All state-changing web requests require valid CSRF tokens.
- Browser confirmation for archive/restore uses the existing `data-confirm` handler in categories.js.

## Try it
1. Run `python -m pytest -q` (expected existing suite plus 18 new test functions).
2. Start `python -m flask --app app run --debug`, sign in as admin.
3. Archive `P004 — Keyboard` (initial quantity 0) in Manage Products.
4. Verify Inventory now shows 5 active products and `/admin/archived` shows P004.
5. Open History for P004: initial movement is intact.
6. Restore P004: Inventory returns to 6; code, categories, quantity and history unchanged.
7. To archive a stocked item, first use a proper stock exit/adjustment to reach zero.
8. Log in as viewer: `/admin/archived` and archive/restore requests must be denied.

NOTE: An archive is a product lifecycle operation, not a stock movement. This phase
retains existing stock history; lifecycle-specific audit records (who archived/restored)
are not yet implemented. Data is still in-memory, and restarting Flask resets it.
Do not commit `instance/auth.json`, and do not edit the LaTeX report yet.
