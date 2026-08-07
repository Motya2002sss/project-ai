---
aliases:
  - Today Design Handoff
type: design-handoff
status: proposed
area: design
updated: 2026-08-02
---

# Handoff Today для разработки

## Статус пакета

Это дизайн-handoff, а не разрешение на реализацию. Код и API на этапе подготовки концепции не меняются. Перед началом разработки владелец продукта подтверждает P0 scope и порядок итераций.

Источники правды:

1. [[Концепция Today Experience]] — продуктовая логика и границы.
2. [[Экраны и состояния Today]] — сценарии, порядок блоков и microcopy.
3. [[Дизайн-система Today]] — токены, размеры и component states.
4. Этот документ — mapping данных, sequencing и acceptance criteria.

При конфликте точная безопасность и backend validation имеют приоритет над визуальным макетом. Концепт-борд задаёт направление, но не заменяет спецификацию.

## Рекомендуемый scope первой UI-итерации

### P0.1 — семантика плана

- сохранить текущую Today-first структуру;
- разделить `planned` и `not_scheduled` визуально и текстом;
- заменить неоднозначное «Позже / без времени» для элементов перегрузки на «Не помещается сегодня»;
- сохранить обратимый checkbox и честный progress;
- не добавлять новых API и controls.

### P0.2 — адаптивный composer

- expanded variant в empty state;
- compact variant при активном плане;
- сохранить draft при error;
- показать processing без очистки поля до успешного ответа;
- коротко объяснять результат после ответа.

### P0.3 — устойчивость состояний

- skeleton без layout shift;
- inline error для checkbox и composer;
- all-done completion panel;
- reduced motion и keyboard focus;
- dev-only настройки визуально отделены и не входят в production layout.

### P1 после dogfooding

- day switch «Сегодня / Завтра»;
- отдельный evening-summary entry point;
- быстрый перенос и редактирование только после API/product решения;
- goal context только при подтверждённой пользе.

## Mapping backend → UI

### Plan

| Backend field | UI | Правило |
|---|---|---|
| `plan.date` | Дата дня | Для P0 Today; не вычислять смысл только из системной даты после ответа |
| `plan.energy_level` | Tempo label | `low → Бережный темп`, `medium → Обычный темп`, `high → Много энергии` |
| `plan.status` | Overload context | `overloaded` может поддержать explanation, но список определяется item statuses |
| `plan.items[].status=planned` | Основной план | Сортировать по `start_time`, сохраняя стабильный backend order при null |
| `plan.items[].status=not_scheduled` | «Не помещается сегодня» | Никогда не присваивать выдуманное время |
| `plan.items[].start_time` | Время старта | Формат `HH:MM`; null не рендерится |
| `plan.items[].end_time` | Необязательный time range | В task row P0 достаточно start time; range можно использовать в accessible detail |
| `plan.items[].task_id` | Связь с task | Item без task не рендерится как интерактивный checkbox без отдельного контракта |
| `plan.summary` | Не выводить напрямую | Сейчас может содержать raw input или служебный default; использовать только после отдельного content contract |

### Task

| Backend field | UI | Правило |
|---|---|---|
| `task.id` | Mutation key | PATCH всегда с user context |
| `task.title` | Task title | Не обрезать смысл; перенос до 3 строк |
| `task.status` | Checkbox | Только `planned` и `done` |
| `task.estimated_minutes` | Duration | `null → не показывать`; формат 20 мин / 1 ч / 1 ч 20 мин |
| `task.target_date` | Day grouping | Today, tomorrow, другая дата; не смешивать с plan дня |
| `task.priority` | Порядок backend | Не показывать priority chip в основном Today UI |

### Message response

| Backend field | UI | Правило |
|---|---|---|
| `reply_text` | Fallback explanation | Удалять технические повторы плана на presentation layer нельзя вслепую; предпочтительнее компактный локальный formatter |
| `summary` | Candidate result body | Пока дублирует `reply_text`; не считать готовым коротким summary без контракта |
| `intent` | Внутренняя логика | Не показывать пользователю; допустимо только в dev details |
| `affected_tasks` | «Обновлено: …» | Не более 2–3 названий, затем «и ещё N» |
| `affected_goals` | Goal result | Тот же лимит и нейтральная формулировка |
| `profile` | Context update result | Показать только человекопонятные изменённые настройки |
| `plan_summary` | Immediate result | После сообщения всё равно выполнить согласованную refresh strategy |

### Goals

| Backend field | UI | Правило |
|---|---|---|
| `goal.title` | Secondary context | Read-only; не конкурирует с Today tasks |
| `goal.priority` | Не показывать по умолчанию | Технические `high/medium/low` не нужны в главном UI |
| `goal.category` | Future grouping | Не вводить category chips без пользовательской пользы |
| `goal.status` | Filter | Today показывает только активные данные, полученные от API |

## UI model

Presentation layer должна собирать явную модель, не размазывать условия по JSX:

```text
TodayViewModel
  dateLabel
  dayTitle
  tempoLabel?
  progress { done, total, percent, allDone }
  scheduledTasks[]
  completedTasks[]
  unscheduledTasks[]
  futureTasks[]
  composerVariant: expanded | compact
  resultMessage?
  globalError?
```

Это рекомендация для handoff, а не требование менять архитектуру до подтверждения реализации. Источником правды остаются backend entities; view model не хранит отдельное пользовательское состояние.

## Interaction contracts

### Checkbox

1. Пользователь меняет status одной задачи.
2. Только её checkbox получает pending и disabled.
3. Выполняется `PATCH /api/tasks/{task_id}/status` с `user_external_id` и target status.
4. После успеха обновляются tasks, plan и progress.
5. После ошибки визуальный status остаётся прежним; появляется inline message.
6. Повторный tap во время pending игнорируется.

Done task всегда можно вернуть в `planned`.

### Composer

1. Пустой или whitespace-only draft не отправляется.
2. При submit draft остаётся видимым до успешного response.
3. Один submit создаёт один request.
4. При success draft очищается, показывается result, обновляются plan/tasks/goals.
5. При failure draft сохраняется целиком.
6. Поле принимает до текущего backend limit 4000 символов; UI не вводит меньший скрытый limit.

### Refresh

- initial loading допускает skeleton;
- background refresh не очищает валидные данные;
- при partial failure UI различает «операция не сохранена» и «операция сохранена, refresh не удался»;
- изменение user ID относится только к local MVP и сбрасывает last-response context;
- UI не использует local optimistic state как источник правды после server response.

## Responsive redlines

| Параметр | Mobile | Wide viewport |
|---|---:|---:|
| Viewport reference | 390×844 | 1280×800 |
| Content width | `100% - 32px` | 500–520 px |
| Horizontal gutter | 16 px | auto centered |
| Top padding | 28–32 px | 48–56 px |
| Section gap | 32 px | 36–40 px |
| Task min-height | 72–80 px | 72–80 px |
| Control target | ≥44 px | ≥44 px |
| Composer textarea | min 96 px expanded | min 96 px expanded |

Проверить дополнительно 320 px, 375 px, 768 px и 1440 px. На широких экранах не создавать второй столбец только ради свободного пространства.

## Component acceptance criteria

### Day header

- дата локализована на русском и не содержит года для Today;
- heading остаётся единственным `h1`;
- focus line не дублирует system status;
- layout выдерживает 200% text zoom.

### Task row

- title не перекрывает checkbox и metadata;
- status можно изменить мышью, клавиатурой и touch;
- accessible name содержит название задачи и действие;
- pending заметен текстом, а не только disabled opacity;
- done task читаема и доступна для undo;
- длинное название не создаёт horizontal scroll.

### Progress

- `done = 0`, mixed и all-done отображаются корректно;
- `total = 0` не показывает бессмысленный 0%;
- текст совпадает с фактическим количеством задач выбранного дня;
- progress fill ограничен диапазоном 0–100%.

### Unscheduled

- секция появляется только при наличии элементов;
- каждый item показывается один раз и не дублируется в scheduled/future;
- отсутствующее время не заменяется «00:00»;
- текст не обвиняет пользователя;
- нет неработающих кнопок переноса.

### Composer

- label остаётся видимым при заполненном поле;
- submit disabled для пустого draft и во время отправки;
- draft сохраняется при network/API error;
- success очищает draft только после подтверждения;
- loading copy не меняет ширину CTA так, чтобы ломать layout.

### Result и errors

- result не выводит intent, raw parsed JSON или status code;
- affected entities сокращаются после трёх items;
- error имеет recovery action или понятную следующую инструкцию;
- global и inline errors не дублируют друг друга;
- screen reader получает одно краткое объявление.

## Acceptance scenarios

### A. Пустой день → первый план

1. Открыть пользователя без задач.
2. Убедиться, что empty state спокойный, composer prominent.
3. Ввести: «Сегодня мало сил, надо оплатить счета и 40 минут поделать проект».
4. Во время отправки draft остаётся видимым.
5. После успеха появляются tempo, план, progress и краткий result.
6. Ни intent, ни raw parser data не видны.

### B. Mixed progress

1. Открыть день с четырьмя задачами, две `done`.
2. Увидеть «Сделано 2 из 4».
3. Вернуть одну done-задачу в planned.
4. Увидеть «Сделано 1 из 4» после server refresh.
5. Ошибка mutation не должна визуально менять status.

### C. Перегрузка

1. Построить план, где часть items имеет `not_scheduled`.
2. Scheduled rows остаются в основном плане.
3. Непоместившиеся появляются в отдельной секции.
4. Они не получают времени и не дублируются в «Позже».
5. UI не предлагает unsupported перенос.

### D. All done

1. Закрыть последнюю planned task.
2. Увидеть «Все задачи закрыты» и спокойный completion state.
3. Не увидеть CTA добавления новых задач как главный action.
4. Сохранить возможность вернуть любую задачу в planned.

### E. Composer error

1. Ввести многострочный draft.
2. Смоделировать network error.
3. Полный draft остаётся в поле.
4. Error сообщает, что текст сохранён.
5. Повторная отправка не создаёт визуальных дублей.

### F. Partial refresh error

1. Успешно изменить checkbox.
2. Смоделировать ошибку последующего refresh.
3. Сообщение явно говорит, что status сохранён, но весь день не обновился.
4. Доступно действие «Обновить день».

## API и продуктовые пробелы

Эти пробелы нельзя маскировать декоративными controls:

- Web использует временный `user_external_id`, а не production auth;
- нет отдельного endpoint быстрого переноса задачи;
- нет edit/delete task contract для Web;
- current Web data loader запрашивает только Today;
- `MessageResponse.summary` пока не является отдельным коротким UI-summary;
- `plan.summary` не является безопасным готовым текстом для hero;
- нет отдельной сущности истории дневных итогов для Web presentation;
- нет события/контракта для автоматического определения «вечера»;
- voice UI не должен появляться до STT.

## Решения, которые должен подтвердить dogfooding

1. После появления плана достаточно ли compact composer, или пользователю нужен expanded ввод весь день?
2. Нужен ли result card постоянно, либо достаточно временной подсветки изменений?
3. Помогает ли видимый список целей на Today или создаёт давление?
4. Понимает ли пользователь разницу между «Не помещается сегодня» и будущими задачами?
5. Нужна ли отдельная кнопка вечернего итога, если тот же intent хорошо работает через свободный текст?

Эти вопросы не блокируют P0. Они определяют, какие P1 controls заслуживают реализации.

## Design QA checklist

### Визуально

- проверены empty, loading, mixed, overload, all-done и error;
- нет layout shift между loading и ready;
- один главный action в каждом состоянии;
- secondary sections не конкурируют с планом;
- радиус основных surfaces не превышает 8 px;
- цвета соответствуют токенам;
- generated concept board не используется как pixel-perfect source.

### Поведение

- checkbox reversible;
- draft сохраняется при error;
- `not_scheduled` отделён от scheduled;
- данные пользователя не смешиваются при смене local user ID;
- UI не показывает неподдерживаемые actions;
- Telegram и Web semantics не расходятся без продуктового решения.

### Доступность

- keyboard-only проход завершён;
- focus видим;
- contrast соответствует baseline;
- 200% zoom и 320 px не ломают layout;
- reduced motion учтён;
- screen reader announcements краткие и недублирующиеся.

### Проверки проекта перед будущим merge

Если реализация будет подтверждена, применяются существующие требования проекта: Alembic до head, `scripts/check_mvp.py`, import check, `pytest`, frontend production build, проверка diff и отсутствие секретов. Дизайн-пакет сам по себе не требует миграций и не авторизует commit или push.

## Definition of Ready для разработки

Разработка может начинаться, когда:

- подтверждён P0 scope;
- согласованы microcopy и названия секций;
- решено, показывать ли goals в P0;
- принят способ компактного result summary без раскрытия технических данных;
- известны тестовые fixtures для mixed, overload и partial error;
- назначен короткий dogfooding checkpoint после первой итерации.

## Связанные материалы

- [[Концепция Today Experience]]
- [[Экраны и состояния Today]]
- [[Дизайн-система Today]]
- [[05 Тестирование продукта/Сценарии приёмочного тестирования]]
- [[07 Техническая документация/Базовая безопасность]]
