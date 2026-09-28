import re
from collections.abc import Mapping, Sequence

REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_PREFIX_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|sk-lf-[A-Za-z0-9_-]{8,}|phc_[A-Za-z0-9_-]{8,})\b"
)
_URL_CREDENTIAL_RE = re.compile(r"(://[^:/\s]+:)[^@/\s]+(@)")
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|credential)"
    r"\s*[:=]\s*[^,;\s]+"
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_text(value: str) -> str:
    value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    value = _SECRET_PREFIX_RE.sub(REDACTED, value)
    value = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]\2", value)
    return _KEY_VALUE_SECRET_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        value,
    )


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
