"""Watch the canary revision's error rate in Cloud Monitoring. Exit 1 when it is too high.

Usage: python pipeline/watch_canary.py --project P --service S --region R --revision REV --since EPOCH --minutes 10
The window starts at --since, the moment traffic moved, so dependency installs do not shorten it. The reader and
the clock are injectable, so tests never call Google or sleep.
"""

import argparse
import sys
import time
from collections.abc import Callable

# A reader takes (revision, start_epoch, end_epoch) and returns (total_requests, error_requests)
# in that window, or None when Monitoring could not be read this time.
MetricsReader = Callable[[str, float, float], tuple[int, int] | None]

# Cloud Run samples every 60 s and can take up to 120 s more to publish them, so the last
# minutes of traffic only show up after this much extra waiting.
SETTLE_SECONDS = 180
MONITORING_TIMEOUT_S = 30
# Total time one read may spend retrying, so a slow API cannot eat the rollback time.
RETRY_BUDGET_S = 45


def watch(
    reader: MetricsReader,
    revision: str,
    since: float,
    minutes: int,
    max_error_rate: float,
    min_requests: int = 20,
    poll_seconds: int = 60,
    settle_seconds: int = SETTLE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> bool:
    """Observe [since, since + minutes], then wait `settle_seconds`, then read the whole window once.

    Reads during the window only exist to fail early. The decision is the final read: it starts after
    the settle period (so late metrics have arrived), asks for the fixed window, and must succeed.
    No read starts after the settle deadline except that final one.
    """
    window_end = since + minutes * 60
    final_at = window_end + settle_seconds
    while clock() < final_at:
        now = clock()
        reading = reader(revision, since, min(now, window_end))
        if reading is not None:
            total, errors = reading
            rate = errors / total if total else 0.0
            print(f"requests={total} errors={errors} rate={rate:.3f}")
            if total >= min_requests and rate > max_error_rate:
                print(f"FAIL: error rate {rate:.3f} is over {max_error_rate}")
                return False
        else:
            print("monitoring read failed, the final read decides")
        sleep(max(0.0, min(poll_seconds, final_at - clock())))
    reading = reader(revision, since, window_end)
    if reading is None:
        print("FAIL: the final read failed, so the whole window was not checked")
        return False
    total, errors = reading
    rate = errors / total if total else 0.0
    print(f"final: requests={total} errors={errors} rate={rate:.3f}")
    if total < min_requests:
        # Fail closed: a canary that saw no real traffic proved nothing.
        print(f"FAIL: only {total} requests, need {min_requests}")
        return False
    if rate > max_error_rate:
        print(f"FAIL: error rate {rate:.3f} is over {max_error_rate}")
        return False
    print("OK: canary is healthy")
    return True


def monitoring_reader(project: str, service: str, region: str) -> MetricsReader:
    """Build a reader over run.googleapis.com/request_count, summed per response_code."""
    from google.api_core import exceptions
    from google.api_core.retry import Retry
    from google.cloud import monitoring_v3

    client = monitoring_v3.MetricServiceClient()

    def read(revision: str, start: float, end: float) -> tuple[int, int] | None:
        now = int(end)
        begin = int(start)
        interval = monitoring_v3.TimeInterval(
            {"start_time": {"seconds": begin}, "end_time": {"seconds": now}}
        )
        aggregation = monitoring_v3.Aggregation(
            {
                "alignment_period": {"seconds": max(60, now - begin)},
                "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_SUM,
                "cross_series_reducer": monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
                "group_by_fields": ["metric.labels.response_code"],
            }
        )
        flt = (
            'metric.type = "run.googleapis.com/request_count" '
            'AND resource.type = "cloud_run_revision" '
            f'AND resource.labels.service_name = "{service}" '
            f'AND resource.labels.location = "{region}" '
            f'AND resource.labels.revision_name = "{revision}"'
        )
        try:
            series = client.list_time_series(
                request={
                    "name": f"projects/{project}",
                    "filter": flt,
                    "interval": interval,
                    "aggregation": aggregation,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                },
                retry=Retry(timeout=RETRY_BUDGET_S),
                timeout=MONITORING_TIMEOUT_S,
            )
            total = errors = 0
            for item in series:
                count = sum(point.value.int64_value for point in item.points)
                total += count
                code = item.metric.labels.get("response_code", "")
                if code.isdigit() and 500 <= int(code) <= 599:
                    errors += count
        except (exceptions.GoogleAPICallError, exceptions.RetryError) as exc:
            print(f"monitoring error: {type(exc).__name__}")
            return None
        return total, errors

    return read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--service")
    parser.add_argument("--region")
    parser.add_argument("--revision")
    parser.add_argument("--since", type=float, help="epoch seconds when traffic moved")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--max-error-rate", type=float, default=0.02)
    parser.add_argument("--min-requests", type=int, default=20)
    args = parser.parse_args(argv)
    for name in ("project", "service", "region", "revision", "since"):
        if not getattr(args, name):
            parser.error(f"--{name} is required")
    reader = monitoring_reader(args.project, args.service, args.region)
    ok = watch(reader, args.revision, args.since, args.minutes, args.max_error_rate, args.min_requests)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
