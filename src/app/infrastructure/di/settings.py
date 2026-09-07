import dishka
from dishka import Provider, Scope

from app.core.settings import (
    AppSettings,
    IdempotencySettings,
    PostgresSettings,
    RedisSettings,
    Settings,
    get_settings,
)


class SettingsProvider(Provider):
    scope = Scope.APP

    @dishka.provide
    def settings(self) -> Settings:
        return get_settings()

    @dishka.provide
    def app_settings(self, settings: Settings) -> AppSettings:
        return settings.app

    @dishka.provide
    def postgres_settings(self, settings: Settings) -> PostgresSettings:
        return settings.postgres

    @dishka.provide
    def redis_settings(self, settings: Settings) -> RedisSettings:
        return settings.redis

    @dishka.provide
    def idempotency_settings(self, settings: Settings) -> IdempotencySettings:
        return settings.idempotency
