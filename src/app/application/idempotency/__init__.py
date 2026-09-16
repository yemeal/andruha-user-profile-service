"""Application idempotency policy.

CommandBus integrates through idempotency.middleware.IdempotencyMiddleware.
Composition code imports the needed classes from their owning modules; importing
a model or a port must not eagerly load the entire execution pipeline.
"""
