# Lead Intake MVP

Lead Intake MVP is a compact backend service for automated lead intake.
It receives webhook-style requests, validates payloads, stores leads in SQLite, and logs events.
The project demonstrates a practical API automation pipeline for learning and portfolio use.
Core flow: **Webhook/API -> Validation -> SQLite -> Event Log**.

---

## Название проекта

**Lead Intake MVP (Webhook -> SQLite -> Event Log)**

## Описание

Мини-сервис для автоматизации приёма лидов.
Эндпоинт `POST /lead` принимает заявку, валидирует данные, сохраняет запись в SQLite и фиксирует событие в `events.log`.

## Бизнес-проблема

В небольших командах заявки часто обрабатываются несистемно:

- обращения приходят из разных источников и теряются;
- менеджер узнаёт о новой заявке слишком поздно;
- контактные данные хранятся хаотично (чаты, таблицы, заметки).

Из-за этого снижается скорость реакции и теряются потенциальные клиенты.

## Решение

Сервис даёт единый и предсказуемый канал приёма заявок:

- `POST /lead` принимает структурированный JSON;
- валидация проверяет обязательные поля (в первую очередь `contact`);
- данные сохраняются в SQLite (`data/leads.db`);
- после успешного сохранения пишется событие в лог (`logs/events.log`);
- ошибки валидации и БД возвращаются с корректными HTTP-кодами.

## Стек технологий

- Python 3.10+
- FastAPI
- Uvicorn
- SQLite
- Pydantic
- Logging

## Возможности

- `POST /lead` — создание лида
- `GET /health` — проверка доступности сервиса
- валидация входящих данных
- хранение заявок в SQLite
- логирование событий в файл
- обработка ошибок (400 и 500)

## Структура проекта

```text
lead-intake-mvp/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   └── logger.py
├── data/
├── logs/
├── requirements.txt
├── README.md
├── .gitignore
└── .env.example
```

## Установка

1. Клонировать репозиторий:

```bash
git clone <your-repo-url>
cd lead-intake-mvp
```

2. Создать виртуальное окружение:

```bash
python -m venv .venv
```

3. Активировать виртуальное окружение:

- PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

- Bash:

```bash
source .venv/bin/activate
```

4. Установить зависимости:

```bash
pip install -r requirements.txt
```

## Запуск

Запуск сервера разработки:

```bash
uvicorn app.main:app --reload
```

После запуска:

- базовый URL: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Использование API

### `POST /lead`

Пример JSON-тела запроса:

```json
{
  "name": "Ирина",
  "contact": "+79990000000",
  "source": "landing",
  "comment": "Хочу консультацию по тарифам"
}
```

### `GET /health`

Простой health-check:

```bash
curl http://127.0.0.1:8000/health
```

## Примеры запросов PowerShell и curl

### PowerShell

```powershell
$body = @{
  name    = "Ирина"
  contact = "+79990000000"
  source  = "landing"
  comment = "Хочу консультацию по тарифам"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/lead" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

### curl

```bash
curl -X POST "http://127.0.0.1:8000/lead" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Ирина\",\"contact\":\"+79990000000\",\"source\":\"landing\",\"comment\":\"Хочу консультацию по тарифам\"}"
```

## Примеры ответов 200 / 400 / 500

### 200 OK (успешно)

```json
{
  "id": 1,
  "message": "Lead saved successfully."
}
```

### 400 Bad Request (ошибка валидации)

```json
{
  "detail": "contact: Field required"
}
```

или

```json
{
  "detail": "contact: Value error, Field 'contact' is required and must not be empty."
}
```

### 500 Internal Server Error (ошибка базы данных)

```json
{
  "detail": "Database error."
}
```

## Где смотреть результат

- База SQLite: `data/leads.db`
- Лог событий: `logs/events.log`
- Swagger-документация: `http://127.0.0.1:8000/docs`

## Скриншоты

Рекомендуемые файлы для демонстрации проекта:

- `screenshots/01_project_structure.png`
- `screenshots/02_successful_lead_request.png`
- `screenshots/03_validation_error_missing_contact.png`
- `screenshots/04_events_log.png`
- `screenshots/05_sqlite_leads_table.png`

## Возможности развития v2

- дедупликация лидов (по контакту/телефону/email);
- email-уведомления о новых заявках;
- Telegram-уведомления для менеджера;
- простая admin-панель для просмотра лидов;
- деплой на VPS (Nginx + systemd + HTTPS);
- интеграция с CRM (например, HubSpot/Bitrix24/AmoCRM).

## Позиционирование в портфолио

Проект можно использовать как учебный и практический MVP-кейс для откликов на стажировке и фриланс:

**Webhook -> DB -> Notification automation**

Он демонстрирует:

- проектирование API и валидацию данных;
- хранение данных и работу с SQLite;
- событийное логирование;
- аккуратную обработку ошибок;
- ориентацию на бизнес-задачу автоматизации приема лидов.
