from prometheus_client import Counter

_OUTCOMES = Counter(
    "user_profile_idempotency_outcomes_total",
    "Completed user profile idempotency coordinator outcomes.",
    ("outcome",),
)
_HOT_DEGRADED = Counter(
    "user_profile_idempotency_hot_degraded_total",
    "Redis idempotency hot-path degradations that used durable safety.",
    ("stage",),
)


class PrometheusIdempotencyMetrics:
    """Low-cardinality Prometheus metrics adapter for idempotency observability."""

    def observe_outcome(self, outcome: str) -> None:
        _OUTCOMES.labels(outcome=outcome).inc()

    def observe_hot_degraded(self, stage: str) -> None:
        _HOT_DEGRADED.labels(stage=stage).inc()
