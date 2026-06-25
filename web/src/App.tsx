import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from "react";

type MessageSource = "web_text";

type Task = {
  id: number;
  title: string;
  priority: string;
  estimated_minutes: number | null;
  target_date: string;
  status: string;
};

type Goal = {
  id: number;
  title: string;
  category: string;
  priority: string;
  status: string;
};

type PlanItem = {
  id: number;
  task_id: number | null;
  title: string;
  item_type: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
};

type Plan = {
  id: number;
  date: string;
  summary: string | null;
  energy_level: string | null;
  budget_limit: number | null;
  status: string;
  items: PlanItem[];
};

type MessageResponse = {
  user_external_id: string;
  source: MessageSource;
  intent: string;
  parsed: Record<string, unknown>;
  reply_text: string;
  summary: string | null;
  affected_tasks: Task[];
  affected_goals: Goal[];
  plan_summary: Plan | null;
};

type LoadState = "idle" | "loading" | "ready" | "error";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const USER_ID_STORAGE_KEY = "ai-life-planner-user-id";

function localDateValue(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function formatToday(): string {
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long"
  }).format(new Date());
}

function formatTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null;
}

function formatTaskDate(value: string): string {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (value === localDateValue()) {
    return "Сегодня";
  }

  const tomorrowValue = [
    tomorrow.getFullYear(),
    String(tomorrow.getMonth() + 1).padStart(2, "0"),
    String(tomorrow.getDate()).padStart(2, "0")
  ].join("-");

  if (value === tomorrowValue) {
    return "Завтра";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short"
  }).format(new Date(`${value}T00:00:00`));
}

function formatDuration(minutes: number | null): string | null {
  if (!minutes) {
    return null;
  }

  if (minutes < 60) {
    return `${minutes} мин`;
  }

  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} ч`;
  }

  return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

function priorityLabel(priority: string): string {
  const labels: Record<string, string> = {
    high: "важная",
    medium: "обычная",
    low: "низкий приоритет"
  };

  return labels[priority] || priority;
}

function responseSummary(replyText: string): string {
  return replyText.split("\n\nПлан дня:")[0].trim();
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    throw new Error(`Сервис ответил с ошибкой ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export default function App() {
  const initialUserId = localStorage.getItem(USER_ID_STORAGE_KEY) || "web-demo-user";
  const [userId, setUserId] = useState(initialUserId);
  const [userIdDraft, setUserIdDraft] = useState(initialUserId);
  const [draft, setDraft] = useState("");
  const [backendStatus, setBackendStatus] = useState<LoadState>("idle");
  const [dataStatus, setDataStatus] = useState<LoadState>("idle");
  const [submitStatus, setSubmitStatus] = useState<LoadState>("idle");
  const [completingTaskIds, setCompletingTaskIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [lastResponse, setLastResponse] = useState<MessageResponse | null>(null);

  const todayText = useMemo(() => formatToday(), []);
  const todayValue = useMemo(() => localDateValue(), []);
  const todayTasks = useMemo(
    () => tasks.filter((task) => task.target_date === todayValue),
    [tasks, todayValue]
  );
  const doneToday = todayTasks.filter((task) => task.status === "done");
  const activeToday = todayTasks.filter((task) => task.status !== "done");
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const scheduledItems = (plan?.items || []).filter((item) => item.status === "planned");
  const scheduledTaskIds = new Set(
    scheduledItems.flatMap((item) => (item.task_id === null ? [] : [item.task_id]))
  );
  const laterTasks = tasks.filter(
    (task) =>
      task.status !== "done" &&
      (task.target_date !== todayValue || !scheduledTaskIds.has(task.id))
  );
  const progressPercent = todayTasks.length
    ? Math.round((doneToday.length / todayTasks.length) * 100)
    : 0;

  async function refreshData(nextUserId = userId) {
    setDataStatus("loading");
    setError(null);

    try {
      const [planData, taskData, goalData] = await Promise.all([
        requestJson<Plan>(`/api/plan/${encodeURIComponent(nextUserId)}?date=today`),
        requestJson<Task[]>(`/api/tasks/${encodeURIComponent(nextUserId)}`),
        requestJson<Goal[]>(`/api/goals/${encodeURIComponent(nextUserId)}`)
      ]);

      setPlan(planData);
      setTasks(taskData);
      setGoals(goalData);
      setDataStatus("ready");
    } catch (refreshError) {
      setDataStatus("error");
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось загрузить день");
    }
  }

  useEffect(() => {
    async function checkBackend() {
      setBackendStatus("loading");

      try {
        await requestJson<{ status: string }>("/health");
        setBackendStatus("ready");
      } catch {
        setBackendStatus("error");
      }
    }

    checkBackend();
  }, []);

  useEffect(() => {
    localStorage.setItem(USER_ID_STORAGE_KEY, userId);
    refreshData(userId);
    // refreshData is intentionally called when the persisted user identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  function applyUserId() {
    const normalizedUserId = userIdDraft.trim() || "web-demo-user";
    setUserIdDraft(normalizedUserId);
    setUserId(normalizedUserId);
    setLastResponse(null);
  }

  function handleUserIdKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.currentTarget.blur();
      applyUserId();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const text = draft.trim();

    if (!text) {
      return;
    }

    setSubmitStatus("loading");
    setError(null);

    try {
      const response = await requestJson<MessageResponse>("/api/message", {
        method: "POST",
        body: JSON.stringify({
          user_external_id: userId,
          source: "web_text",
          text
        })
      });

      setLastResponse(response);
      setDraft("");
      await refreshData(userId);
      setSubmitStatus("ready");
    } catch (submitError) {
      setSubmitStatus("error");
      setError(submitError instanceof Error ? submitError.message : "Не удалось разобрать текст");
    }
  }

  async function handleTaskDone(task: Task) {
    if (task.status === "done" || completingTaskIds.has(task.id)) {
      return;
    }

    setCompletingTaskIds((current) => new Set(current).add(task.id));
    setError(null);

    try {
      await requestJson<Task>(`/api/tasks/${task.id}/done`, {
        method: "POST",
        body: JSON.stringify({ user_external_id: userId })
      });
      await refreshData(userId);
    } catch (completeError) {
      setError(
        completeError instanceof Error ? completeError.message : "Не удалось отметить задачу"
      );
    } finally {
      setCompletingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  return (
    <main className="app-shell">
      <header className="today-header">
        <div>
          <p className="date-line">{todayText}</p>
          <h1>Сегодня</h1>
        </div>
        <div className="progress-summary" aria-label={`Сделано ${doneToday.length} из ${todayTasks.length}`}>
          <strong>Сделано {doneToday.length} из {todayTasks.length}</strong>
          <span className="progress-track" aria-hidden="true">
            <span style={{ width: `${progressPercent}%` }} />
          </span>
        </div>
      </header>

      <section className="input-surface">
        <form onSubmit={handleSubmit}>
          <label htmlFor="mind-input">Что у тебя в голове?</label>
          <textarea
            id="mind-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Например: сегодня мало сил, надо оплатить счета и 40 минут поделать проект"
            rows={3}
          />
          <div className="input-actions">
            <span className={`service-status service-status-${backendStatus}`}>
              {backendStatus === "ready"
                ? "Сервис доступен"
                : backendStatus === "error"
                  ? "Сервис недоступен"
                  : "Проверяю сервис"}
            </span>
            <button type="submit" disabled={submitStatus === "loading" || !draft.trim()}>
              {submitStatus === "loading" ? "Разбираю..." : "Разобрать"}
            </button>
          </div>
        </form>
      </section>

      {error && <p className="error-line">{error}</p>}

      {lastResponse && (
        <section className="assistant-note" aria-live="polite">
          <p className="assistant-label">AI Life Planner</p>
          <p>{responseSummary(lastResponse.reply_text)}</p>
          <ChangeSummary response={lastResponse} />
        </section>
      )}

      <section className="today-plan" aria-labelledby="today-plan-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Главное на день</p>
            <h2 id="today-plan-title">План на сегодня</h2>
          </div>
          {plan?.energy_level && <span>{energyLabel(plan.energy_level)}</span>}
        </div>

        {dataStatus === "loading" ? (
          <EmptyState text="Собираю план дня..." />
        ) : scheduledItems.length || doneToday.length ? (
          <ul className="today-task-list">
            {scheduledItems.map((item) => {
              const task = item.task_id === null ? null : taskById.get(item.task_id);

              if (!task) {
                return null;
              }

              return (
                <TaskRow
                  key={`planned-${task.id}`}
                  task={task}
                  time={formatTime(item.start_time)}
                  pending={completingTaskIds.has(task.id)}
                  onDone={handleTaskDone}
                />
              );
            })}
            {doneToday.map((task) => (
              <TaskRow
                key={`done-${task.id}`}
                task={task}
                time={null}
                pending={false}
                onDone={handleTaskDone}
              />
            ))}
          </ul>
        ) : (
          <EmptyState text="На сегодня пока ничего не запланировано" />
        )}
      </section>

      {laterTasks.length > 0 && (
        <section className="secondary-section" aria-labelledby="later-title">
          <div className="section-heading compact-heading">
            <h2 id="later-title">Позже / без времени</h2>
          </div>
          <ul className="later-task-list">
            {laterTasks.map((task) => (
              <TaskRow
                key={`later-${task.id}`}
                task={task}
                time={task.target_date === todayValue ? null : formatTaskDate(task.target_date)}
                pending={completingTaskIds.has(task.id)}
                onDone={handleTaskDone}
                compact
              />
            ))}
          </ul>
        </section>
      )}

      <section className="goals-section" aria-labelledby="goals-title">
        <div className="section-heading compact-heading">
          <h2 id="goals-title">Цели</h2>
          {goals.length > 0 && <span>{goals.length}</span>}
        </div>
        {goals.length ? (
          <ul className="goal-list">
            {goals.map((goal) => (
              <li key={goal.id}>
                <span>{goal.title}</span>
                <small>{priorityLabel(goal.priority)}</small>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState text="Целей пока нет" />
        )}
      </section>

      <details className="developer-settings">
        <summary>Локальные настройки</summary>
        <div className="developer-settings-body">
          <label htmlFor="user-id">User ID</label>
          <input
            id="user-id"
            value={userIdDraft}
            onChange={(event) => setUserIdDraft(event.target.value)}
            onBlur={applyUserId}
            onKeyDown={handleUserIdKeyDown}
            autoComplete="off"
          />
          <p>Временная dev-идентификация, не production auth.</p>
          {lastResponse && <p>Распознано: {lastResponse.intent}</p>}
        </div>
      </details>
    </main>
  );
}

function TaskRow({
  task,
  time,
  pending,
  onDone,
  compact = false
}: {
  task: Task;
  time: string | null;
  pending: boolean;
  onDone: (task: Task) => Promise<void>;
  compact?: boolean;
}) {
  const done = task.status === "done";
  const duration = formatDuration(task.estimated_minutes);

  return (
    <li className={`task-row ${done ? "task-row-done" : ""} ${compact ? "task-row-compact" : ""}`}>
      <label>
        <input
          type="checkbox"
          checked={done}
          disabled={done || pending}
          onChange={() => onDone(task)}
          aria-label={`Отметить задачу «${task.title}» выполненной`}
        />
        <span className="task-copy">
          <strong>{task.title}</strong>
          <span className="task-meta">
            {done ? (
              "Сделано"
            ) : (
              <>
                {time && <span>{time}</span>}
                {duration && <span>{duration}</span>}
                {!time && !duration && <span>Без времени</span>}
              </>
            )}
          </span>
        </span>
      </label>
    </li>
  );
}

function ChangeSummary({ response }: { response: MessageResponse }) {
  const titles = [
    ...response.affected_tasks.map((task) => task.title),
    ...response.affected_goals.map((goal) => goal.title)
  ];

  if (!titles.length) {
    return null;
  }

  return <p className="change-line">Обновлено: {titles.join(", ")}</p>;
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

function energyLabel(energy: string): string {
  const labels: Record<string, string> = {
    low: "Бережный темп",
    medium: "Обычный темп",
    high: "Много энергии"
  };

  return labels[energy] || energy;
}
