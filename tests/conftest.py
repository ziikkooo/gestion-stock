"""Safety guard: pytest must never write to a user's real Cosmos account.

This runs before test modules import app.py, which otherwise initializes the
repository on import. Cosmos integration is tested with an offline fake.
"""
import os

os.environ["STOCK_BACKEND"] = "memory"
