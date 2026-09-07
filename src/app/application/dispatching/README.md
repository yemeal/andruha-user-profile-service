# Как выполняется команда

Начни с [execution.py](execution.py): это место, где соединяются хендлер,
транзакция и обёртка идемпотентности. Redis и PostgreSQL находятся за обёрткой.
Чтобы написать хендлер, их внутреннюю координацию знать не требуется.

## Один вызов от входа до ответа

```python
result = await bus.dispatch(command, context, result_mode=ResultMode.REPLAYABLE)
```

1. [bus.py](bus.py) находит регистрацию по типу команды.
2. `scope_factory()` создаёт отдельные зависимости для этого вызова.
   В [PostgreSQL-сборке](../../infrastructure/di/commands.py) это новая session,
   репозитории, UoW и экземпляры исполнителей. `handler_factory(dependencies)`
   позднее создаст сам хендлер; фабрика — обычная функция создания объекта.
3. [execution.py](execution.py) готовит функцию `invoke_handler`.
   Определение `async def` ничего не выполняет. Это отложенная операция,
   которую можно передать обёртке, и только `await operation()` запустит её.
4. Без policy исполнитель запускает операцию в UoW. С policy передаёт её
   [IdempotencyMiddleware](../idempotency/middleware.py).
5. Обёртка возвращает запись результата: после первого выполнения или из памяти
   повторов. На replay `invoke_handler` вообще не вызывается.
6. Исполнитель возвращает DTO через codec или `None` при COMPLETION_ONLY.
   Хендлеры всегда выполняют свой обычный контракт результата.

## Две вложенные функции в execution.py

| Функция | Что произойдёт, когда её вызовут |
| --- | --- |
| `invoke_handler()` | Создать хендлер → вызвать его → проверить результат → подготовить snapshot или marker |
| `run_transaction()` | Войти в UoW → вызвать `invoke_handler()` → выйти с commit либо rollback |

Вызов `return` внутри `async with` сначала выполняет выход из контекста.
Поэтому результат хендлера ещё не означает успешный commit.
Если проверка результата или commit завершатся ошибкой, успешного ответа не будет.

## Почему для идемпотентности передаются разные callbacks

| Режим | Передаваемая операция | Кто владеет транзакцией |
| --- | --- | --- |
| Без policy | Обёртка не вызывается | `run_transaction` в CommandExecution |
| HOT_ONLY | `run_transaction` | CommandExecution; Redis запоминает результат после commit |
| HOT_DURABLE | `invoke_handler` | TransactionalIdempotencyExecution: бизнес-изменение и запись результата фиксируются вместе |

Во втором случае нельзя обернуть callback ещё одной транзакцией: получится
вложенный UoW. Репозитории хендлера и durable store должны использовать одну session.

## Контракт отдельного модуля идемпотентности

Вход обёртки: callback `operation`, key, доверенный scope, имя операции,
отпечаток данных и policy. Callback возвращает `StoredResult`.
Выход: `CompletedIdempotencyResult` либо ошибка.

Обёртка не импортирует `BaseCommand`, `CommandContext`, `ResultMode` и не создаёт
хендлер. Внутри неё coordinator управляет Redis, lease и heartbeat, а durable
executor управляет атомарной записью в PostgreSQL. Их гарантии не изменены.
Формат snapshot/marker принадлежит хранению, выбор режима вызова — dispatching.

```text
Первый вызов с HOT_DURABLE:
  bus → execution → обёртка → coordinator → durable executor
      → UoW [хендлер → snapshot/marker → запись результата] → commit
      → публикация результата в Redis → execution → ответ

Повтор с готовым результатом в Redis:
  bus → execution → обёртка → coordinator → Redis
      → execution → ответ (без хендлера)
```

При промахе Redis durable executor может вернуть существующий результат PostgreSQL.
Потеря Redis и одновременные попытки обрабатываются внутри модуля; полный контракт —
в [руководстве по идемпотентности](../idempotency/README.md).

## Где менять поведение

- Новая бизнес-операция: команда, хендлер, регистрация.
- Выбор ответа/подтверждения: [result_mode.py](result_mode.py) и execution.
- Защита повторов и её сроки: модуль idempotency.
- SQL/Redis команды и соединения: infrastructure.

`dispatching/__init__.py` не импортирует bus и registry автоматически.
Используй прямые импорты, например
`from app.application.dispatching.result_mode import ResultMode`.
Это позволяет импортировать маленький контракт без загрузки всей цепочки.
