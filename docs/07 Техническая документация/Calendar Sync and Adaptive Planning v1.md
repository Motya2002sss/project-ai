---
aliases:
  - Calendar Sync and Adaptive Planning v1
type: technical-contract
status: implemented-locally
---

# Calendar Sync and Adaptive Planning v1

## Статус

Локально реализованы и покрыты тестами:

- user-scoped импорт занятых интервалов Apple Calendar;
- Day, Week и Month read models в `/api/v2/calendar`;
- адаптивное перепланирование будущих flexible placements;
- атомарный `PlanChange` и ограниченный по времени Undo;
- mobile-экран Calendar и offline cache, привязанный к public user ID.

Реальный EventKit flow на iPhone ещё должен быть проверен в iOS development build или TestFlight. Запись событий в Apple Calendar не реализована и не включена.

## Граница приватности

Разрешение запрашивается только после явного нажатия «Учесть Apple Calendar». Отказ не вызывает sync и не показывает ложный успех.

Mobile отправляет только технические busy-интервалы:

- device, provider и calendar external IDs;
- event и occurrence external IDs;
- начало, конец и source revision;
- покрытый диапазон и timezone устройства.

Названия, заметки, location, attendees, capture text, задачи и содержание календарных событий не входят в transport DTO. На экране внешние события называются только «Занято».

Текущий Expo/EventKit API может выдавать системное разрешение уровня полного доступа к календарям, но приложение использует его только для чтения busy-интервалов и не вызывает write API.

## Sync, dedupe и удаление

```text
tap → OS permission → GET sync-state → read busy intervals
    → PUT /api/v2/calendar/busy-blocks → refresh Calendar reads
```

Sync изолирован по `user + device + provider`. Стабильная occurrence identity строится из EventKit event ID и конкретного start time. Повтор с тем же `request_id` повторяет тот же payload; version и client revision защищают от stale write.

Удалённые события превращаются в tombstones внутри явно покрытого диапазона. Исчезнувший календарь передаётся через `removed_calendar_external_ids`; календарь другого provider или устройства не затрагивается. Backend возвращает `affected_dates` и `replan_required`, но sync сам не применяет перепланирование.

## Read models

- `GET /api/v2/calendar/day?date=YYYY-MM-DD` — единая временная линия fixed, flexible, busy, free и recovery внутри planning horizon `06:00 → sleep_time`, либо `23:00` без sleep time.
- `GET /api/v2/calendar/week?start=YYYY-MM-DD` — ровно семь дней с Monday start, нагрузка commitments и дневные summary.
- `GET /api/v2/calendar/month?month=YYYY-MM-01` — только high-level milestones, deadlines, life modes, measurements и tension markers.

Ответы имеют стабильный opaque cursor/ETag. GET использует read-only auth path и не обновляет session telemetry.

## Адаптивное перепланирование и rollback

`POST /api/v2/planning/replan` требует `request_id`, точные `base_versions`, affected dates и причину. Мутация:

- не меняет прошлые дни, completed facts, fixed и locked placements;
- перестраивает только затронутые будущие flexible placements;
- учитывает persisted calendar busy blocks и временные ограничения;
- применяет все дни атомарно;
- сохраняет factual diff, snapshots и inverse state в `PlanChange`.

`POST /api/v2/planning/plan-changes/{change_id}/undo` проверяет owner, expiry, latest-change rule и ожидаемые версии. Повтор request идемпотентен; stale или конфликтующий запрос получает typed `409`, а не частичный результат.

## Mobile и offline

Calendar открывается из Today, а не является новым root tab. Day/Week/Month используют спокойную timeline без drag-and-drop. Capture остаётся единственной точкой пользовательской мутации.

Последний authoritative read кэшируется в namespace текущего public user ID. Без подтверждённой identity production cache не читается и не записывается. При недоступном backend показывается маркированный cached state; импорт не сообщает об успехе до server response.

## Запись в Apple Calendar и kill switch

Write sync намеренно отсутствует в v1. До его включения обязательны одновременно:

1. отдельное явное согласие пользователя;
2. server-side feature flag/kill switch, выключенный по умолчанию;
3. стабильная device-scoped write identity и dedupe;
4. проверка create/update/delete и revocation на release build.

Без этих условий backend и mobile не должны создавать или изменять события. Это release gate, а не локально реализованная возможность.

## Проверка

```bash
cd /Users/motya/Documents/work/project-ai
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python scripts/check_mvp.py
.venv/bin/pytest -q

cd mobile
npm test
npm run typecheck
npm run lint
npx expo-doctor
```

Текущий миграционный head: `a7f6e5d4c833`.
