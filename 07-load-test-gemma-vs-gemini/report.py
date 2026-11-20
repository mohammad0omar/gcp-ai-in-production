"""Turn results/records.csv and prices.toml into the numbers for the post.

Usage: python report.py results/records-GEMMA.csv results/records-GEMINI.csv --utilisation 0.6 --output-tokens 128 --pricing-date 2027-04-13
Money maths uses Decimal so the break-even is exact. No price appears in this file.
The comparison is OUTPUT TOKENS ONLY: input tokens, the Cloud Run request fees and the
cost of your own engineers are not in it.

Throughput and utilisation: throughput is measured while the GPU is kept busy: output tokens
of requests that start inside a steady window, divided by the window length. The window is
the test minus its first and last 10 percent, or --steady-window START END (seconds from test
start). Benchmark Gemma with ONE serving instance (max-instances 1, the deploy default); all
numbers are per instance, and instances needed = ceil(volume / per-instance capacity). Utilisation is the
share of an always-on instance's time that is busy in production. Idle time is counted once,
in utilisation.
"""

import argparse
import csv
import math
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

SECONDS_PER_HOUR = 3600
HOURS_PER_DAY = 24
TOKENS_PER_MILLION = 1_000_000


class PriceError(Exception):
    """A price is missing from prices.toml."""


@dataclass(frozen=True)
class Record:
    side: str
    ttft_s: float | None
    output_tokens: int
    tokens_per_second: float | None
    started_at: float
    ended_at: float
    ok: bool


@dataclass(frozen=True)
class Summary:
    side: str
    requests: int
    failures: int
    ttft_p50: float | None
    ttft_p95: float | None
    tokens_per_second_p50: float | None


def load_prices(path: Path) -> dict:
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def _price(prices: dict, section: str, name: str) -> Decimal:
    try:
        return Decimal(str(prices[section][name]["value"]))
    except KeyError as error:
        raise PriceError(f"prices.toml has no [{section}.{name}] value") from error


def gemini_output_per_million(prices: dict, on: date) -> Decimal:
    """Gemini output price in force on `on`. Raises PriceError if no rate covers the date."""
    for entry in prices.get("gemini", {}).values():
        if date.fromisoformat(entry["effective_from"]) <= on <= date.fromisoformat(entry["effective_to"]):
            return Decimal(str(entry["value"]))
    raise PriceError(f"prices.toml has no Gemini output price for {on}")


def gpu_instance_hour(prices: dict) -> Decimal:
    """GPU + vCPU + memory for one always-on instance, per hour."""
    shape = prices.get("instance")
    if not shape:
        raise PriceError("prices.toml has no [instance] shape")
    per_second = (
        _price(prices, "cloud_run", "gpu_second")
        + Decimal(shape["vcpu"]) * _price(prices, "cloud_run", "vcpu_second")
        + Decimal(shape["memory_gib"]) * _price(prices, "cloud_run", "gib_second")
    )
    return per_second * SECONDS_PER_HOUR


def percentile(values: list[float], pct: int) -> float:
    """Nearest-rank percentile. Simple and the same in every language."""
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def read_records(path: Path) -> list[Record]:
    with Path(path).open(newline="") as handle:
        return [
            Record(
                side=row["side"],
                ttft_s=float(row["ttft_s"]) if row["ttft_s"] else None,
                output_tokens=int(row["output_tokens"]),
                tokens_per_second=float(row["tokens_per_second"]) if row["tokens_per_second"] else None,
                started_at=float(row.get("started_at") or 0),
                ended_at=float(row.get("ended_at") or 0),
                ok=row["ok"] == "1",
            )
            for row in csv.DictReader(handle)
        ]


TRIM_SHARE = Decimal("0.1")  # default: drop the first and last 10 percent of the test


def steady_window(
    records: list[Record], side: str, window: tuple[Decimal, Decimal] | None = None
) -> tuple[Decimal, Decimal] | None:
    """Absolute (start, end) epoch seconds of the steady-state window for one side.

    Test start is the first request start, test end is the last request end, successes and
    failures alike. `window` is (START, END) in seconds from test start; the default drops
    TRIM_SHARE of the test duration at each end (ramp-up and ramp-down).
    """
    mine = [r for r in records if r.side == side]
    if not mine:
        return None
    begin = Decimal(str(min(r.started_at for r in mine)))
    duration = Decimal(str(max(r.ended_at for r in mine))) - begin
    if duration <= 0:
        return None
    if window is None:
        window = (duration * TRIM_SHARE, duration * (1 - TRIM_SHARE))
    elif not 0 <= window[0] < window[1] <= duration:
        raise ValueError(f"steady window {window} must lie inside the test, 0 to {duration} seconds")
    return begin + window[0], begin + window[1]


def aggregate_throughput(
    records: list[Record], side: str, window: tuple[Decimal, Decimal] | None = None
) -> Decimal | None:
    """Output tokens per second over the steady window, whatever the outcome at the edges.

    Only requests that both START and END inside the window count, so no token is credited
    from time outside it. A failure adds zero tokens but its time stays in the window.
    """
    bounds = steady_window(records, side, window)
    if bounds is None or bounds[1] <= bounds[0]:
        return None
    inside = [
        r for r in records if r.side == side
        and bounds[0] <= Decimal(str(r.started_at))
        and Decimal(str(r.ended_at)) <= bounds[1]
    ]
    tokens = sum(r.output_tokens for r in inside if r.ok)
    return Decimal(tokens) / (bounds[1] - bounds[0])


def mean_output_tokens(records: list[Record], side: str) -> Decimal | None:
    """Average output tokens of one side's successful requests, from that side's own stream."""
    good = [r.output_tokens for r in records if r.side == side and r.ok]
    return Decimal(sum(good)) / len(good) if good else None


def check_one_run_per_side(files_records: dict[str, list[Record]]) -> None:
    """Refuse to pool two runs of the same side: the gap between them would skew the window."""
    seen: dict[str, str] = {}
    for name, records in files_records.items():
        for side in {r.side for r in records}:
            if side in seen:
                raise ValueError(f"{side} appears in both {seen[side]} and {name}; pass one file per side")
            seen[side] = name


def instances_needed(requests_per_day: Decimal, capacity_per_instance: Decimal) -> int:
    """Whole instances needed to serve a daily volume."""
    return math.ceil(requests_per_day / capacity_per_instance)


def require_positive(name: str, value: Decimal) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite number above zero, got {value}")
    return value


def _check_utilisation(utilisation: Decimal) -> None:
    if not utilisation.is_finite() or not 0 < utilisation <= 1:
        raise ValueError(f"utilisation must be above 0 and at most 1, got {utilisation}")


def summarize(records: list[Record], side: str) -> Summary:
    mine = [r for r in records if r.side == side]
    good = [r for r in mine if r.ok]
    ttfts = [r.ttft_s for r in good if r.ttft_s is not None]
    speeds = [r.tokens_per_second for r in good if r.tokens_per_second is not None]
    return Summary(
        side=side,
        requests=len(mine),
        failures=len(mine) - len(good),
        ttft_p50=percentile(ttfts, 50) if ttfts else None,
        ttft_p95=percentile(ttfts, 95) if ttfts else None,
        tokens_per_second_p50=percentile(speeds, 50) if speeds else None,
    )


def gemma_cost_per_million(gpu_hour: Decimal, throughput_tps: Decimal, utilisation: Decimal) -> Decimal:
    """Dollars per 1M output tokens when the GPU is busy `utilisation` of the time."""
    require_positive("gpu_hour", gpu_hour)
    require_positive("throughput_tps", throughput_tps)
    _check_utilisation(utilisation)
    tokens_per_hour = throughput_tps * SECONDS_PER_HOUR * utilisation
    return gpu_hour / tokens_per_hour * TOKENS_PER_MILLION


def break_even_requests_per_day(
    gpu_hour: Decimal, gemini_per_million: Decimal, output_tokens_per_request: int
) -> Decimal:
    """Requests per day where one always-on GPU instance costs the same as Gemini.

    Below this, Gemini is cheaper. Above it, Gemma is cheaper until one instance runs out of capacity.
    """
    require_positive("gpu_hour", gpu_hour)
    require_positive("gemini_per_million", gemini_per_million)
    require_positive("output_tokens_per_request", Decimal(output_tokens_per_request))
    gemma_per_day = gpu_hour * HOURS_PER_DAY
    gemini_per_request = gemini_per_million * output_tokens_per_request / TOKENS_PER_MILLION
    return gemma_per_day / gemini_per_request


def instance_capacity_requests_per_day(
    throughput_tps: Decimal, utilisation: Decimal, output_tokens_per_request: int
) -> Decimal:
    """Most requests one instance can serve per day at this utilisation."""
    require_positive("throughput_tps", throughput_tps)
    _check_utilisation(utilisation)
    require_positive("output_tokens_per_request", Decimal(output_tokens_per_request))
    seconds_per_day = SECONDS_PER_HOUR * HOURS_PER_DAY
    return throughput_tps * utilisation * seconds_per_day / output_tokens_per_request


def break_even_is_reachable(break_even: Decimal, capacity: Decimal) -> bool:
    """False when one instance cannot serve as many requests as the break-even needs."""
    return break_even <= capacity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, nargs="+", help="the Gemma and Gemini records files of ONE comparison")
    parser.add_argument("--prices", type=Path, default=Path(__file__).with_name("prices.toml"))
    parser.add_argument("--utilisation", type=Decimal, required=True, help="busy share of an always-on instance, above 0 up to 1")
    parser.add_argument("--output-tokens", type=int, required=True, help="average BILLED Gemini output tokens per request")
    parser.add_argument("--pricing-date", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, picks the Gemini rate")
    parser.add_argument("--steady-window", type=Decimal, nargs=2, metavar=("START", "END"),
                        help="seconds from test start; default drops the first and last 10 percent")
    parser.add_argument("--throughput-tps", type=Decimal, help="override the measured tokens per second of ONE instance")
    args = parser.parse_args()

    prices = load_prices(args.prices)
    per_file = {str(path): read_records(path) for path in args.records}
    check_one_run_per_side(per_file)
    records = [r for recs in per_file.values() for r in recs]
    gemma, gemini = summarize(records, "gemma"), summarize(records, "gemini")
    for s in (gemma, gemini):
        print(f"{s.side}: requests={s.requests} failures={s.failures} ttft p50={s.ttft_p50} "
              f"p95={s.ttft_p95} per-stream tokens/s p50={s.tokens_per_second_p50}")
    window = tuple(args.steady_window) if args.steady_window else None
    throughput = args.throughput_tps or aggregate_throughput(records, "gemma", window)
    gemma_tokens = mean_output_tokens(records, "gemma")
    if throughput is None or gemma_tokens is None:
        raise SystemExit("No successful Gemma requests in the steady window; cannot price the GPU side.")

    gpu_hour = gpu_instance_hour(prices)
    gemini_price = gemini_output_per_million(prices, args.pricing_date)
    print("Output tokens only. Input tokens and request fees are not included.")
    print(f"Gemma steady-window throughput: {throughput:.1f} tokens/s per instance (measured while busy)")
    print(f"Gemma cost per 1M output tokens: {gemma_cost_per_million(gpu_hour, throughput, args.utilisation):.2f}")
    print(f"Gemini cost per 1M output tokens on {args.pricing_date}: {gemini_price:.2f}")
    break_even = break_even_requests_per_day(gpu_hour, gemini_price, args.output_tokens)
    capacity = instance_capacity_requests_per_day(throughput, args.utilisation, gemma_tokens)
    print(f"Break-even requests per day (one always-on instance vs Gemini): {break_even:.0f}")
    print(f"One instance can serve about {capacity:.0f} requests per day at Gemma's own {gemma_tokens:.0f} output tokens per request")
    if not break_even_is_reachable(break_even, capacity):
        print(f"One instance is the limit: serving {break_even:.0f} requests per day needs "
              f"{instances_needed(break_even, capacity)} instances. Each extra instance adds cost and "
              "capacity together, so compare per-token cost above, not this one number.")


if __name__ == "__main__":
    main()
