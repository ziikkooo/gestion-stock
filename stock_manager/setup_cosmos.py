"""One-time opt-in creation of the database/container in an existing Cosmos account.

Requires COSMOS_ENDPOINT and COSMOS_KEY (environment variables). Does not
create the Azure resource itself. Review Azure pricing before running.
"""
from __future__ import annotations
import os


def main():
    from azure.cosmos import CosmosClient, PartitionKey
    from .cosmos_repository import CosmosWarehouseRepository

    endpoint = os.environ.get("COSMOS_ENDPOINT", "").strip()
    key = os.environ.get("COSMOS_KEY", "").strip()
    if not endpoint.startswith("https://") or not key:
        raise SystemExit("Set COSMOS_ENDPOINT and COSMOS_KEY first (never commit them).")
    db_name = os.environ.get("COSMOS_DATABASE", "stockmanager")
    container_name = os.environ.get("COSMOS_CONTAINER", "warehouses")
    client = CosmosClient(url=endpoint, credential=key)
    database = client.create_database_if_not_exists(id=db_name)
    # Manual provisioned 400 RU/s for the demo. Charges may apply if the
    # Cosmos account does not have a suitable free tier / sufficient credit.
    container = database.create_container_if_not_exists(
        id=container_name, partition_key=PartitionKey(path="/warehouse_id"),
        offer_throughput=400,
    )
    meta = container.read()
    paths = meta.get("partitionKey", {}).get("paths", [])
    if paths != ["/warehouse_id"]:
        raise SystemExit("Existing container must use /warehouse_id partition key; choose another name.")
    repo = CosmosWarehouseRepository(container, warehouse_id=os.environ.get("STOCK_WAREHOUSE_ID", "main"))
    state = repo.read()
    print("Cosmos connection OK.")
    print(f"Database: {db_name} | Container: {container_name}")
    print(f"Existing categories: {len(state.categories)} | Products: {len(state.products)} | Movements: {len(state.movements)}")
    print("No data was deleted. Start the Flask app with STOCK_BACKEND=cosmos to seed an empty warehouse.")


if __name__ == "__main__":
    main()
