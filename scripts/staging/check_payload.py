from __future__ import annotations

import sys

import httpx

from editorial_os_api.config import get_settings


def main() -> int:
    settings = get_settings()
    if settings.environment != "staging":
        raise SystemExit("Payload connectivity check is staging-only.")
    if not settings.payload_enabled:
        raise SystemExit("Payload integration is disabled.")
    if not settings.payload_base_url or not settings.payload_api_token:
        raise SystemExit("Payload staging URL/token is not configured.")

    if settings.payload_auth_mode == "api_key":
        authorization = (
            f"{settings.payload_auth_collection} API-Key "
            f"{settings.payload_api_token}"
        )
    else:
        authorization = f"Bearer {settings.payload_api_token}"

    response = httpx.get(
        (
            f"{settings.payload_base_url.rstrip('/')}/api/"
            f"{settings.payload_collection.strip('/')}"
        ),
        headers={"Authorization": authorization},
        params={"limit": "1", "depth": "0", "draft": "true"},
        timeout=15.0,
    )
    if response.status_code >= 400:
        print(
            f"Payload staging connectivity failed with HTTP "
            f"{response.status_code}.",
            file=sys.stderr,
        )
        return 1

    print("Payload staging connectivity verified with a read-only request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
