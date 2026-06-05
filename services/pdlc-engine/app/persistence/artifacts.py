"""Artifact store adapters — filesystem (self-host) and S3/MinIO (SaaS).

Both implement the pdlc_graph ArtifactStore interface (`put`/`get`) and are
injected into `pdlc_graph.ports` at boot. Filesystem is the verifiable self-host
default (a mounted volume); S3 targets AWS or a MinIO endpoint. The returned
URI is opaque to graph nodes — they stash it in state and pass it to gate
payloads.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("pdlc.persistence.artifacts")


class FilesystemArtifactStore:
    """Writes artifact bodies under a base directory (self-host volume)."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def _path(self, uri: str) -> Path:
        # uri == "file://{base}/{project_id}/{path}" -> strip scheme + base
        rel = uri.removeprefix("file://")
        return Path(rel)

    def put(self, project_id: str, path: str, content: str) -> str:
        target = self._base / project_id / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"file://{target}"

    def get(self, uri: str) -> str:
        return self._path(uri).read_text(encoding="utf-8")


class S3ArtifactStore:
    """Writes artifact bodies to S3 (or a MinIO endpoint). Lazily builds the
    boto3 client so importing this module never requires AWS credentials."""

    def __init__(self, bucket: str, *, region: str | None = None, endpoint_url: str | None = None) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._client = None

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3", region_name=self._region, endpoint_url=self._endpoint_url
            )
        return self._client

    def _key(self, project_id: str, path: str) -> str:
        return f"{project_id}/{path}"

    def put(self, project_id: str, path: str, content: str) -> str:
        key = self._key(project_id, path)
        self._s3().put_object(Bucket=self._bucket, Key=key, Body=content.encode("utf-8"))
        return f"s3://{self._bucket}/{key}"

    def get(self, uri: str) -> str:
        # uri == "s3://{bucket}/{key}"
        _, _, rest = uri.partition("s3://")
        bucket, _, key = rest.partition("/")
        obj = self._s3().get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8")
