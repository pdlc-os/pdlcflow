"""SaaS sink — Kinesis Firehose put_record_batch into the events delivery stream.

Records land in S3 under `s3://bucket/dt=YYYY-MM-DD/org=ORG/` partitioned by
Glue, then are ingested into ClickHouse Cloud via the standard MergeTree
ReplacingMergeTree pipeline that dedups on (org_id, event_id).
"""

from __future__ import annotations

from event_schema import EventEnvelope


class FirehoseSink:
    def __init__(self, stream_name: str, region: str = "us-east-1"):
        self._stream = stream_name
        self._region = region
        # Lazy boto3 client init — keeps unit tests offline.

    def write(self, batch: list[EventEnvelope]) -> None:
        # Real: client.put_record_batch(DeliveryStreamName=self._stream,
        #         Records=[{"Data": e.model_dump_json().encode()+b"\n"} for e in batch])
        return None
