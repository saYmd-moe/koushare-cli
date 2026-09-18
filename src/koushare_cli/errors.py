class KoushareError(RuntimeError):
    """Base error for koushare-cli."""


class UnsupportedUrl(KoushareError):
    """Raised when a Koushare URL cannot be interpreted."""


class ApiError(KoushareError):
    """Raised when the Koushare API returns an unsuccessful response."""


class DownloadError(KoushareError):
    """Raised when the selected downloader fails."""
