"""Object storage for delivery photos and signatures.

`local` keeps files on disk (development / single node, served through an authenticated API endpoint).
`s3` signs short-lived presigned URLs (AWS Signature V4) so devices upload straight to any S3-compatible store
(AWS S3 in af-south-1, MinIO, Cloudflare R2, ...) and the API never proxies image bytes.
"""
import datetime as dt
import hashlib
import hmac
import mimetypes
import re
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit

from routebridge.config.settings import Settings, get_settings

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9/_\-.]{5,200}$")


def new_object_key(tenant_id, job_id, kind: str, content_type: str) -> str:
    if content_type not in ALLOWED_TYPES:
        raise ValueError("Only JPEG, PNG or WebP images are accepted")
    if kind not in {"photo", "signature"}:
        raise ValueError("kind must be photo or signature")
    return f"{tenant_id}/{job_id}/{kind}-{secrets.token_hex(8)}{ALLOWED_TYPES[content_type]}"


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key)) and ".." not in key


# ---- local disk ---------------------------------------------------------------------------------------------------


class LocalDiskStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not valid_key(key):
            raise ValueError("Invalid object key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid object key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> tuple[bytes, str]:
        path = self._path(key)
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"


# ---- S3-compatible (SigV4 presign) --------------------------------------------------------------------------------


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def presign_url(
    method: str,
    endpoint: str,
    bucket: str,
    key: str,
    region: str,
    access_key: str,
    secret_key: str,
    expires: int,
    now: dt.datetime | None = None,
    virtual_host: bool = False,
) -> str:
    """AWS Signature V4 query-string presign. `virtual_host=True` -> https://bucket.host/key, else path style."""
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    parts = urlsplit(endpoint)
    host = f"{bucket}.{parts.netloc}" if virtual_host else parts.netloc
    path = "/" + quote(key, safe="/~") if virtual_host else "/" + quote(f"{bucket}/{key}", safe="/~")
    scope = f"{date}/{region}/s3/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(f"{quote(k, safe='~')}={quote(v, safe='~')}" for k, v in sorted(query.items()))
    canonical_request = "\n".join([method, path, canonical_query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
    k = _sign(("AWS4" + secret_key).encode(), date)
    for part in (region, "s3", "aws4_request"):
        k = _sign(k, part)
    signature = hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{parts.scheme}://{host}{path}?{canonical_query}&X-Amz-Signature={signature}"


def s3_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return s.media_provider == "s3" and bool(s.s3_endpoint and s.s3_bucket and s.s3_access_key and s.s3_secret_key)


def presign_for(settings: Settings, method: str, key: str) -> str:
    return presign_url(method, settings.s3_endpoint, settings.s3_bucket, key, settings.s3_region, settings.s3_access_key, settings.s3_secret_key, settings.media_url_ttl_seconds)


def local_storage() -> LocalDiskStorage:
    return LocalDiskStorage(get_settings().media_dir)
