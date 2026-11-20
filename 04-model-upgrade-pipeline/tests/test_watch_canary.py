from types import SimpleNamespace
from unittest import mock

from pipeline import watch_canary
from pipeline.watch_canary import watch


class FakeTime:
    """A clock that only moves when the watcher sleeps."""

    def __init__(self):
        self.now = 1_000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def run(readings, **kwargs):
    """readings: one value per read, the last repeats. Returns (ok, fake time, [(rev, start, end, at)])."""
    fake, calls = FakeTime(), []

    def reader(revision, start, end):
        calls.append((revision, start, end, fake.now))
        return readings[min(len(calls) - 1, len(readings) - 1)]

    ok = watch(reader, "rev-1", 1_000.0, sleep=fake.sleep, clock=fake.clock, **kwargs)
    return ok, fake, calls


def test_watch_canary_passes_and_the_final_read_is_after_settling():
    ok, fake, calls = run([(300, 2)], minutes=10, max_error_rate=0.02)
    assert ok
    window_end, final_at = 1_000.0 + 600, 1_000.0 + 600 + 180
    assert sum(fake.sleeps) == 600 + 180
    revision, start, end, at = calls[-1]
    assert (revision, start, end) == ("rev-1", 1_000.0, window_end)  # fixed window end
    assert at == final_at  # started after the settle period
    assert all(call[3] < final_at for call in calls[:-1])  # no other read starts at or after the deadline
    assert all(call[2] <= window_end for call in calls)


def test_watch_canary_fails_over_threshold():
    ok, fake, _ = run([(100, 0), (200, 20)], minutes=10, max_error_rate=0.02)
    assert not ok
    assert fake.sleeps == [60]  # stops at the first bad poll


def test_late_error_spike_is_seen_by_the_final_read():
    readings = [(500, 0)] * 12 + [(520, 40)]
    ok, _, _ = run(readings, minutes=10, max_error_rate=0.02)
    assert not ok


def test_watch_canary_fails_closed_without_traffic():
    ok, _, _ = run([(0, 0), (5, 0)], minutes=2, max_error_rate=0.02, min_requests=20)
    assert not ok


def test_failed_final_read_fails_even_after_healthy_reads():
    readings = [(500, 0)] * 12 + [None]
    ok, _, _ = run(readings, minutes=10, max_error_rate=0.02)
    assert not ok


def test_monitoring_read_failure_is_not_a_pass():
    ok, _, _ = run([None], minutes=1, max_error_rate=0.02)
    assert not ok


def test_monitoring_reader_filters_by_service_region_revision():
    series = SimpleNamespace(
        metric=SimpleNamespace(labels={"response_code": "503"}),
        points=[SimpleNamespace(value=SimpleNamespace(int64_value=4))],
    )
    ok_series = SimpleNamespace(
        metric=SimpleNamespace(labels={"response_code": "200"}),
        points=[SimpleNamespace(value=SimpleNamespace(int64_value=96))],
    )
    client = mock.Mock()
    client.list_time_series.return_value = [series, ok_series]
    with mock.patch("google.cloud.monitoring_v3.MetricServiceClient", return_value=client):
        read = watch_canary.monitoring_reader("proj", "svc", "europe-west1")
        assert read("svc-c123", 1_000.0, 1_600.0) == (100, 4)
    request = client.list_time_series.call_args.kwargs["request"]
    flt = request["filter"]
    assert request["name"] == "projects/proj"
    assert 'resource.labels.service_name = "svc"' in flt
    assert 'resource.labels.location = "europe-west1"' in flt
    assert 'resource.labels.revision_name = "svc-c123"' in flt
    assert client.list_time_series.call_args.kwargs["timeout"] == watch_canary.MONITORING_TIMEOUT_S
    assert client.list_time_series.call_args.kwargs["retry"] is not None  # bounded retry
