"""SaaS sink — Kinesis Firehose put_record_batch into the events delivery stream.

Records land in S3 under `s3://bucket/dt=YYYY-MM-DD/org=ORG/` partitioned by
Glue, then are ingested downstream (e.g. a warehouse pipeline that dedups on
(org_id, event_id)).

Was a silent no-op until the quick-wins honesty pass — selecting
PDLC_CLICKSTREAM_SINK=firehose dropped every event. Now real: newline-delimited
JSON records, batched ≤500 per put_record_batch (the API limit), one retry for
partial failures, and a LOUD-once error log on client failures so a
misconfigured stream can't silently discard telemetry again.
"""

from __future__ import annotations

import logging

from event_schema import EventEnvelope

log = logging.getLogger("pdlc.clickstream.firehose")

_BATCH_LIMIT = 500  # put_record_batch hard limit


class FirehoseSink:
    def __init__(self, stream_name: str, region: str = "us-east-1", client=None):
        self._stream = stream_name
        self._region = region
        self._client = client  # injectable for tests; lazy boto3 otherwise
        self._error_logged = False

    def _c(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("firehose", region_name=self._region)
        return self._client

    def write(self, batch: list[EventEnvelope]) -> None:
        records = [{"Data": e.model_dump_json().encode() + b"\n"} for e in batch]
        for start in range(0, len(records), _BATCH_LIMIT):
            chunk = records[start:start + _BATCH_LIMIT]
            try:
                resp = self._c().put_record_batch(
                    DeliveryStreamName=self._stream, Records=chunk)
                if resp.get("FailedPutCount", 0):
                    # Retry only the failed records once (per-record errors are
                    # positional in RequestResponses).
                    failed = [chunk[i] for i, r in enumerate(resp["RequestResponses"])
                              if r.get("ErrorCode")]
                    retry = self._c().put_record_batch(
                        DeliveryStreamName=self._stream, Records=failed)
                    if retry.get("FailedPutCount", 0):
                        log.warning("firehose: %d record(s) failed after retry",
                                    retry["FailedPutCount"])
            except Exception as exc:
                # The emitter's drain already guards, but a broken stream must
                # be unmissable exactly once — not a silent drop, not log spam.
                if not self._error_logged:
                    self._error_logged = True
                    log.error(
                        "firehose sink FAILED (%s: %s) — events are NOT being "
                        "delivered to stream %r; fix the stream/credentials or "
                        "switch PDLC_CLICKSTREAM_SINK",
                        type(exc).__name__, exc, self._stream)
                raise
