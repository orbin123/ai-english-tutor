"""Quota enforcement errors."""


class QuotaError(Exception):
    """Base for quota-related failures."""


class QuotaExceeded(QuotaError):
    """Raised when a daily or monthly free-capacity limit is reached."""

    def __init__(
        self,
        *,
        metric: str,
        period_type: str,
        period_key: str,
        limit: int,
        attempted: int,
    ) -> None:
        self.metric = metric
        self.period_type = period_type
        self.period_key = period_key
        self.limit = limit
        self.attempted = attempted
        super().__init__(
            f"Monthly free capacity reached for {metric} "
            f"({period_type} {period_key}: limit {limit}, attempted {attempted})"
        )
