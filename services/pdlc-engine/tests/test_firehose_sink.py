"""FirehoseSink actually delivers records (was a silent no-op).

Uses an injected fake client — no boto3, no network — to assert batching, the
record shape, the partial-failure retry, and the loud-once error contract.
"""

from __future__ import annotations

import uuid

import pytest
from app.clickstream.sinks.firehose import FirehoseSink
from event_schema import EventEnvelope


class _FakeFirehose:
    def __init__(self, fail_indices=None, raise_times=0):
        self.batches: list[list[dict]] = []
        self._fail_indices = fail_indices or []
        self._raise_times = raise_times
        self.calls = 0

    def put_record_batch(self, DeliveryStreamName, Records):  # boto3 kwargs
        self.calls += 1
        if self._raise_times > 0:
            self._raise_times -= 1
            raise RuntimeError("stream not found")
        self.batches.append(Records)
        responses = [{} for _ in Records]
        if self.calls == 1:
            for i in self._fail_indices:
                responses[i] = {"ErrorCode": "ServiceUnavailable"}
            return {"FailedPutCount": len(self._fail_indices),
                    "RequestResponses": responses}
        return {"FailedPutCount": 0, "RequestResponses": responses}


def _ev(i: int) -> EventEnvelope:
    return EventEnvelope(event_type="agent.invoked", org_id=uuid.uuid4(),
                         project_id=uuid.uuid4(), payload={"n": i})


def test_delivers_newline_delimited_json():
    fake = _FakeFirehose()
    FirehoseSink("pdlcflow-events", client=fake).write([_ev(0), _ev(1)])
    assert fake.calls == 1 and len(fake.batches[0]) == 2
    data = fake.batches[0][0]["Data"]
    assert data.endswith(b"\n") and b'"event_type":"agent.invoked"' in data


def test_batches_over_the_500_limit():
    fake = _FakeFirehose()
    FirehoseSink("s", client=fake).write([_ev(i) for i in range(1200)])
    assert [len(b) for b in fake.batches] == [500, 500, 200]


def test_retries_partial_failures_once():
    fake = _FakeFirehose(fail_indices=[1, 3])
    FirehoseSink("s", client=fake).write([_ev(i) for i in range(4)])
    assert fake.calls == 2  # initial + one retry of the 2 failed records
    assert len(fake.batches[1]) == 2


def test_client_error_raises_and_logs_once(caplog):
    fake = _FakeFirehose(raise_times=5)
    sink = FirehoseSink("broken-stream", client=fake)
    import logging
    with caplog.at_level(logging.ERROR, logger="pdlc.clickstream.firehose"):
        with pytest.raises(RuntimeError):
            sink.write([_ev(0)])
        with pytest.raises(RuntimeError):
            sink.write([_ev(1)])
    # Loud exactly once — not a silent drop, not log spam.
    assert sum("firehose sink FAILED" in r.message for r in caplog.records) == 1
