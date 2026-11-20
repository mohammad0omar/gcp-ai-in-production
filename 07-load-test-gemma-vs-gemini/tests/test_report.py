import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import report

FOLDER = Path(__file__).resolve().parents[1]


def test_break_even_math():
    # One GPU instance for 24 hours costs 24.0. Gemini output costs 0.4 per 1M tokens,
    # so the break-even is 60,000,000 output tokens a day, 300,000 requests of 200 tokens.
    result = report.break_even_requests_per_day(
        gpu_hour=Decimal("1.0"),
        gemini_per_million=Decimal("0.4"),
        output_tokens_per_request=200,
    )
    assert result == Decimal(300000)


def test_break_even_is_not_reachable_with_one_instance_at_fixture_rates():
    # 100 tokens/s for 24 hours is 8,640,000 tokens; at 200 tokens per request that is 43,200
    # requests a day, far below the 300,000 break-even. The report must flag it.
    capacity = report.instance_capacity_requests_per_day(Decimal(100), Decimal(1), 200)
    assert capacity == Decimal(43200)
    assert not report.break_even_is_reachable(Decimal(300000), capacity)
    assert report.break_even_is_reachable(Decimal(40000), capacity)


def _rec(start, end, tokens, ok=True, side="gemma"):
    return report.Record(side, 0.1, tokens, 50.0, start, end, ok)


def test_default_window_drops_ten_percent_at_each_end():
    # Test runs 100 to 200. Default window is 110 to 190, so the requests starting at 100
    # (ramp-up) and 195 (ramp-down) are out. In-window: 120 (60 tokens), 150 (failure, 0 tokens).
    records = [
        _rec(100.0, 101.0, 500),
        _rec(120.0, 121.0, 60),
        _rec(150.0, 151.0, 0, ok=False),
        _rec(195.0, 200.0, 500),
    ]
    # 60 tokens over an 80 second window.
    assert report.aggregate_throughput(records, "gemma") == Decimal("0.75")
    assert report.aggregate_throughput(records, "gemini") is None


def test_explicit_steady_window_in_seconds_from_test_start():
    records = [_rec(100.0, 101.0, 500), _rec(120.0, 121.0, 60), _rec(195.0, 200.0, 500)]
    window = (Decimal(10), Decimal(30))  # absolute 110 to 130: only the request at 120
    assert report.aggregate_throughput(records, "gemma", window) == Decimal(3)


def test_failures_at_the_edges_do_not_inflate_throughput():
    records = [_rec(100.0, 101.0, 100), _rec(100.0, 200.0, 0, ok=False), _rec(150.0, 151.0, 80)]
    # The failed request stretches the test to 100 seconds, so the window is 110 to 190.
    assert report.aggregate_throughput(records, "gemma") == Decimal(1)


def test_request_must_end_inside_the_window_to_count():
    # Test runs 100 to 200; window 110 to 190. The request starting at 189 ends at 219, outside it.
    records = [_rec(100.0, 101.0, 1), _rec(120.0, 121.0, 60), _rec(189.0, 219.0, 30), _rec(199.0, 200.0, 1)]
    records[2] = _rec(189.0, 219.0, 30)
    assert report.aggregate_throughput(records, "gemma", (Decimal(10), Decimal(90))) == Decimal("0.75")


def test_window_outside_the_test_is_refused():
    records = [_rec(100.0, 101.0, 10), _rec(150.0, 200.0, 10)]
    with pytest.raises(ValueError):
        report.aggregate_throughput(records, "gemma", (Decimal(10), Decimal(500)))


def test_capacity_uses_gemmas_own_tokens_and_instances_needed():
    records = [_rec(0.0, 1.0, 100), _rec(1.0, 2.0, 300)]
    assert report.mean_output_tokens(records, "gemma") == Decimal(200)
    assert report.mean_output_tokens(records, "gemini") is None
    capacity = report.instance_capacity_requests_per_day(Decimal(100), Decimal(1), Decimal(200))
    assert capacity == Decimal(43200)
    assert report.instances_needed(Decimal(300000), capacity) == 7


def test_two_runs_of_one_side_are_refused():
    run_a = [_rec(0.0, 1.0, 10)]
    run_b = [_rec(500.0, 501.0, 10)]
    with pytest.raises(ValueError):
        report.check_one_run_per_side({"a.csv": run_a, "b.csv": run_b})
    report.check_one_run_per_side({"a.csv": run_a, "b.csv": [_rec(0.0, 1.0, 10, side="gemini")]})


@pytest.mark.parametrize("util", ["0", "-1", "1.5", "NaN"])
def test_bad_utilisation_is_rejected(util):
    with pytest.raises(ValueError):
        report.gemma_cost_per_million(Decimal(1), Decimal(100), Decimal(util))


def test_bad_costing_inputs_are_rejected():
    with pytest.raises(ValueError):
        report.gemma_cost_per_million(Decimal(1), Decimal(-5), Decimal(1))
    with pytest.raises(ValueError):
        report.break_even_requests_per_day(Decimal(1), Decimal("0.4"), 0)


def test_gemini_rate_depends_on_the_pricing_date():
    prices = report.load_prices(FOLDER / "prices.toml")
    assert report.gemini_output_per_million(prices, date(2026, 11, 20)) == Decimal("3.75")
    assert report.gemini_output_per_million(prices, date(2027, 4, 13)) == Decimal("7.5")


def test_report_follows_the_price_file(tmp_path):
    cheap = tmp_path / "prices.toml"
    cheap.write_text(
        '[gemini.a]\nvalue = 1.25\neffective_from = "2020-01-01"\neffective_to = "2099-12-31"\n'
        '[cloud_run.gpu_second]\nvalue = 1\n[cloud_run.vcpu_second]\nvalue = 0\n'
        '[cloud_run.gib_second]\nvalue = 0\n[instance]\nvcpu = 1\nmemory_gib = 1\n'
    )
    prices = report.load_prices(cheap)
    assert report.gemini_output_per_million(prices, date(2027, 1, 1)) == Decimal("1.25")
    assert report.gpu_instance_hour(prices) == Decimal(3600)


def test_gemma_cost_per_million_at_full_and_half_utilisation():
    full = report.gemma_cost_per_million(Decimal("1.0"), Decimal(100), Decimal(1))
    half = report.gemma_cost_per_million(Decimal("1.0"), Decimal(100), Decimal("0.5"))
    assert full.quantize(Decimal("0.0001")) == Decimal("2.7778")
    assert half == full * 2


def test_percentile_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert report.percentile(values, 50) == 5.0
    assert report.percentile(values, 95) == 10.0


def test_summarize_reads_records(tmp_path):
    csv_file = tmp_path / "records.csv"
    csv_file.write_text(
        "side,ttft_s,output_tokens,tokens_per_second,ok\n"
        "gemma,0.2,50,40.0,1\n"
        "gemma,0.4,50,60.0,1\n"
        "gemma,9.0,0,,0\n"
        "gemini,0.5,50,100.0,1\n"
    )
    records = report.read_records(csv_file)
    gemma = report.summarize(records, "gemma")
    assert gemma.requests == 3 and gemma.failures == 1
    assert gemma.ttft_p50 == 0.2
    assert gemma.tokens_per_second_p50 == 40.0


def test_prices_come_from_config():
    tree = ast.parse((FOLDER / "report.py").read_text())
    floats = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    assert floats == []
    # Whole-number literals must be unit constants, not prices.
    assert {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int)
            and not isinstance(n.value, bool)} <= {0, 1, 2, 24, 50, 95, 100, 1_000_000, 3600}
    assert (FOLDER / "prices.toml").exists()


def test_every_price_has_source_and_date():
    prices = report.load_prices(FOLDER / "prices.toml")
    for name, section in prices.items():
        if name == "instance":
            continue  # machine shape, not a price
        for entry in section.values():
            assert entry["source"].startswith("https://")
            assert entry["checked"] == "2026-11-20"
            assert float(entry["value"]) > 0


def test_missing_price_is_a_clean_error(tmp_path):
    bad = tmp_path / "prices.toml"
    bad.write_text("[gemini]\n")
    with pytest.raises(report.PriceError):
        report.gemini_output_per_million(report.load_prices(bad), date(2027, 1, 1))
