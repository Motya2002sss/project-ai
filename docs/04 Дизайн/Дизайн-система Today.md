---
aliases:
  - Today Design System
type: design-system
status: proposed
area: design
updated: 2026-08-02
---

# Дизайн-система Today

## Назначение

Soft Light Daily Planner v0.1 — компактная дизайн-система для Today-first MVP. Она должна обеспечивать спокойную иерархию, честные состояния плана, touch-friendly interaction и достаточную доступность без преждевременного создания универсальной библиотеки компонентов.

Существующие визуальные решения сохраняются там, где они соответствуют этим правилам. Токены ниже — целевой источник правды для следующей итерации UI, а не команда немедленно переписать текущие стили.

## Основные принципы

1. **Тёплый свет, не стерильный белый.** Canvas смягчает ощущение контроля.
2. **Контраст через иерархию, не через яркость.** Основной текст графитовый, accent используется дозированно.
3. **Плотность по состоянию.** Пустой день воздушнее, активный план компактнее.
4. **Функция раньше украшения.** Иллюстрация не заменяет сообщение и action.
5. **Человекопонятные состояния.** Цвет всегда поддерживает текст, а не кодирует смысл один.
6. **Один радиус.** Основные контейнеры и controls используют максимум 8 px.

## Цветовые токены

### Нейтральные

| Token | Значение | Применение |
|---|---|---|
| `color.canvas` | `#F7F3EC` | Фон приложения |
| `color.surface` | `#FFFDF9` | Карточки и поля |
| `color.surfaceMuted` | `#FBF8F2` | Composer, спокойные secondary surfaces |
| `color.textPrimary` | `#2F2A25` | Заголовки и основной текст |
| `color.textSecondary` | `#6E655C` | Описания и metadata; контраст 5.16:1 на canvas |
| `color.textTertiary` | `#81786E` | Только крупный или некритичный текст; не использовать ниже 16 px как единственный label |
| `color.border` | `#DED5CA` | Контуры surfaces и разделители |
| `color.borderSubtle` | `#EAE2D8` | Внутренние тихие разделители |

### Sage accent

| Token | Значение | Применение |
|---|---|---|
| `color.accentStrong` | `#536D52` | Primary button; белый текст имеет контраст 5.71:1 |
| `color.accent` | `#627C61` | Accent-текст на светлой поверхности, focus и иконки |
| `color.accentSoft` | `#EAF1E7` | Completion и assistant result background |
| `color.accentLine` | `#8FAE8B` | Progress fill и декоративные линии, не мелкий текст |

### Системные

| Token | Значение | Применение |
|---|---|---|
| `color.dangerText` | `#98533F` | Error text; контраст 5.21:1 на canvas |
| `color.dangerSurface` | `#F8E9E4` | Error banner background |
| `color.warningText` | `#7B5E38` | Overload explanation, если нужен warning tone |
| `color.warningSurface` | `#F4ECDC` | Необязательный warning surface |
| `color.disabledSurface` | `#E6DED4` | Disabled controls |
| `color.disabledText` | `#746C63` | Disabled label при сохранении читаемости |

### Правила цвета

- `color.accentStrong` используется только для главного action и выбранного состояния.
- `color.accentLine` не используется для текста меньше 18 px.
- Done-state не полагается на opacity ниже 0.7 для целой строки; текст должен оставаться читаемым.
- Ошибки не кодируются только терракотовым цветом: всегда есть явный текст и действие.
- В продукте нет corporate blue, neon accents, AI-gradients и многоцветных priority chips.

## Типографика

### Семейство

Основной стек: `Inter`, затем системный `ui-sans-serif`. Если Inter не загружается локально без нового dependency или внешнего запроса, системный стек остаётся допустимым. Данные и время используют то же семейство; моноширинный шрифт не нужен.

### Шкала

| Style | Mobile | Desktop | Line-height | Weight | Применение |
|---|---:|---:|---:|---:|---|
| `display` | 42 px | 48 px | 0.98–1.02 | 700 | «Сегодня» |
| `title1` | 24 px | 24 px | 1.20 | 700 | Главный блок |
| `title2` | 20 px | 21 px | 1.25 | 680 | Composer и completion |
| `title3` | 17 px | 18 px | 1.30 | 650 | Secondary section |
| `body` | 16 px | 16 px | 1.50 | 450 | Основной текст и task title |
| `bodySmall` | 14 px | 14 px | 1.45 | 450 | Supporting copy |
| `meta` | 13 px | 13 px | 1.40 | 500 | Время, duration, status |
| `label` | 12 px | 12 px | 1.30 | 700 | Kicker, compact labels |

### Правила типографики

- Task title начинается со строчной буквы только если это результат свободного ввода; система не исправляет регистр ради визуальной симметрии.
- Kicker может использовать uppercase, но не содержит длинных фраз.
- Не использовать all caps для ошибок, перегрузки или CTA.
- Числа progress и время должны иметь tabular numerals, если шрифт их поддерживает.
- Максимальная комфортная длина body copy — около 60 символов в строке.

## Размеры и spacing

Базовый шаг — 4 px.

| Token | Значение | Типичное применение |
|---|---:|---|
| `space.1` | 4 px | Внутренние микрозазоры |
| `space.2` | 8 px | Icon gap, goal chips |
| `space.3` | 12 px | Metadata groups |
| `space.4` | 16 px | Mobile gutter, task padding |
| `space.5` | 20 px | Section internal gap |
| `space.6` | 24 px | Card padding |
| `space.8` | 32 px | Между крупными блоками |
| `space.10` | 40 px | Header/section rhythm |
| `space.12` | 48 px | Desktop top spacing |
| `space.16` | 64 px | Нижний safe breathing space |

Не вводить промежуточные значения без явной причины. Оптическая коррекция 1–2 px допустима для icons и stroke, но не превращается в новый token.

## Геометрия

| Token | Значение | Применение |
|---|---:|---|
| `radius.control` | 8 px | Button, input, checkbox |
| `radius.card` | 8 px | Task, composer, result, empty |
| `radius.progress` | 999 px | Только тонкая progress track |
| `border.default` | 1 px | Surface separation |
| `border.focus` | 3 px | Внешний focus ring |

Основные карточки не используют 16–24 px «mobile banking» radius. Это сохраняет более собранный и взрослый характер продукта.

## Elevation

| Level | Значение | Применение |
|---|---|---|
| `shadow.none` | none | Done rows, inline secondary lists |
| `shadow.low` | `0 8px 24px rgba(62,45,27,.04)` | Goal chips, тихие карточки |
| `shadow.card` | `0 14px 34px rgba(62,45,27,.055)` | Task row |
| `shadow.focused` | `0 18px 40px rgba(62,45,27,.075)` | Hover на pointer devices |

Тень не используется как единственная граница. На mobile hover elevation отсутствует.

## Layout

### Mobile-first

- минимальная ширина: 320 px;
- основной gutter: 16 px, на очень узких экранах не меньше 12 px;
- max content width: 500–520 px;
- один столбец;
- верхний отступ: 28–32 px;
- нижний safe area: `max(32px, env(safe-area-inset-bottom))`;
- основной button на узком экране занимает доступную ширину composer.

### Wide viewport

- контент остаётся центрированным одним столбцом;
- ширина не растягивается ради заполнения экрана;
- secondary details не выносятся в постоянную боковую панель;
- desktop grid допускается только в будущих detail screens, не на Today.

## Компоненты

### Day header

- `date / display title / focus line`;
- дата — secondary, title — dominant;
- header не содержит avatar, streak, notification center и глобальный search в MVP.

### Progress

- текст `Сделано X из Y` всегда видим;
- track высотой 4 px;
- fill анимируется до 220 ms;
- all-done меняет текст на «Все задачи закрыты», но сохраняет числовой accessible label;
- progress не сравнивает пользователя с предыдущими днями.

### Task row

- min height 72–80 px для основного плана;
- checkbox visual 24–26 px, интерактивная зона минимум 44 px;
- title переносится до трёх строк без обрезки важного смысла;
- metadata переносится независимо;
- `pending` блокирует только конкретный checkbox;
- `done` использует checked state, спокойный текст и strike-through;
- row не имеет скрытых swipe actions в Web MVP.

### Composer

Два варианта одного компонента:

| Variant | Когда | Поле | CTA |
|---|---|---|---|
| `expanded` | Empty/morning | 3–6 строк, resize до разумного max | «Собрать день» |
| `compact` | Active/all-done | 1–3 строки с раскрытием по focus | «Обновить день» |

Общее:

- видимый label, placeholder не заменяет label;
- draft сохраняется при ошибке;
- disabled state не должен выглядеть как отсутствующий control;
- helper text: «Без формата и правильных слов»;
- voice icon не показывается до появления работающего STT.

### Assistant result

- soft sage surface или левая accent-line;
- label: «План обновлён»;
- body: одно объяснение результата;
- optional affected-items line;
- нет аватара, speech bubble и длинной chat history;
- автоматически сворачивается визуально после следующего значимого действия, но не исчезает до прочтения.

### Overload section

- располагается сразу после scheduled plan;
- может использовать border-top вместо card stack;
- explanation — neutral, не alarm;
- количество видно в header;
- никаких red badges.

### Completion panel

- accent soft background;
- icon check в круге допускается как функциональный символ;
- headline + одна поддерживающая строка;
- optional summary metrics только если они уже достоверны;
- no confetti, trophies, streaks или сравнения.

### Error banner

- danger surface + danger text + action;
- inline для локальной операции, global только для общей загрузки;
- не меняет высоту соседних критичных controls во время pending;
- не раскрывает HTTP status или backend details.

### Skeleton

- повторяет размеры title, progress и 2–3 task rows;
- слабая opacity-анимация до 1.2 s;
- при reduced motion — статичный;
- skeleton не показывается поверх уже валидных данных при background refresh.

## Иконография

- стиль: простой outline, stroke 1.5–2 px;
- базовые размеры: 16, 20, 24 px;
- обязательные иконки P0: check и error/retry при необходимости;
- иконка никогда не заменяет label у primary action;
- не вводить отдельный «AI sparkle» symbol;
- не добавлять icon library только ради 2–3 символов без инженерного основания.

## Motion

| Interaction | Duration | Easing |
|---|---:|---|
| Hover/focus color | 150 ms | ease-out |
| Checkbox feedback | 150 ms | ease-out |
| Progress fill | 220 ms | ease-out |
| Result highlight | 180–220 ms | ease-out |
| Section expand | 200 ms | ease-out |

Анимация поддерживает причинно-следственную связь, но не задерживает действие. При `prefers-reduced-motion: reduce` transitions отключаются или становятся почти мгновенными.

## Content design

### Голос

- спокойный;
- конкретный;
- взрослый;
- без морализаторства;
- без обещаний, которых система не может гарантировать.

### Использовать

- «План на сегодня пока пуст»;
- «Не помещается сегодня»;
- «Текст сохранён — попробуй ещё раз»;
- «День закрыт мягко. Можно выдохнуть»;
- «Что изменилось?».

### Не использовать

- «Вы провалили 2 задачи»;
- «Просрочено» для задач, которые не поместились;
- «AI анализирует ваш intent»;
- «Будь продуктивнее»;
- «Добавьте ещё задачи» после all-done;
- emoji как обязательный carrier статуса.

## Accessibility baseline

- WCAG AA для основного текста и controls;
- текст до 18 px — contrast минимум 4.5:1;
- крупный текст и non-text controls — минимум 3:1;
- focus ring заметен на canvas и surface;
- target минимум 44×44 px;
- масштабирование текста до 200% не скрывает action;
- landscape mobile не создаёт горизонтальный scroll;
- status передаётся текстом и семантикой, а не только цветом;
- screen reader получает краткое обновление, а не повтор всей страницы;
- все действия доступны клавиатурой.

## Контроль целостности

Новый component или token добавляется только если:

1. он поддерживает подтверждённый пользовательский сценарий;
2. существующий primitive не решает задачу без потери смысла;
3. определены default, loading, disabled, error и accessibility states;
4. он не создаёт параллельный паттерн для той же функции.

## Связанные материалы

- [[Направление дизайна]]
- [[Концепция Today Experience]]
- [[Экраны и состояния Today]]
- [[Handoff Today для разработки]]
