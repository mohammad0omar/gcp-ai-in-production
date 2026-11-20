from loadtest.records import FIELDS


def test_records_keep_a_status_column_for_http_codes():
    assert "status" in FIELDS
