"""Read-only Cosmos persistence check (no prints of credentials)."""
import os


def main():
    if os.environ.get("STOCK_BACKEND", "").lower() != "cosmos":
        raise SystemExit("Run in Cosmos mode: export STOCK_BACKEND=cosmos")
    from .cosmos_repository import repository_from_environment
    repo = repository_from_environment()
    state = repo.read()
    print("Cosmos warehouse connection: OK")
    print("Warehouse ID:", repo.warehouse_id)
    print("Categories:", len(state.categories))
    print("Products:", len(state.products))
    print("Archived:", sum(p.archived for p in state.products.values()))
    print("Movements:", len(state.movements))
    for product in sorted(state.products.values(), key=lambda p: p.code):
        print(f"  {product.code}: {product.name} — {product.quantity} units{' [archived]' if product.archived else ''}")


if __name__ == "__main__":
    main()
