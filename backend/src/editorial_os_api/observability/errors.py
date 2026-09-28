from editorial_os_api.observability.contracts import ErrorCategory


def classify_exception(error: Exception) -> ErrorCategory:
    name = type(error).__name__.lower()
    module = type(error).__module__.lower()

    if "budget" in name:
        return ErrorCategory.BUDGET
    if "validation" in name or "structuredoutput" in name:
        return ErrorCategory.VALIDATION
    if "transition" in name or "policy" in name:
        return ErrorCategory.POLICY
    if module.startswith(("sqlalchemy", "psycopg")):
        return ErrorCategory.PERSISTENCE
    if any(part in name for part in ("timeout", "provider", "connection", "http")):
        return ErrorCategory.PROVIDER
    return ErrorCategory.INTERNAL
