class PipelineError(Exception):
    """Base exception for pipeline failures."""


class CookieAuthError(PipelineError):
    """Raised when a stored browser session is missing or expired."""


class CookieRefreshError(PipelineError):
    """Raised when refreshed cookies cannot be pushed back to GitHub Secrets."""

