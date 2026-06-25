# AI Life Planner UAT Scenarios

Use these scenarios for manual Telegram MVP checks after running migrations.

## 1. Profile Setup

Message:

```text
Мой график с 10 до 19, хочу спать в 00:30
```

Expected:

- Bot saves work start, work end, and sleep time.
- Bot shows the stored profile.
- Later plans start after work plus the configured buffer.

## 2. Goals

Message:

```text
Моя цель: накопить 500000 рублей, научиться рисовать, сделать мобильное приложение
```

Expected:

- Bot stores all goals.
- Money amount is treated as part of the goal, not as a daily budget.
- `Покажи цели` lists active goals in readable form.

## 3. Goal-Driven Tasks

Message:

```text
Что сделать для целей?
```

Expected:

- If goals exist, bot creates small tasks connected to the active goals.
- If no goals exist, bot asks the user to add goals first.
- The plan is rebuilt for the selected date.

## 4. Tasks Today

Message:

```text
Сегодня хочу разобрать документы
```

Expected:

- Bot creates a task for today.
- Bot rebuilds today's plan.
- The task appears only in today's plan.

## 5. Tasks Tomorrow

Message:

```text
Завтра хочу позаниматься математикой
```

Expected:

- Bot creates a task with tomorrow as `target_date`.
- `Покажи план завтра` includes the task.
- Today's plan does not include the tomorrow task.

## 6. Day Plan

Message:

```text
Покажи план
```

Expected:

- Bot shows the plan for today.
- Plan uses profile work end and sleep time when available.
- If profile is incomplete, bot explains that defaults were used.
- If too many tasks do not fit before sleep, overflow tasks are shown as better to move.

## 7. Mark Done

Message:

```text
Документы сделал
```

Expected:

- Bot finds an active task for the selected date.
- Bot marks it done.
- Bot rebuilds the plan without the completed task.

## 8. Daily Summary

Message:

```text
Итог дня: документы сделал, математику не сделал
```

Expected:

- Completed tasks are marked done.
- Not-done tasks remain active.
- Bot shows what was updated and rebuilds the plan.

## 9. Reschedule

Message:

```text
Я задержался до 20
```

Expected:

- Bot treats this as a reschedule signal.
- Plan starts from the new available time plus buffer.
- Tasks that no longer fit before sleep are marked as not scheduled.

## 10. Universal Goal Examples

Try goals across domains:

```text
Моя цель: улучшить здоровье, чаще видеться с семьей, написать рассказ, закрыть долг
```

Expected:

- Bot stores all goals.
- Goal-task suggestions remain useful and do not assume a single user's gym, English, or AI project context.

## 11. Today Web UI

Setup:

```bash
uvicorn app.main:app --reload
cd web
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Input:

```text
Сегодня мало сил, надо оплатить счета и 40 минут поделать проект
```

Expected:

- The Web UI sends the text to `POST /api/message` with `source=web_text`.
- The AI response block shows the backend `reply_text` and intent.
- Today plan refreshes from `GET /api/plan/{user_external_id}?date=today`.
- Tasks refresh from `GET /api/tasks/{user_external_id}`.
- Goals refresh from `GET /api/goals/{user_external_id}`.
- Checking a Today task calls `POST /api/tasks/{task_id}/done`.
- The completed task becomes muted/struck through, progress changes to `Сделано X из Y`, and the remaining plan is rebuilt.
- Changing `User ID` switches the temporary local MVP identity stored in `localStorage`.
