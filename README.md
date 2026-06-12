# AI Life Planner

AI Life Planner — это AI-планировщик дня, который помогает пользователю не заполнять ежедневник вручную.

Пользователь пишет обычным языком:

> Сегодня работаю до 18:00, хочу сходить в зал, подготовиться к собесу и не потратить больше 1500 рублей.

Система должна:
- извлекать задачи;
- понимать ограничения;
- учитывать время, бюджет и энергию;
- строить реалистичный план дня;
- перепланировать день при изменениях.

## Текущий статус

Первый development step:

- FastAPI backend;
- endpoint `/health`;
- PostgreSQL через Docker Compose;
- базовая структура проекта;
- SQLAlchemy config;
- Alembic config;
- `.env.example`.

Пока не реализовано:

- Telegram bot;
- LLM-интеграция;
- бизнес-логика планирования;
- сущности задач и целей.

## Структура проекта

```text
ai-life-planner/
├── app/
│   ├── main.py
│   ├── api/
│   ├── bot/
│   ├── core/
│   ├── db/
│   ├── llm/
│   ├── models/
│   ├── schemas/
│   └── services/
├── migrations/
├── tests/
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Быстрый запуск

### 1. Создать `.env`

```bash
cp .env.example .env
```

На Windows CMD:

```cmd
copy .env.example .env
```

### 2. Поднять PostgreSQL

```bash
docker compose up -d postgres
```

### 3. Создать venv

```bash
python -m venv .venv
```

Windows CMD:

```cmd
.venv\Scripts\activate
```

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 4. Установить зависимости

```bash
pip install -r requirements.txt
```

### 5. Запустить backend

```bash
uvicorn app.main:app --reload
```

### 6. Проверить health endpoint

Открой в браузере:

```text
http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "service": "ai-life-planner"
}
```

## Следующий шаг

После запуска skeleton нужно сделать второй development step:

1. Создать модели БД:
   - User;
   - Goal;
   - Task;
   - DayPlan;
   - PlanItem.

2. Создать миграции Alembic.

3. Добавить Telegram bot `/start`.

4. Добавить сохранение пользователя в БД.
