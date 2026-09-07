# Проверки application handlers

Реализованы пять command handlers и шесть query handlers. Проверяется публичный
вызов `await handler(command_or_query)` с настоящими агрегатами и in-memory adapters.
Сборка HTTP/Kafka и подключение реальных repositories — отдельный этап.

## Отдельная проверка результата команды

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/handlers_tdd/commands/test_result_contract.py -q
```

Проверяются `async __call__`, тип аргумента команды, аннотация результата и фактическое
значение. Каждый handler вызывается при изменении и no-op. None допустим только
для команды с `BaseCommand[NoneType]`. Проверка полноты требует добавлять новые команды
в матрицу. Тест не является доказательством всех возможных ветвей выполнения;
runtime-проверка по зарегистрированной схеме выполняется pipeline до commit.

## Начать с одного сценария

Команды PowerShell из корня `services/user-profile-service`; используется существующая `.venv`.

Самый маленький первый шаг — проверка существования профиля:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/handlers_tdd/queries/test_profile_queries.py::test_check_profile_exists_reports_existing_and_absent_profiles -vv
```

1. Прочитать тест и соответствующие query/port. Первый запуск сообщает точный путь отсутствующего handler.
2. Создать только этот handler с публичным асинхронным `__call__` и зависимостями из таблицы ниже.
3. Добиться прохождения выбранного сценария минимальной реализацией.
4. Выбрать следующий сценарий того же handler; проверить RED → реализовать → проверить GREEN.
5. Упростить код при зелёных тестах. Затем запустить весь файл и существующие unit-тесты.

Для первого command handler:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/handlers_tdd/commands/test_create_default_profile.py -x -vv
```

Рекомендуемая последовательность: exists → get_my profile/settings → create_default →
update_avatar → update_profile → update/reset settings → публичное чтение, поиск и batch.
Каждый тест запускается отдельно; для выбора сценария достаточно дописать `::имя_теста`.

## Публичная граница и зависимости

Имена классов и параметры конструкторов ниже соответствуют реализованным handlers.
Единственное место сборки в тестах — `HANDLERS` и `HandlerHarness.handler()` в [support.py](support.py).
При другом соглашении о конструкторах достаточно изменить сборку; поведенческие тесты остаются прежними.

Пути в таблице относятся к `src/app/application/`; в каждом из них находится `handler.py`.

| Путь | Класс | Зависимости конструктора | Результат |
| --- | --- | --- | --- |
| commands/profiles/create_default | CreateDefaultProfileHandler | profiles, settings | None |
| commands/profiles/update | UpdateProfileHandler | profiles, clock | ProfileDTO |
| commands/profiles/update_avatar | UpdateAvatarHandler | profiles, clock | ProfileDTO |
| commands/settings/update | UpdateSettingsHandler | settings, clock | SettingsDTO |
| commands/settings/reset | ResetSettingsHandler | settings, clock | SettingsDTO |
| queries/profiles/get_my | GetMyProfileHandler | profiles | ProfileDTO |
| queries/profiles/get_public | GetPublicProfileHandler | profiles, settings | PublicProfileDTO |
| queries/profiles/search_by_username | SearchByUsernameHandler | profiles, settings | PublicProfileDTO при успешном поиске |
| queries/profiles/get_batch | GetBatchProfilesHandler | profiles, settings | Коллекция PublicProfileDTO |
| queries/profiles/check_exists | CheckProfileExistsHandler | profiles | bool |
| queries/settings/get_my | GetMySettingsHandler | settings | SettingsDTO |

`profiles` и `settings` для команд соответствуют repository ports,
для запросов — reader ports. `clock` — вызываемый объект без аргументов,
возвращающий timezone-aware `datetime`.
Search возвращает PublicProfileDTO либо ошибку, batch — list[PublicProfileDTO].

Handler не получает HTTP/Kafka context, idempotency key, ResultMode или UnitOfWork.
Транзакция и идемпотентность принадлежат command pipeline.
`CreateDefaultProfileCommand` возвращает None по контракту самой команды;
остальные команды возвращают свои DTO независимо от транспорта.
`COMPLETION_ONLY` применяется при dispatch, а не внутри handler.

## Какие сценарии подготовлены

Количество учитывает варианты параметризации.

| Тестовый файл | Сценариев | Что проверяет |
| --- | ---: | --- |
| commands/test_create_default_profile.py | 5 | Создание профиля и settings, сохранение существующих данных, заполнение отсутствующей половины, повторная инициализация |
| commands/test_update_profile.py | 9 | DTO и сохранение, неизменяемые соседние поля и другой пользователь, no-op, очистка bio, not found, устаревшая версия, занятый/reserved username, конкурирующая запись между чтением и сохранением |
| commands/test_update_avatar.py | 5 | Замена/удаление avatar, сохранение текста профиля, no-op, not found, конфликт версии |
| commands/test_update_settings.py | 6 | Preferences, частичное обновление privacy без сброса соседних правил, no-op, not found, конфликт версии, невалидный timezone без частичного сохранения |
| commands/test_reset_settings.py | 4 | Сброс всех preferences и privacy, no-op, not found, конфликт версии |
| queries/test_profile_queries.py | 12 | Свой и публичный DTO, маскирование bio/avatar, поиск username и приватность поиска, batch, exists, not found |
| queries/test_settings_queries.py | 2 | Свои settings и not found |
| test_support.py | 3 | Отделённые копии при чтении/записи, optimistic version check, интерфейс reader без методов записи |

Набор проверяет основные сценарии, а не исчерпывает все комбинации.
Например, матрицу owner/anonymous/privacy, гонки остальных изменяющих handlers
и ошибки реальных хранилищ следует расширять по мере реализации соответствующего поведения.

## Как работают фикстуры

`harness` создаётся заново для каждого теста, без Docker, базы данных и сетевых вызовов.

- `seed_profile()` / `seed_settings()` создают настоящие доменные агрегаты.
- `harness.now` фиксирован; тесты не зависят от системных часов и sleep.
- In-memory repositories копируют агрегаты при чтении и записи. Изменить полученный объект недостаточно для сохранения.
- Repository моделирует проверку версии и уникальности username, объявленную для persistence.
- `arrange_competing_write()` моделирует запись другого запроса перед сохранением: проверка версии только после чтения не должна позволить затереть победителя.
- Query handlers получают reader adapters с методами только для чтения. Создание default-данных из query не входит в контракт read-only query.

Доменные методы, DTO и policies используются настоящие.
Тесты не проверяют порядок внутренних вызовов и не подменяют бизнес-логику моками.

In-memory adapters **не доказывают SQL-атомарность, rollback, блокировки или реальные гонки**.
Проверка отсутствия частичного сохранения здесь относится к изменению одного агрегата.
Атомарное создание пары profile/settings и выполнение вместе с durable idempotency
требуют отдельного integration-теста через настоящий dispatch/UoW и БД после подключения handlers.

## Зафиксированное поведение

- Settings OCC использует SettingsVersionMismatchError и при загрузке, и при записи.
- Search нормализует Username. Скрытый и отсутствующий username дают UserProfileNotFoundError.
- При отсутствии settings публичное чтение, поиск и batch дают UserSettingsNotFoundError;
  автоматического создания настроек и раскрытия полей по default-policy нет.
- Batch возвращает существующие профили в порядке входных ID, пропускает отсутствующие;
  повторяющиеся ID удаляет сама query. Все статусы обрабатываются по текущим reader/policy
  контрактам: отдельная фильтрация disabled/blocked не добавлена.
- SettingsReader пока имеет только get_by_id: batch читает settings последовательно,
  максимум для 100 профилей. Массовый reader — возможная отдельная оптимизация.
- CreateDefaultProfileHandler использует registered_at для обеих сущностей.
- Транзакция, ResultMode и идемпотентность находятся снаружи handlers.

## Запуски и критерии готовности

Только новый набор:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/handlers_tdd -q --tb=short
```

Проверка вспомогательных адаптеров и существующей unit-регрессии:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/handlers_tdd/test_support.py tests/unit -q
& .\.venv\Scripts\python.exe -m ruff check tests/handlers_tdd
& .\.venv\Scripts\python.exe -m ruff format tests/handlers_tdd --check
```

Снимок проверки при подготовке набора, 2026-09-05:

- 43 handler-сценария — RED исключительно из-за отсутствующих handler-модулей.
- 3 теста адаптеров — PASS.
- 342 существующих unit-теста — PASS.
- Ошибок collection, skip или xfail в новом наборе нет.
- Integration-тесты в рамках этой подготовки не запускались.

Тесты импортируют будущие handlers внутри тела, поэтому отсутствие одного модуля
не ломает collection всего набора. После создания handler ошибки его собственных импортов
не маскируются под ожидаемый RED.

Набор handlers больше не находится в RED. Исторические результаты выше относятся
к подготовке набора. Общий pytest включает также заготовленные HTTP endpoint-тесты;
они требуют отдельной реализации транспортного слоя.

Handler готов к следующему этапу, когда его сценарии зелёные, существующие unit-тесты проходят,
а открытые вопросы для этого handler явно решены.
После этого нужен отдельный шаг регистрации и integration-проверки через application pipeline;
зелёные тесты прямого вызова handler ещё не доказывают его подключение к API/Kafka.
