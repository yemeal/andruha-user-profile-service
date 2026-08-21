# Слой портов приложения (`app.application.ports`)

Слой портов объявляет **интерфейсные контракты (Protocols)**, через которые Прикладной слой взаимодействует с внешней инфраструктурой (реляционными базами данных, транзакционными контекстами, кэшами, брокерами сообщений) по принципам **Чистой Архитектуры (Clean Architecture)**, **CQRS**, **Инверсии Зависимостей (DIP)** и **Разделения Интерфейсов (ISP)**.

Порты полностью изолируют бизнес-логику от деталей реализации (SQLAlchemy, PostgreSQL, Redis, Kafka) и определяют требования прикладного слоя к адаптерам внешнего мира.

---

## Архитектура портов

```
src/app/application/ports/
├── __init__.py
├── deduplication.py             # Порт дедупликации входящих событий EventDeduplicationPort
└── persistence/                 # Порты взаимодействия с персистентным хранилищем
    ├── __init__.py
    ├── unit_of_work.py          # Транзакционный менеджер AsyncUOWProtocol
    ├── repositories/            # Порты транзакционного изменения агрегатов (Write Side)
    │   ├── __init__.py
    │   ├── base.py              # Базовый generic CRUD-протокол AsyncRepositoryProtocol
    │   ├── profiles.py          # ProfileRepositoryProtocol
    │   └── settings.py          # SettingsRepositoryProtocol
    └── readers/                 # Порты чтения и проекций данных (Read Side / Projections)
        ├── __init__.py
        ├── profiles.py          # ProfileReaderProtocol
        └── settings.py          # SettingsReaderProtocol
```

---

## 1. Репозитории доменных агрегатов (`app.application.ports.persistence.repositories`)

* **`AsyncRepositoryProtocol[EntityT, IdT]`** — обобщённый асинхронный контракт хранилища данных (Generic Repository).
* **`ProfileRepositoryProtocol`** — порт репозитория агрегата `UserProfile` для операций мутации и оптимистической блокировки (OCC).
* **`SettingsRepositoryProtocol`** — порт репозитория агрегата `UserSettings` для операций изменения настроек.

---

## 2. Ридеры данных (`app.application.ports.persistence.readers`)

* **`ProfileReaderProtocol`** — порт выборки данных профилей для сценариев чтения: получение по ID, поиск по username, пакетные выборки и проверка существования.
* **`SettingsReaderProtocol`** — порт выборки данных настроек пользователя для сценариев чтения.

---

## 3. Транзакционные границы (`app.application.ports.persistence.unit_of_work`)

* **`AsyncUOWProtocol`** — порт управления транзакционным контекстом (Unit of Work) для обеспечения атомарности (ACID) над транзакционными операциями.

---

## 4. Дедупликация событий (`app.application.ports.deduplication`)

* **`EventDeduplicationPort`** — порт идемпотентного барьера (Inbox Fence) для защиты от повторной обработки событий брокера.
