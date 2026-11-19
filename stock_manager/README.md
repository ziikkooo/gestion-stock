# Stock Manager — foundation milestone

This is the first, independent backend slice of the revised architecture. It does not change the existing Flask application or templates. No Azure resources are required.

- `models.py`: immutable domain records, inventory state, stock statuses.
- `repository.py`: transaction and snapshot contract, thread-safe in-memory implementation.
- `service.py`: category management, product creation and editing, archive/restore, filters and stock audit trail.
- `../tests/test_stock_foundation.py`: automated rule and concurrency tests.

Run from the project root with the existing virtual environment active:

```sh
python -m pip install 'pytest>=8,<10'
python -m pytest -q tests/test_stock_foundation.py
```

The service starts with an empty catalogue. The tests build their own fixtures. The existing Flask application is not yet connected to the service. Its previous sample data will be recreated via audited creation when we connect the two. An actor passed to the service must come from a trusted authenticated server-side identity; validating the actor's shape is not authentication.

The repository deliberately uses a full in-memory snapshot and single lock in this small academic prototype. The future Cosmos implementation needs a consistent revision-fenced read, conditional transactional writes of only changed documents in one warehouse partition, bounded retries and actual Azure integration tests. It must respect Cosmos transactional batch limits. The current lock is process-local and provides no cross-process or cloud concurrency guarantee. Adjustments currently check the expected quantity; the persistent adapter will also need appropriate version/conflict handling. No notification events, user accounts, CSRF, HTTP routes or persistence are implemented yet.
