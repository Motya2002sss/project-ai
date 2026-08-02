import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { checkHealth, getTodayData, processMessage, setTaskStatus } from "./api";
import BrainDumpCard from "./components/BrainDumpCard";
import TaskRow from "./components/TaskRow";
import TodayPlan from "./components/TodayPlan";
import type {
  Goal,
  LoadState,
  MessageResponse,
  Plan,
  Task,
  TaskStatus
} from "./types";

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

function priorityLabel(priority: string): string {
  const labels: Record<string, string> = {
    high: "важная",
    medium: "обычная",
    low: "низкий приоритет"
  };

  return labels[priority] || priority;
}

function responseSummary(response: MessageResponse): string {
  const taskTitles = response.affected_tasks.map((task) => task.title);
  const goalTitles = response.affected_goals.map((goal) => goal.title);

  if (taskTitles.length > 0) {
    return `День обновлён. Я добавил в план: ${taskTitles.join(", ")}.`;
  }

  if (goalTitles.length > 0) {
    return `Цели обновлены: ${goalTitles.join(", ")}.`;
  }

  const intentMessages: Record<string, string> = {
    show_plan: "План актуален. Можно начать с самого простого шага.",
    show_tasks: "Все текущие шаги собраны в одном месте.",
    mark_done: "Готово. Я обновил день после выполненной задачи.",
    daily_summary: "Итог дня сохранён. Оставшиеся шаги не потеряются.",
    update_profile: "Настройки сохранены. Я буду учитывать их в следующих планах.",
    reschedule: "День обновлён с учётом новых обстоятельств.",
    clear_tasks: "План очищен. Можно спокойно собрать день заново."
  };

  return (
    intentMessages[response.intent] ||
    response.reply_text.split("\n\nПлан дня:")[0].trim()
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

export default function App() {
  const initialUserId = localStorage.getItem(USER_ID_STORAGE_KEY) || "web-demo-user";
  const [userId, setUserId] = useState(initialUserId);
  const [userIdDraft, setUserIdDraft] = useState(initialUserId);
  const [draft, setDraft] = useState("");
  const [backendStatus, setBackendStatus] = useState<LoadState>("idle");
  const [dataStatus, setDataStatus] = useState<LoadState>("idle");
  const [submitStatus, setSubmitStatus] = useState<LoadState>("idle");
  const [pendingTaskIds, setPendingTaskIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [lastResponse, setLastResponse] = useState<MessageResponse | null>(null);
  const loadedUserId = useRef<string | null>(null);

  const todayText = useMemo(() => formatToday(), []);
  const todayValue = useMemo(() => localDateValue(), []);
  const todayTasks = useMemo(
    () => tasks.filter((task) => task.target_date === todayValue),
    [tasks, todayValue]
  );
  const scheduledItems = useMemo(
    () => (plan?.items || []).filter((item) => item.status === "planned"),
    [plan]
  );
  const scheduledTaskIds = useMemo(
    () =>
      new Set(
        scheduledItems.flatMap((item) => (item.task_id === null ? [] : [item.task_id]))
      ),
    [scheduledItems]
  );
  const laterTasks = useMemo(
    () =>
      tasks.filter(
        (task) =>
          task.status !== "done" &&
          (task.target_date !== todayValue || !scheduledTaskIds.has(task.id))
      ),
    [scheduledTaskIds, tasks, todayValue]
  );

  async function refreshData(nextUserId = userId): Promise<void> {
    setDataStatus("loading");

    try {
      const data = await getTodayData(nextUserId);
      setPlan(data.plan);
      setTasks(data.tasks);
      setGoals(data.goals);
      setDataStatus("ready");
    } catch (refreshError) {
      setDataStatus("error");
      throw refreshError;
    }
  }

  useEffect(() => {
    setBackendStatus("loading");
    void checkHealth()
      .then(() => setBackendStatus("ready"))
      .catch(() => setBackendStatus("error"));
  }, []);

  useEffect(() => {
    if (loadedUserId.current === userId) {
      return;
    }

    loadedUserId.current = userId;
    localStorage.setItem(USER_ID_STORAGE_KEY, userId);
    setError(null);

    void refreshData(userId).catch(() => {
      setError("Не удалось загрузить день. Проверь, что backend запущен, и попробуй ещё раз.");
    });
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

  async function handleSubmit(): Promise<void> {
    const text = draft.trim();

    if (!text) {
      return;
    }

    setSubmitStatus("loading");
    setError(null);

    let response: MessageResponse;

    try {
      response = await processMessage(userId, text);
    } catch {
      setSubmitStatus("error");
      setError("Не удалось обновить план. Текст сохранён — попробуй ещё раз.");
      return;
    }

    setLastResponse(response);
    setDraft("");

    try {
      await refreshData(userId);
    } catch {
      setError("Запись сохранена, но день не обновился. Перезагрузи страницу чуть позже.");
    }

    setSubmitStatus("ready");
  }

  async function handleTaskStatusChange(task: Task, nextStatus: TaskStatus): Promise<void> {
    if (task.status === nextStatus || pendingTaskIds.has(task.id)) {
      return;
    }

    setPendingTaskIds((current) => new Set(current).add(task.id));
    setError(null);

    try {
      await setTaskStatus(userId, task.id, nextStatus);
    } catch {
      setError("Не удалось обновить задачу. Её прежний статус сохранён.");
      setPendingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
      return;
    }

    try {
      await refreshData(userId);
    } catch {
      setError("Статус изменён, но не удалось обновить весь день. Перезагрузи страницу.");
    } finally {
      setPendingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  return (
    <main className="app-shell">
      <header className="today-header">
        <p className="date-line">{todayText}</p>
        <h1>Сегодня</h1>
        <p className="focus-line">Спокойно соберём день по шагам.</p>
      </header>

      {error && <p className="error-line">{error}</p>}

      <TodayPlan
        dataStatus={dataStatus}
        plan={plan}
        todayTasks={todayTasks}
        scheduledItems={scheduledItems}
        pendingTaskIds={pendingTaskIds}
        onStatusChange={handleTaskStatusChange}
      />

      <BrainDumpCard
        draft={draft}
        submitting={submitStatus === "loading"}
        onDraftChange={setDraft}
        onSubmit={handleSubmit}
      />

      {lastResponse && (
        <section className="assistant-note" aria-live="polite">
          <p className="assistant-label">План обновлён</p>
          <p>{responseSummary(lastResponse)}</p>
          <ChangeSummary response={lastResponse} />
        </section>
      )}

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
                pending={pendingTaskIds.has(task.id)}
                onStatusChange={handleTaskStatusChange}
                compact
              />
            ))}
          </ul>
        </section>
      )}

      {goals.length > 0 && (
        <section className="goals-section" aria-labelledby="goals-title">
          <div className="section-heading compact-heading">
            <h2 id="goals-title">Цели</h2>
            <span>{goals.length}</span>
          </div>
          <ul className="goal-list">
            {goals.map((goal) => (
              <li key={goal.id}>
                <span>{goal.title}</span>
                <small>{priorityLabel(goal.priority)}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

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
          <p>
            Backend:{" "}
            {backendStatus === "ready"
              ? "доступен"
              : backendStatus === "error"
                ? "недоступен"
                : "проверяется"}
          </p>
          {lastResponse && <p>Распознано: {lastResponse.intent}</p>}
        </div>
      </details>
    </main>
  );
}
