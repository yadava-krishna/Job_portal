"""Private file storage behind one interface. Callers use keys like "users/3/exports/12/<sha>.pdf", never paths.

LocalStorage (beta: files under STORAGE_DIR on the persistent volume) is the default. S3Storage is the AWS
migration target (private bucket, short-lived pre-signed downloads); it needs boto3 and STORAGE_S3_BUCKET and is
not configured in the private beta.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path, PurePosixPath

from backend.config import get_settings


class StorageError(Exception):
    pass


def _check_key(key: str) -> str:
    p = PurePosixPath(key)
    if p.is_absolute() or ".." in p.parts or not key or "\\" in key:
        raise StorageError(f"invalid storage key: {key!r}")
    return str(p)


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / _check_key(key)).resolve()
        if self.root not in path.parents:
            raise StorageError("key escapes the storage root")
        return path

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def local_path(self, key: str) -> Path:
        return self._path(key)


class S3Storage:  # pragma: no cover - not used in the private beta
    def __init__(self, bucket: str):
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise StorageError("S3 storage needs boto3, which is not installed in the beta image") from exc
        self.bucket, self.s3 = bucket, boto3.client("s3")

    def put(self, key: str, data: bytes) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=_check_key(key), Body=data, ServerSideEncryption="AES256")
        return key

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=_check_key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=_check_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=_check_key(key))

    def presigned_url(self, key: str, seconds: int = 300) -> str:
        return self.s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": _check_key(key)}, ExpiresIn=seconds)


@lru_cache(maxsize=1)
def _cached(kind: str, root: str, bucket: str):
    return S3Storage(bucket) if kind == "s3" else LocalStorage(Path(root))


def get_storage():
    s = get_settings()
    kind = os.environ.get("STORAGE_BACKEND", "local")
    return _cached(kind, str(s.storage_dir), os.environ.get("STORAGE_S3_BUCKET", ""))
