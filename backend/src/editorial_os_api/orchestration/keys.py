import hashlib


def stable_action_key(namespace: str, *parts: object) -> str:
    """Build a deterministic action key from stable external identifiers."""

    canonical = "|".join([namespace, *(str(part) for part in parts)])
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
