from pebble_support import tools
from pebble_support.orders import reset_refunds


def setup_function():
    reset_refunds()


def test_lookup_order_returns_order():
    result = tools.lookup_order("PP-1001")
    assert result["status"] == "ok"
    assert result["currency"] == "GBP"


def test_lookup_unknown_order_is_clean_error():
    result = tools.lookup_order("PP-0000")
    assert result["status"] == "not_found"
    assert "PP-0000" in result["message"]


def test_refund_ok_within_limit():
    result = tools.refund_order("PP-1001", 2400, "GBP")
    assert result["status"] == "refunded"


def test_refund_over_limit_refused():
    result = tools.refund_order("PP-1002", 8900, "EUR")
    assert result["status"] == "refused"
    assert result["reason"] == "over_limit"
    assert "5000" in result["message"]


def test_currency_mismatch_refused():
    result = tools.refund_order("PP-1001", 1000, "USD")
    assert result["status"] == "refused"
    assert result["reason"] == "currency_mismatch"


def test_refund_is_idempotent_per_order():
    assert tools.refund_order("PP-1003", 1500, "GBP")["status"] == "refunded"
    second = tools.refund_order("PP-1003", 1500, "GBP")
    assert second["status"] == "refused"
    assert second["reason"] == "already_refunded"


def test_refund_rejects_non_positive_amount():
    assert tools.refund_order("PP-1001", 0, "GBP")["reason"] == "invalid_amount"
    assert tools.refund_order("PP-1001", -5, "GBP")["reason"] == "invalid_amount"


def test_fault_flag_changes_lookup(monkeypatch):
    assert tools.lookup_order("PP-1001")["currency"] == "GBP"
    monkeypatch.setenv("DRILL_FAULT", "wrong_currency")
    assert tools.lookup_order("PP-1001")["currency"] == "USD"
    # The refund check still uses the true currency, so the fault shows up as refusals.
    assert tools.refund_order("PP-1001", 1000, "USD")["reason"] == "currency_mismatch"


def test_unknown_fault_value_is_ignored(monkeypatch):
    monkeypatch.setenv("DRILL_FAULT", "something_else")
    assert tools.lookup_order("PP-1001")["currency"] == "GBP"


def test_refund_above_order_total_refused():
    # 3000 is under the 5000 cap but PP-1001 only cost 2400.
    result = tools.refund_order("PP-1001", 3000, "GBP")
    assert result["reason"] == "over_order_total"


def test_refund_rejects_bool_amount():
    assert tools.refund_order("PP-1001", True, "GBP")["reason"] == "invalid_amount"
