import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from editorial_os_api.scout.contracts import RawSourceItem

_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}
_WHITESPACE_RE = re.compile(r"\s+")


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError(f"Unsupported or incomplete URL: {url!r}.")
    port = parsed.port

    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = hostname
    else:
        netloc = f"{hostname}:{port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
        and not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    query.sort()

    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def normalized_text(value: str | None) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def identity_key(
    source_id: UUID,
    *,
    external_id: str | None,
    canonical_url: str,
) -> str:
    identity = normalized_text(external_id) or canonical_url
    return hashlib.sha256(f"{source_id}:{identity}".encode()).hexdigest()


def content_fingerprint(item: RawSourceItem, canonical_url: str) -> str:
    components = (
        canonical_url,
        normalized_text(item.title),
        normalized_text(item.summary),
        normalized_text(item.body),
    )
    return hashlib.sha256("\n".join(components).encode()).hexdigest()
