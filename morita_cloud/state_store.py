from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage


class LockUnavailable(RuntimeError):
    pass


class GcsStore:
    def __init__(self, bucket_name: str, client: storage.Client | None = None) -> None:
        if not bucket_name:
            raise ValueError("GCS bucket name is required")
        self.client = client or storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def exists(self, name: str) -> bool:
        return self.bucket.blob(name).exists(client=self.client)

    def read_json(self, name: str, default: dict[str, Any] | None = None) -> tuple[dict[str, Any], int | None]:
        blob = self.bucket.blob(name)
        try:
            blob.reload(client=self.client)
            generation = int(blob.generation) if blob.generation is not None else None
            raw = blob.download_as_text(client=self.client)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(f"GCS JSON object must be a mapping: {name}")
            return data, generation
        except NotFound:
            return dict(default or {}), None

    def write_json(self, name: str, data: dict[str, Any], generation: int | None = None) -> int:
        blob = self.bucket.blob(name)
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        blob.upload_from_string(
            payload,
            content_type="application/json",
            if_generation_match=0 if generation is None else generation,
        )
        blob.reload(client=self.client)
        return int(blob.generation)

    def upload_bytes(self, name: str, payload: bytes, content_type: str = "application/octet-stream") -> None:
        self.bucket.blob(name).upload_from_string(payload, content_type=content_type)

    def download_bytes(self, name: str) -> bytes:
        return self.bucket.blob(name).download_as_bytes(client=self.client)

    @contextmanager
    def lock(self, name: str, ttl_seconds: int = 2100) -> Iterator[None]:
        blob = self.bucket.blob(name)
        now = datetime.now(timezone.utc)
        payload = json.dumps({"created_at_utc": now.isoformat()})
        try:
            blob.upload_from_string(payload, content_type="application/json", if_generation_match=0)
        except PreconditionFailed:
            stale_removed = self._remove_stale_lock(name, ttl_seconds)
            if not stale_removed:
                raise LockUnavailable(f"Another tick is already running: gs://{self.bucket.name}/{name}")
            blob = self.bucket.blob(name)
            try:
                blob.upload_from_string(payload, content_type="application/json", if_generation_match=0)
            except PreconditionFailed as exc:
                raise LockUnavailable(f"Another tick acquired the lock: gs://{self.bucket.name}/{name}") from exc

        blob.reload(client=self.client)
        generation = int(blob.generation)
        try:
            yield
        finally:
            try:
                blob.delete(client=self.client, if_generation_match=generation)
            except (NotFound, PreconditionFailed):
                pass

    def _remove_stale_lock(self, name: str, ttl_seconds: int) -> bool:
        blob = self.bucket.blob(name)
        try:
            blob.reload(client=self.client)
            generation = int(blob.generation)
            raw = json.loads(blob.download_as_text(client=self.client))
            created = datetime.fromisoformat(str(raw["created_at_utc"]))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except (NotFound, KeyError, ValueError, json.JSONDecodeError):
            return False
        if datetime.now(timezone.utc) - created <= timedelta(seconds=ttl_seconds):
            return False
        try:
            blob.delete(client=self.client, if_generation_match=generation)
            return True
        except (NotFound, PreconditionFailed):
            return False
