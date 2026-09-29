from editorial_os_api.domain.enums import SourceFailureKind


class SourceAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: SourceFailureKind,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.http_status = http_status
