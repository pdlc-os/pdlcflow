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
    """Writes artifact bodies under a base directory (self-host volume),
    namespaced by tenant: {base}/{org_id}/{project_id}/{path}. Every resolved
    path is pinned under the base dir so a crafted segment can't escape it."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()

    def _within_base(self, p: Path) -> Path:
        resolved = p.resolve()
        # Defense in depth — the port already sanitizes, but never read/write
        # outside the base dir even if a raw uri/segment slips through.
        if self._base != resolved and self._base not in resolved.parents:
            raise ValueError(f"artifact path escapes base dir: {p}")
        return resolved

    def put(self, org_id: str, project_id: str, path: str, content: str) -> str:
        target = self._within_base(self._base / org_id / project_id / path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"file://{target}"

    def get(self, uri: str) -> str:
        target = self._within_base(Path(uri.removeprefix("file://")))
        return target.read_text(encoding="utf-8")

    def list(self, org_id: str, project_id: str) -> list[str]:
        root = self._within_base(self._base / org_id / project_id)
        if not root.exists():
            return []
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    def read(self, org_id: str, project_id: str, path: str) -> str:
        target = self._within_base(self._base / org_id / project_id / path)
        return target.read_text(encoding="utf-8")


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

    def _key(self, org_id: str, project_id: str, path: str) -> str:
        return f"{org_id}/{project_id}/{path}"

    def put(self, org_id: str, project_id: str, path: str, content: str) -> str:
        key = self._key(org_id, project_id, path)
        self._s3().put_object(Bucket=self._bucket, Key=key, Body=content.encode("utf-8"))
        return f"s3://{self._bucket}/{key}"

    def get(self, uri: str) -> str:
        # uri == "s3://{bucket}/{key}"
        _, _, rest = uri.partition("s3://")
        bucket, _, key = rest.partition("/")
        obj = self._s3().get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8")

    def list(self, org_id: str, project_id: str) -> list[str]:
        prefix = f"{org_id}/{project_id}/"
        paths: list[str] = []
        paginator = self._s3().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                paths.append(obj["Key"].removeprefix(prefix))
        return sorted(paths)

    def read(self, org_id: str, project_id: str, path: str) -> str:
        return self.get(f"s3://{self._bucket}/{org_id}/{project_id}/{path}")
