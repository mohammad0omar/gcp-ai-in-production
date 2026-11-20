"""The two tools the agent may call. Money rules live here, not in the prompt."""

from config import MAX_REFUND_MINOR

from .logs import log_tool_call
from .orders import displayed_currency, find_order, try_mark_refunded


def lookup_order(order_id: str) -> dict:
    """Look up a Pebble Post order.

    Args:
        order_id: The order number, for example PP-1001.

    Returns:
        A dict with status, item, total_minor (smallest currency unit) and currency.
    """
    order = find_order(order_id)
    if order is None:
        log_tool_call("lookup_order", "refused", "not_found", order_id=order_id)
        return {"status": "not_found", "message": f"No order {order_id} exists."}
    log_tool_call("lookup_order", "allowed", "found", order_id=order_id)
    return {
        "status": "ok",
        "item": order["item"],
        "total_minor": order["total_minor"],
        "currency": displayed_currency(order),
        "order_status": order["status"],
    }


def _refuse(order_id: str, reason: str, message: str) -> dict:
    log_tool_call("refund_order", "refused", reason, order_id=order_id)
    return {"status": "refused", "reason": reason, "message": message}


def refund_order(order_id: str, amount_minor: int, currency: str) -> dict:
    """Refund part or all of an order.

    Args:
        order_id: The order number, for example PP-1001.
        amount_minor: Amount in the smallest currency unit (pence, cents). A whole number.
        currency: Three letter currency code. It must equal the order currency.

    Returns:
        A dict with status "refunded" or "refused" and a message to read to the customer.
    """
    order = find_order(order_id)
    if order is None:
        return _refuse(order_id, "not_found", f"No order {order_id} exists.")
    # bool is a subclass of int in Python, so True would pass a plain isinstance check.
    if type(amount_minor) is not int or amount_minor <= 0:
        return _refuse(order_id, "invalid_amount", "The refund amount must be a positive whole number.")
    if amount_minor > order["total_minor"]:
        return _refuse(order_id, "over_order_total", "The refund cannot be more than the order total.")
    if amount_minor > MAX_REFUND_MINOR:
        return _refuse(
            order_id,
            "over_limit",
            f"Refunds above {MAX_REFUND_MINOR} minor units need a human agent.",
        )
    if currency != order["currency"]:
        return _refuse(
            order_id,
            "currency_mismatch",
            f"The refund currency {currency} does not match the order currency.",
        )
    if not try_mark_refunded(order_id):
        return _refuse(order_id, "already_refunded", f"Order {order_id} was already refunded.")
    log_tool_call(
        "refund_order", "refunded", "within_limit",
        order_id=order_id, amount_minor=amount_minor, currency=currency,
    )
    return {"status": "refunded", "message": f"Refunded {amount_minor} {currency} on {order_id}."}
