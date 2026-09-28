from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.contracts import RawFetchBatch, SourceSnapshot
from editorial_os_api.scout.errors import SourceAdapterError


class RSSHubAdapter(RssAtomAdapter):
    name = "rsshub"

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        if not source.base_url:
            raise SourceAdapterError(
                "RSSHub source requires a base_url for the RSSHub instance.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )
        route = source.config.get("route")
        if not isinstance(route, str) or not route.strip():
            raise SourceAdapterError(
                "RSSHub source requires config.route.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )

        url = f"{source.base_url.rstrip('/')}/{route.lstrip('/')}"
        return self.fetch_url(source, url)
