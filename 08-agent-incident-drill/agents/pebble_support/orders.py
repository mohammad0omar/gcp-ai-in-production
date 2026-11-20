"""A tiny in-memory order book for Pebble Post. A real shop would call its order system here."""

import os
import threading

from config import FAULT_ENV, FAULT_WRONG_CURRENCY

ORDERS = {
    "PP-1001": {"item": "Box of 12 stamps", "total_minor": 2400, "currency": "GBP", "status": "delivered"},
    "PP-1002": {"item": "Bulk packing kit", "total_minor": 8900, "currency": "EUR", "status": "delivered"},
    "PP-1003": {"item": "Courier tape", "total_minor": 1500, "currency": "GBP", "status": "delivered"},
}

# SIMULATED refund ledger. It lives in one process only: it is lost when the instance
# restarts or a new revision starts, and other instances cannot see it. A real shop
# keeps refunds in a database, keyed by a stable refund-operation key, and checks and
# writes in one transaction. The lock below only makes check-and-write atomic inside
# this process.
_refunded: set[str] = set()
_lock = threading.Lock()


def find_order(order_id: str) -> dict | None:
    """Return the true order record, or None."""
    return ORDERS.get(order_id)


def displayed_currency(order: dict) -> str:
    """Currency that lookup_order shows. The drill fault makes it wrong on purpose."""
    if os.environ.get(FAULT_ENV) == FAULT_WRONG_CURRENCY:
        return "USD" if order["currency"] != "USD" else "GBP"
    return order["currency"]


def try_mark_refunded(order_id: str) -> bool:
    """Atomically record a refund. Return False if the order was already refunded."""
    with _lock:
        if order_id in _refunded:
            return False
        _refunded.add(order_id)
        return True


def reset_refunds() -> None:
    """Clear refund state. Used by tests."""
    _refunded.clear()
