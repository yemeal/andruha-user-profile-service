# Контракт результата команды и dispatch

Handler возвращает результат своего application-сценария. Вызывающий код
отдельно выбирает, нужен ли этот результат и его сохранение для повторов.
Источник команды — HTTP, Kafka или внутренний вызов — этого не определяет.

## Контракт handler

| Сценарий | Команда | Handler | Регистрация |
| --- | --- | --- | --- |
| Операция предоставляет данные результата | `BaseCommand[ResultDTO]` | `async def ... -> ResultDTO` | `result_type=ResultDTO` |
| Операция не предоставляет данных результата | `BaseCommand[NoneType]` | `async def ... -> None` | `result_type=NoneType` |

`NoneType` импортируется из `types`. В существующем коде
[CreateDefaultProfileCommand](profiles/create_default/command.py) имеет результат
NoneType, а [UpdateProfileCommand](profiles/update/command.py) — ProfileDTO.
Это контракты сценариев, а не ограничения на источник доставки.

`BaseCommand[ResultT]` и аннотация handler задают статический контракт.
`CommandHandlerRegistry.register(..., result_type=...)` явно задаёт ту же
схему для runtime-проверки. Реестр не извлекает generic-тип через Pydantic metadata.
Согласованность декларации команды и регистрации проверяется при разработке.
[Отдельный unit-тест](../../../../tests/handlers_tdd/commands/test_result_contract.py)
проверяет для каждой команды аннотации `__call__` и фактическое возвращаемое значение
в сценариях изменения и no-op. Новый command.py требует добавить случай в этот тест.
Извлечение generic metadata используется только тестом, не рабочим pipeline.

Перед commit codec проверяет результат по зарегистрированной схеме. Для DTO
требуется экземпляр соответствующего класса: словарь не преобразуется в DTO
незаметно. Неправильный результат откатывает транзакцию и в COMPLETION_ONLY.
Прямой вызов handler вне pipeline сам по себе runtime-проверку codec не запускает.

## Режим результата dispatch

`ResultMode` находится в [application/dispatching/result_mode.py](../dispatching/result_mode.py).
Передаётся keyword-only параметром `result_mode`:

```python
from app.application.dispatching.result_mode import ResultMode

# Вернуть результат и сохранить snapshot для повторов.
profile = await bus.dispatch(command, context, result_mode=ResultMode.REPLAYABLE)

# Выполнить ту же команду, вернуть None и сохранить только факт выполнения.
await bus.dispatch(command, context, result_mode=ResultMode.COMPLETION_ONLY)
```

`REPLAYABLE` используется по умолчанию и сохраняет прежнее поведение.
Overload-сигнатуры bus связывают REPLAYABLE с ResultT, COMPLETION_ONLY с None;
для переменного режима тип ответа — ResultT | None.

Handler получает только command. Его результат проверяется по зарегистрированной
схеме до commit в обоих режимах. При COMPLETION_ONLY DTO не сериализуется
и не передаётся в storage. Handler всё ещё может строить DTO; этот режим
не оптимизирует внутреннюю работу бизнес-операции.

Если idempotency policy отсутствует, COMPLETION_ONLY только проверяет результат
и возвращает None после транзакции. Записи идемпотентности не появляются,
повторный dispatch снова выполняет handler.

## Что сохраняется

| Режим | Сохранённое представление | Ответ dispatch |
| --- | --- | --- |
| REPLAYABLE | Snapshot результата с `result_payload={"value": ...}` | ResultT |
| COMPLETION_ONLY | `result_type="completion"`, payload и resource reference отсутствуют | None |

Для команды с ResultT=NoneType режим REPLAYABLE сохраняет snapshot
`{"value": null}`. Это отличается от completion marker: результат None
сохранён и может быть возвращён при повторном REPLAYABLE.

Policy HOT_ONLY/HOT_DURABLE определяет гарантии и сроки памяти. ResultMode
определяет содержимое записи и ответ caller; эти два выбора независимы.
Marker сохраняет identity, fingerprint и expiry, поэтому проверка конфликтов,
владения lease и срока идемпотентности продолжает действовать.

## Повторы и конкуренция

Для одинакового ключа, scope и команды в пределах retention:

| Сохранена запись | Запрошен REPLAYABLE | Запрошен COMPLETION_ONLY |
| --- | --- | --- |
| Snapshot | Вернуть сохранённый результат | Вернуть None |
| Completion marker | IdempotencyResultNotStoredError | Вернуть None |

`IdempotencyResultNotStoredError` означает: операция уже выполнена, результат
намеренно не сохранён. Handler не запускается повторно, текущие данные ресурса
не подставляются вместо первоначального результата. Это не временная
недоступность storage; повтор того же запроса не восстановит отсутствующий DTO.

ResultMode не входит в identity или fingerprint. Изменение режима не создаёт
новую операцию. Completion-вызов не удаляет ранее сохранённый snapshot.
При конкурентных durable попытках определяющей становится запись победителя;
проигравшие бизнес-изменения откатываются до возврата или ошибки.

После истечения retention запись перестаёт защищать от нового выполнения —
это одинаково для snapshot и marker.

## Граница транспорта

Transport adapter формирует command/context, выбирает ResultMode и обрабатывает
результат или application exception. HTTP-статусы, headers и Kafka acknowledgements
остаются в adapter. Application не ветвится по имени другого сервиса или транспорта.

Одна команда и один handler могут вызываться с разными ResultMode.
Дублировать команды ради HTTP/Kafka или передавать `is_kafka` в handler не нужно.
Command handlers реализованы; их регистрацию и transport adapters ещё предстоит подключить.

[Подключение идемпотентности и обновление схемы](../idempotency/README.md).
