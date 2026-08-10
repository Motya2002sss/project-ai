---
aliases:
  - Mobile API v1
  - iOS API Contract
type: architecture
status: active
area: backend
updated: 2026-08-10
---

# Mobile API Contract v1

> **iOS-first. Android later. Web/Telegram frozen. Backend is the single product brain.**

## 1. Назначение

Контракт покрывает первый iOS vertical slice:

```text
Открыть приложение
→ загрузить Today
→ написать изменение
→ получить clarification / confirmation / conflict / applied result
→ увидеть согласованный перестроенный день
→ отметить задачу выполненной
```

Mobile не реализует parser, scheduler, AI planning logic, conflict detection или расчёт progress/current task. Он хранит только cache и незавершённый draft.

## 2. Текущее состояние backend

Уже готовы:

- FastAPI, PostgreSQL, SQLAlchemy и Alembic;
- единый `process_user_message()` для text и готовых voice transcripts;
- mock/OpenAI-compatible/Ollama interpretation с Pydantic validation и fallback;
- deterministic Planning Engine с timezone, work/sleep availability и no-overlap invariant;
- fixed, flexible, unscheduled и completed plan items;
- factual `PlanDiff`;
- persistent user-scoped clarification, confirmation и conflict context;
- confirmation по plan version;
- idempotency receipt по `(user_id, request_id)`;
- atomic `DaySnapshot` после message mutation;
- routines с ограниченными cadence;
- ownership check для task status.

Frozen compatibility API остаётся под `/api`. Он принимает `user_external_id` и не является production-safe mobile contract.

## 3. Архитектура

```text
iOS
 ↓
FastAPI /api/v1
 ↓
process_user_message()
 ↓
message interpretation
 ↓
clarification / confirmation / conflict
 ↓
deterministic Planning Engine
 ↓
PostgreSQL
 ↓
DaySnapshot + factual PlanDiff
 ↓
iOS
```

Voice использует тот же путь после transcription:

```text
audio → transcription service → text → process_user_message() → Planning Engine
```

## 4. Authentication

Каждый Mobile API request передаёт:

```http
Authorization: Bearer <MOBILE_DOGFOOD_TOKEN>
```

P0 local dogfooding:

- backend token хранится в локальном `.env` и не попадает в Git;
- локальная iOS build получает тот же shared secret через untracked `.xcconfig` или launch provisioning, сохраняет его в Keychain и не содержит token в source code;
- simulator может использовать local HTTP только в development; physical-device dogfooding передаёт bearer token только по HTTPS;
- backend связывает token с `MOBILE_DOGFOOD_USER_EXTERNAL_ID`;
- body и path не принимают user id;
- missing/invalid credentials возвращают `401`;
- не настроенный server token возвращает `503`.

Это не TestFlight auth. Для multi-user версии нужен Sign in with Apple boundary: backend проверяет Apple identity token и разрешает стабильный `(provider, subject)` в собственный `users.id`.

Compatibility `/api` блокирует зарезервированные `mobile:*` identities, поэтому знание server-owned external id не обходит bearer boundary.

## 5. Реализованные endpoints

### `GET /api/v1/today`

Возвращает один актуальный `DaySnapshot` текущего дня пользователя.

Ключевые поля:

```json
{
  "date": "2026-08-10",
  "focus_text": "Сначала — Подготовить презентацию.",
  "progress": {"done": 1, "total": 3},
  "scheduled_items": [],
  "unscheduled_items": [],
  "completed_items": [],
  "current_item": null,
  "day_context": {
    "energy_level": null,
    "budget_limit": null,
    "work_override_mode": "busy",
    "work_start_time": "09:00:00",
    "work_end_time": "20:00:00"
  },
  "tasks": [],
  "goals": [],
  "routines": [],
  "plan": {},
  "plan_version": 4
}
```

Semantics:

- `scheduled_items` — timeline items с сохранённым временем, включая completed history;
- `unscheduled_items` — items без времени; legacy semantics сохранены для совместимости;
- `completed_items` — factual subset со status `done` независимо от наличия времени;
- `current_item` — только planned item, интервал которого содержит текущий момент в timezone пользователя; иначе `null`;
- `progress` считается по persisted tasks, а не клиентом.

### `POST /api/v1/capture`

Request:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "Сегодня задержусь на работе до 20"
}
```

`request_id` обязателен. При transport timeout iOS повторяет тот же request с тем же id.

Response:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "applied",
  "reply_text": "Сегодня рабочее время учтено до 20:00.",
  "retryable": false,
  "plan_diff": {
    "created_task_ids": [],
    "updated_task_ids": [],
    "completed_task_ids": [],
    "cancelled_task_ids": [],
    "moved_plan_items": [],
    "unscheduled_task_ids": [],
    "created_routine_ids": [],
    "availability_change": "Доступность сегодня обновлена: до 20:00.",
    "conflict": null,
    "clarification": null
  },
  "clarification": null,
  "confirmation": null,
  "conflict": null,
  "day_snapshot": {}
}
```

Допустимые lifecycle states: `applied`, `clarification_required`, `confirmation_required`, `conflict`, `no_change`, `unsupported_capability`, `failed`.

Raw parser payload и внутренний `user_external_id` не входят в mobile response.

### `POST /api/v1/interactions/{interaction_id}/responses`

Option response:

```json
{
  "request_id": "interaction-answer-1",
  "option_id": "one_time",
  "text": "разовая задача"
}
```

Free-text response:

```json
{
  "request_id": "interaction-answer-2",
  "text": "Поставь в 20:00"
}
```

Должен присутствовать `option_id` или непустой `text`. Endpoint использует тот же persistent interaction context и возвращает тот же `MobileActionResponse`, что capture.

Чужой, resolved или expired interaction не применяется.

### `PATCH /api/v1/tasks/{task_id}/status`

Request:

```json
{"status": "done"}
```

Допустимы только `planned` и `done`.

Response:

```json
{
  "status": "applied",
  "task": {"id": 42, "status": "done"},
  "plan_diff": {"completed_task_ids": [42]},
  "day_snapshot": {}
}
```

Backend фильтрует task по `task_id + authenticated user_id`, перестраивает день и возвращает согласованный snapshot. Чужая и отсутствующая task дают одинаковый `404 Task not found`.

## 6. Clarification, confirmation и conflict

Clarification возвращает:

- `id` контекста;
- один вопрос;
- варианты `{id, label, value}`;
- `free_text_allowed`;
- `expires_at`.

До ответа никакая неоднозначная task/routine не создаётся.

Confirmation возвращает proposal с factual changes, `apply/cancel`, expiry и `base_plan_version`. Backend применяет proposal только после ответа и отвергает stale version.

Fixed conflict возвращает structured conflict и варианты следующего действия. Mobile не вычисляет overlap.

## 7. Week API — gap, не реализовано

Минимальный будущий endpoint:

```text
GET /api/v1/week?start=2026-08-10
```

Response содержит ровно семь backend-generated `DaySummary`: date, focus, progress, scheduled count, unscheduled count, completed count и plan version. Это read model, не calendar CRUD и не calendar sync.

## 8. Path / Goals — реальные данные и gap

Текущая `Goal` хранит:

- `id`, `title`, `category`, `priority`, `target_date`, `status`;
- relation к tasks.

Текущий public `GoalResponse` не отдаёт `target_date`. Истории progress, milestones, metric baseline/current value и goal events нет. Поэтому экран «Путь» сейчас может честно показать только список целей и связанные задачи; процент выполнения недостоверен и запрещён.

До отдельной модели progress endpoint `/path` не реализуется.

## 9. Profile — текущие данные и gap

В `User` есть name, timezone, постоянные work start/end и sleep time. Frozen API предоставляет только read endpoint. Нет:

- mobile profile endpoint;
- mutation timezone/work/sleep через typed settings request;
- общей модели пользовательских preferences;
- валидации timezone update на API boundary.

Это не блокирует первый Today vertical slice и остаётся следующим отдельным contract slice.

## 10. Undo — gap, не реализовано

Сейчас обратим только task status `planned ↔ done`. Общего `PlanChange` и реального rollback нет. Mobile не должен показывать общий «Вернуть».

Минимальный будущий контракт:

```text
POST /api/v1/plan-changes/{change_id}/undo
```

Backend проверяет ownership, expiry, что change ещё не отменён, и актуальную plan version; затем применяет сохранённый inverse payload в транзакции и возвращает новый `DaySnapshot + PlanDiff`.

## 11. Voice readiness — gap, STT не реализовано

Будущий контракт:

```text
POST /api/v1/transcriptions
Content-Type: multipart/form-data
audio=<recording>

→ {transcript_id, text, language, duration_ms}
```

Полученный text передаётся в тот же capture pipeline с source `ios_voice_transcript`. Результат text и voice одинаков по бизнес-логике. Отдельный voice parser/scheduler запрещён.

## 12. Latency audit

Текущий synchronous flow:

1. bearer check и user lookup/create;
2. idempotency receipt lookup/reservation и commit;
3. один parser call;
4. mutation + planner + no-overlap check;
5. snapshot queries tasks/goals/routines/plan;
6. receipt completion commit;
7. response.

Фактические ограничения:

- mock parser обычно занимает миллисекунды;
- remote LLM ограничен `LLM_TIMEOUT_SECONDS`, сейчас 12 секунд;
- LLM budget дополнительно ограничен `MESSAGE_REQUEST_TIMEOUT_SECONDS - 2`, сейчас 13 секунд;
- provider retries равны `0`, повторного LLM call внутри submit нет;
- общий ASGI request timeout backend пока жёстко не прерывает DB/planner stage;
- message service логирует total/parser latency без secrets;
- `_snapshot_plan_placements()` читает все планы пользователя для diff и со временем может стать unbounded;
- service flow содержит несколько commit boundaries, поэтому receipt и mutation ещё не образуют одну идеальную транзакцию;
- atomic mobile response устраняет frontend waterfall после mutation.

P0 правила клиента:

- UI сразу показывает local pending state, но не придумывает результат;
- capture имеет client timeout;
- timeout превращается в retryable state;
- retry использует тот же `request_id`;
- полученный `DaySnapshot` атомарно заменяет cache.

P0 рассчитан на один локальный iOS client, который сериализует mutations. Task status строит snapshot под user/task row lock до commit. Общий capture pipeline пока содержит внутренние commit boundaries, поэтому строгая cross-request serializable consistency при двух разных одновременных mutations не гарантируется; это обязательный refactor до TestFlight multi-user.

Следующие backend latency fixes:

1. измерить p50/p95 отдельно для auth, parser, planner, snapshot и commit;
2. ограничить placement diff затронутыми датами;
3. объединить mutation, interaction и receipt completion в явную transaction boundary;
4. определить server/proxy request deadline и controlled timeout response;
5. не добавлять LLM retries до появления измеримых transient failures.

## 13. Реально необходимые migrations

Для реализованного P0 migrations не нужны.

Позже:

- TestFlight auth: `auth_identities(user_id, provider, subject, created_at)` с unique `(provider, subject)`;
- Undo: `plan_changes(user_id, plan_date, base_version, result_version, forward_payload, inverse_payload, status, expires_at)`;
- Profile preferences: отдельная typed table или явно версионированные columns после определения настроек;
- Goal progress: goal milestones/progress events только после определения достоверной метрики.

## 14. Что не надо менять сейчас

- не переписывать parser или deterministic scheduler;
- не создавать отдельную iOS planning logic;
- не удалять Web/Telegram, но не развивать их;
- не создавать Android до проверки iOS;
- не внедрять большой auth framework для local dogfooding;
- не реализовывать STT без выбранного provider и privacy policy;
- не строить calendar management API;
- не показывать fake goal percentages;
- не создавать general Undo UI до backend rollback;
- не добавлять dependencies без отдельной необходимости.

## Связанные материалы

- [[01 Продукт/Видение продукта]]
- [[01 Продукт/Принципы продукта]]
- [[02 Дорожная карта/Сейчас — далее — позже]]
- [[03 Решения/Журнал решений]]
- [[07 Техническая документация/Базовая безопасность]]
