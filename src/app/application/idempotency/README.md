# Идемпотентность на application boundary

`CommandBus → CommandExecution → IdempotencyMiddleware → IdempotencyCoordinator → operation()`

Handler обрабатывает бизнес-команду. Entrypoint передаёт команду и контекст.
Регистрация handler определяет, нужна ли идемпотентность. Coordinator получает
исполняемый callback; он не ищет handler и не знает HTTP, SQLAlchemy или routing.

[Отдельная схема файлов](../../../../docs/idempotency-file-map.md) ·
[Разбор архитектуры](../../../../docs/idempotency-architecture-review.md)

Тип результата handler задаётся [контрактом команды](../commands/README.md).
Вызывающий код отдельно выбирает ResultMode: сохранить результат или только факт
выполнения. Правила «Kafka → None, HTTP → DTO» нет.

## Граница обёртки

`IdempotencyMiddleware.execute(operation, ...)` принимает callback, key, scope,
имя операции, fingerprint и policy. Возвращает `CompletedIdempotencyResult`.
Команда и CommandContext остаются в dispatching. ResultMode и преобразование
записи обратно в DTO также принадлежат CommandExecution.
[Пошаговый путь команды](../dispatching/README.md) объясняет порядок вызовов.

## Где задаётся политика

В `CommandHandlerRegistry.register(..., idempotency_policy=...)` при сборке приложения.
Команда остаётся DTO; её класс не содержит Redis, policy или middleware.
`BaseCommand[ResultT]` задаёт статический тип ответа для вызывающего кода,
а обязательный `result_type` при регистрации задаёт runtime-схему codec.

Пример регистрации существующей команды. Фабрика handler передаётся аргументом:
конкретные handlers/repositories профиля ещё предстоит подключить.

```python
from collections.abc import Callable

from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.dispatching.registry import CommandHandler, CommandHandlerRegistry
from app.application.dto.profiles import ProfileDTO
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


def profile_registry[DependenciesT](
    handler_factory: Callable[
        [DependenciesT], CommandHandler[UpdateProfileCommand, ProfileDTO]
    ],
) -> CommandHandlerRegistry[DependenciesT]:
    registry = CommandHandlerRegistry[DependenciesT]()
    registry.register(
        UpdateProfileCommand,
        handler_factory,
        result_type=ProfileDTO,
        operation="profile.update.v1",
        result_schema_version=1,
        idempotency_policy=IdempotencyPolicy(
            mode=IdempotencyMode.HOT_DURABLE,
            lease_seconds=30,
            retention_seconds=86_400,
            hot_cache_seconds=300,
        ),
    )
    return registry
```

Без `idempotency_policy` команда выполняется обычным транзакционным путём.
Для короткой защиты применяется `IdempotencyMode.HOT_ONLY`.
Policy неизменяема; значения положительны, durable cache TTL не больше retention.
Реестр проверяет дубли классов/operation, фабрику и схему результата. Создание bus
замораживает регистрации: менять смысл команды во время обработки нельзя.

`operation` — стабильное имя протокола. Переименование Python-класса его не меняет.
Несовместимое изменение смысла операции требует явного решения о namespace.
`result_schema_version` проверяется при replay: несовместимая версия даёт
`StoredReplayUnavailableError`, а не повторный вызов handler.

## Режим результата dispatch

`result_mode` описывает потребность caller независимо от транспорта:

```python
from app.application.dispatching.result_mode import ResultMode

result = await bus.dispatch(command, context, result_mode=ResultMode.REPLAYABLE)
await bus.dispatch(command, context, result_mode=ResultMode.COMPLETION_ONLY)
```

REPLAYABLE — режим по умолчанию: вернуть ResultT и сохранить snapshot.
COMPLETION_ONLY — проверить результат handler без JSON-сериализации,
сохранить только факт выполнения и вернуть None. Handler не получает режим
и продолжает возвращать свой обычный результат.

При отсутствии idempotency policy этот параметр управляет только возвратом:
completion marker никуда не сохраняется и дедупликации нет.

| Действующая запись | REPLAYABLE | COMPLETION_ONLY |
| --- | --- | --- |
| Snapshot результата | Сохранённый ResultT | None |
| Только факт выполнения | IdempotencyResultNotStoredError | None |

При запросе несохранённого результата handler повторно не вызывается.
Чтение текущего состояния ресурса не заменяет исходный snapshot.
В смешанной durable-гонке определяющей становится запись победителя; транзакция
проигравшего откатывается. ResultMode не входит в identity/fingerprint.
Completion-вызов не перезаписывает существующий snapshot.

Схема handler остаётся обязательной для обоих режимов. COMPLETION_ONLY экономит
сериализацию/хранение DTO, но не отменяет его построение внутри handler.
`ResultMode` и `IdempotencyPolicy.mode` независимы: первый управляет результатом,
второй — HOT_ONLY/HOT_DURABLE гарантиями.

## Что остаётся у entrypoint

1. Проверить caller и права на выполнение операции, включая повторные запросы.
2. Передать внешний ключ в `CommandContext.idempotency_key`.
3. Передать доверенный `idempotency_scope`, например `user:<verified-id>` либо
   `consumer:<name>:tenant:<verified-id>`.
4. Вызвать `bus.dispatch(command, context)` и перевести application exceptions
   в протокол транспорта.

Scope не читается из произвольного поля body. Автоматического fallback на
`actor_id`, `user_id` или `anonymous` нет. Для идемпотентной команды отсутствие
ключа/scope отклоняется middleware до handler. Повтор обязан не обходить
авторизацию: на replay handler может вообще не создаваться.

Идентичность: `scope + registered operation + SHA256(raw key)`.
CommandExecution вычисляет fingerprint по данным команды; correlation ID и прочие поля
контекста в него не входят. SHA-256 ключа не шифрует сохранённый результат.

## Сборка и транзакции

Готовая функция `infrastructure/di/command_bus.py:build_postgres_command_bus`
принимает registry, `async_sessionmaker`, `dependencies_factory(session)`,
HOT adapter и необязательные metrics/clock.

Каждый dispatch получает новую session, UoW, repositories/dependencies,
durable store, executor, coordinator и middleware. HOT adapter, circuit breaker
и connection pool могут жить всё приложение.

`dependencies_factory(session)` только собирает зависимости handler из
переданной session. Она не выполняет SQL и не открывает отдельную session.
Handler не вызывает commit/rollback. Его repositories и durable store используют
одну session. Это обязательная часть контракта атомарности.

| Регистрация | Кто владеет транзакцией | Что фиксируется |
| --- | --- | --- |
| Без policy | CommandExecution | Бизнес-изменения |
| HOT_ONLY | CommandExecution | Бизнес-изменения; HOT публикуется после commit |
| HOT_DURABLE | TransactionalIdempotencyExecution | Бизнес-изменения и replay-запись вместе |

Результат handler проверяется до commit в обоих ResultMode. REPLAYABLE дополнительно
сериализует результат и восстанавливает первое выполнение/replay по одной схеме.
COMPLETION_ONLY формирует отметку без payload и возвращает None. При конкурентном
durable execution возвращается результат победившей транзакции; локальная
попытка проигравшего откатывается.

Готовая PostgreSQL-сборка поддерживает обе policy. В HOT_ONLY обращения к durable
store отсутствуют. Для другого backend передаётся собственная scope factory
в `CommandBus`; coordinator менять не нужно. Без durable executor разрешён
HOT_ONLY, попытка HOT_DURABLE отклоняется до claim.

В репозитории пока нет конкретных profile handlers/repositories и их подключения
к HTTP/Kafka. Эта сборка не означает, что все endpoints сервиса уже реализованы.

## Режимы и гарантии

| Сценарий | HOT_ONLY / Ephemeral | HOT_DURABLE / Durable |
| --- | --- | --- |
| Результат сохранён | Replay из HOT | Replay из HOT либо DURABLE |
| HOT недоступен до claim | Ошибка; handler не стартует | Обращение к durable |
| Потеря HOT / eviction / restart | Возможен повтор бизнес-операции | Сохранённый durable результат восстанавливается |
| Потеря lease после старта | Старый worker ещё может выполнить эффект | Проигравшая локальная транзакция откатывается |
| Истёк retention | Ключ можно выполнить снова | Ключ можно выполнить снова |

HOT busy/conflict в durable-режиме сначала проверяется по durable winner.
Без winner возвращается соответствующая application exception. Чужой lease
нельзя перезаписать при прогреве. Ошибка HOT после durable commit не отменяет
успешный результат. В HOT_ONLY ошибка публикации может прийти уже после
бизнес-эффекта; она не означает rollback.

Durable-гарантия относится к локальным эффектам в общей транзакции и действует
в пределах retention. Callback может быть вызван несколько раз в конкурирующих
транзакциях. Внешние HTTP/Kafka эффекты требуют outbox и идемпотентных получателей.

## Один срок окончания replay

- `lease_seconds` — владение незавершённой попыткой; heartbeat продлевает его.
- `retention_seconds` — срок памяти результата.
- `hot_cache_seconds` — максимальное пребывание durable snapshot в HOT.
  В HOT_ONLY срок результата берётся из retention.
- `CompletedIdempotencyResult.expires_at` — абсолютный timezone-aware deadline.

В durable-режиме deadline вычисляется после получения/кодирования результата
перед его записью в общей транзакции. В HOT_ONLY — после выполнения callback,
включая локальный commit. Чтение и прогрев сохраняют исходный deadline.

Redis Lua атомарно устанавливает:
`TTL = min(cache limit, expires_at − Redis TIME)`.
Прогрев за секунду до expiry даёт не более секунды памяти. PostgreSQL не возвращает
истёкшие записи и заменяет их условным UPSERT. Coordinator дополнительно отказывается
от уже истёкшего snapshot перед ответом. Для согласованного времени нужны
синхронизированные часы узлов; инъекция clock предназначена также для тестов.

## Контракты хранения

`HotIdempotencyStore`: claim, renew, complete, release; изменение только владельцем.
`DurableIdempotencyStore`: чтение действующего результата, условная запись без
перезаписи действующего winner. Store самостоятельно не коммитит.
`DurableExecution`: атомарное выполнение callback и сохранение replay.
Последний контракт необходим: независимые get/save не закрывают окно сбоя
между бизнес-эффектом и replay.

`TransactionalIdempotencyExecution` подходит к storage с общей транзакцией
и rollback. Замена PostgreSQL на Cassandra требует реализации того же
атомарного контракта для выбранной модели данных; одного нового get/save adapter
недостаточно. Универсальная гарантия для произвольного callback не обещается.

## Формат и ошибки

Для REPLAYABLE codec хранит JSON snapshot `{"value": ...}` с явной версией.
Поддерживаются DTO, dict, list, scalar и None. COMPLETION_ONLY использует
`StoredResult.completion()`: `result_type="completion"`, payload/resource отсутствуют.
Модель и SQL constraint запрещают смешивать marker и данные результата.
Сохранённый snapshot `{"value": null}` остаётся полноценным результатом None.
Resource-reference поля существуют, но стандартный codec не загружает ресурс.

Ошибки: `IdempotencyKeyRequiredError`, `IdempotencyScopeRequiredError`,
`IdempotencyConflictError`, `IdempotencyInProgressError`,
`IdempotencyUnavailableError`, `StoredReplayUnavailableError`,
`IdempotencyResultNotStoredError`. Последняя означает успешное выполнение без
сохранения результата, а не временную ошибку инфраструктуры.
Bus не разбирает состояния EXECUTED/REPLAY/CONFLICT.

SQL UoW классифицирует известные serialization/deadlock и connection/timeout
ошибки. Неизвестные SQL/handler ошибки не маскируются под replay.
Недоступность при commit может означать неизвестный исход операции.

HOT формат и namespace теперь `v2` из-за обязательного `expires_at`.
Старые записи не удаляются. Для HOT_ONLY переход namespace обнуляет доступную
новой версии память о повторах; rollout старых и новых workers требует отдельного
перехода. Durable сохраняет SQL deadline в уже существующей колонке.
Старые/несовместимые snapshot-схемы нельзя считать автоматически мигрированными.

AES-GCM adapter существует отдельно и в pipeline не подключён.
Prometheus и circuit breaker используются только при явной передаче адаптеров
в сборку; их наличие не означает включённую телеметрию/защиту.

## Обновление установленной схемы

Completion marker использует существующие поля:
`result_type="completion"`, `result_payload=NULL`, resource-поля NULL.
Отдельного столбца и изменения identity не требуется.

Для новой БД `IdempotencyRecordORM` уже содержит обновлённый CHECK constraint.
Для существующей таблицы перед включением COMPLETION_ONLY необходимо применить
[001_allow_completion_marker.sql](../../infrastructure/idempotency/postgres/migrations/001_allow_completion_marker.sql)
в схеме сервиса. Скрипт заменяет только ограничение
`ck_idempotency_records_replayable_result` и не удаляет записи.
После этого все workers должны поддерживать completion marker, прежде чем
вызывающий код начнёт использовать новый режим. Автоматического запуска миграции нет.

HOT envelope/namespace остаётся v2: marker передаётся через существующий формат.
Старые snapshot-записи продолжают читаться, смена namespace или очистка кеша
для ResultMode не нужны. Старые версии кода не умеют читать marker, поэтому
обновление readers должно предшествовать его записи.

## Проверка

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_idempotency_postgres.py tests/integration/test_idempotency_redis.py -q
```

Для реальных adapters нужны `TEST_IDEMPOTENCY_POSTGRES_DSN` и
`TEST_IDEMPOTENCY_REDIS_URL`. SQL fixture использует свою временную schema,
Redis fixture — свой namespace. Без подключения тесты явно пропускаются.
