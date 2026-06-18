import { FormEvent, useEffect, useMemo, useState } from "react";

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

type Profile = {
  user_external_id: string;
  name: string | null;
  timezone: string;
  work_start_time: string | null;
  work_end_time: string | null;
  sleep_time: string | null;
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
  profile: Profile | null;
  plan_summary: Plan | null;
};

type LoadState = "idle" | "loading" | "ready" | "error";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const USER_ID_STORAGE_KEY = "ai-life-planner-user-id";

function formatToday(): string {
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long"
  }).format(new Date());
}

function formatTime(value: string | null): string {
  return value ? value.slice(0, 5) : "не указано";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short"
  }).format(new Date(`${value}T00:00:00`));
}

function priorityLabel(priority: string): string {
  const labels: Record<string, string> = {
    high: "важно",
    medium: "средне",
    low: "низко"
  };

  return labels[priority] || priority;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: "активна",
    done: "готово",
    draft: "черновик",
    overloaded: "перегружено",
    planned: "в плане",
    scheduled: "в плане",
    not_scheduled: "не влезло"
  };

  return labels[status] || status;
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
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export default function App() {
  const [userId, setUserId] = useState(() => {
    return localStorage.getItem(USER_ID_STORAGE_KEY) || "web-demo-user";
  });
  const [draft, setDraft] = useState("");
  const [backendStatus, setBackendStatus] = useState<LoadState>("idle");
  const [dataStatus, setDataStatus] = useState<LoadState>("idle");
  const [submitStatus, setSubmitStatus] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [lastResponse, setLastResponse] = useState<MessageResponse | null>(null);

  const todayText = useMemo(() => formatToday(), []);
  const trimmedUserId = userId.trim() || "web-demo-user";

  useEffect(() => {
    localStorage.setItem(USER_ID_STORAGE_KEY, trimmedUserId);
  }, [trimmedUserId]);

  async function refreshData(nextUserId = trimmedUserId) {
    setDataStatus("loading");
    setError(null);

    try {
      const [profileData, planData, taskData, goalData] = await Promise.all([
        requestJson<Profile>(`/api/profile/${encodeURIComponent(nextUserId)}`),
        requestJson<Plan>(`/api/plan/${encodeURIComponent(nextUserId)}?date=today`),
        requestJson<Task[]>(`/api/tasks/${encodeURIComponent(nextUserId)}`),
        requestJson<Goal[]>(`/api/goals/${encodeURIComponent(nextUserId)}`)
      ]);

      setProfile(profileData);
      setPlan(planData);
      setTasks(taskData);
      setGoals(goalData);
      setDataStatus("ready");
    } catch (refreshError) {
      setDataStatus("error");
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось загрузить данные");
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
    refreshData();
    // refreshData is intentionally called when the persisted user identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trimmedUserId]);

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
          user_external_id: trimmedUserId,
          source: "web_text",
          text
        })
      });

      setLastResponse(response);
      setDraft("");
      await refreshData(trimmedUserId);
      setSubmitStatus("ready");
    } catch (submitError) {
      setSubmitStatus("error");
      setError(submitError instanceof Error ? submitError.message : "Не удалось разобрать текст");
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{todayText}</p>
          <h1>Today</h1>
        </div>
        <div className="status-cluster" aria-label="Статус сервиса">
          <span className={`status-dot status-dot-${backendStatus}`} />
          <span>{backendStatus === "ready" ? "Backend OK" : "Backend"}</span>
        </div>
      </header>

      <section className="identity-row" aria-label="Временный пользователь">
        <label htmlFor="user-id">User ID</label>
        <input
          id="user-id"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          onBlur={() => setUserId(trimmedUserId)}
          autoComplete="off"
        />
      </section>

      <section className="input-section">
        <form onSubmit={handleSubmit}>
          <label htmlFor="mind-input">Что у тебя в голове?</label>
          <textarea
            id="mind-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Сегодня мало сил, надо оплатить счета и 40 минут поделать проект"
            rows={5}
          />
          <div className="input-actions">
            <span className="profile-hint">
              Работа {formatTime(profile?.work_start_time || null)}–{formatTime(profile?.work_end_time || null)}
              {" · "}сон {formatTime(profile?.sleep_time || null)}
            </span>
            <button type="submit" disabled={submitStatus === "loading" || !draft.trim()}>
              {submitStatus === "loading" ? "Разбираю..." : "Разобрать"}
            </button>
          </div>
        </form>
      </section>

      {error && <p className="error-line">{error}</p>}

      <section className="layout-grid">
        <article className="panel response-panel">
          <div className="section-heading">
            <h2>Ответ</h2>
            {lastResponse && <span>{lastResponse.intent}</span>}
          </div>
          {lastResponse ? (
            <div className="response-body">
              <p>{lastResponse.reply_text}</p>
              <ChangeSummary response={lastResponse} />
            </div>
          ) : (
            <EmptyState text="Напиши свободный текст, и здесь появится ответ планировщика." />
          )}
        </article>

        <article className="panel plan-panel">
          <div className="section-heading">
            <h2>План на сегодня</h2>
            {plan && <span>{statusLabel(plan.status)}</span>}
          </div>
          {plan?.items.length ? (
            <ol className="plan-list">
              {plan.items.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.title}</strong>
                    <span>{statusLabel(item.status)}</span>
                  </div>
                  <time>
                    {formatTime(item.start_time)} - {formatTime(item.end_time)}
                  </time>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState text={dataStatus === "loading" ? "Загружаю план..." : "План пока пустой."} />
          )}
        </article>

        <article className="panel">
          <div className="section-heading">
            <h2>Задачи</h2>
            <span>{tasks.length}</span>
          </div>
          {tasks.length ? (
            <ul className="task-list">
              {tasks.map((task) => (
                <li key={task.id}>
                  <div>
                    <strong>{task.title}</strong>
                    <span>{formatDate(task.target_date)}</span>
                  </div>
                  <div className="badges">
                    <span>{statusLabel(task.status)}</span>
                    <span>{priorityLabel(task.priority)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text={dataStatus === "loading" ? "Загружаю задачи..." : "Активных задач нет."} />
          )}
        </article>

        <article className="panel">
          <div className="section-heading">
            <h2>Цели</h2>
            <span>{goals.length}</span>
          </div>
          {goals.length ? (
            <ul className="goal-list">
              {goals.map((goal) => (
                <li key={goal.id}>
                  <strong>{goal.title}</strong>
                  <span>{priorityLabel(goal.priority)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text={dataStatus === "loading" ? "Загружаю цели..." : "Целей пока нет."} />
          )}
        </article>
      </section>
    </main>
  );
}

function ChangeSummary({ response }: { response: MessageResponse }) {
  const hasChanges = response.affected_tasks.length > 0 || response.affected_goals.length > 0;

  if (!hasChanges) {
    return null;
  }

  return (
    <div className="changes">
      {response.affected_tasks.length > 0 && (
        <div>
          <span>Задачи</span>
          <ul>
            {response.affected_tasks.map((task) => (
              <li key={task.id}>{task.title}</li>
            ))}
          </ul>
        </div>
      )}
      {response.affected_goals.length > 0 && (
        <div>
          <span>Цели</span>
          <ul>
            {response.affected_goals.map((goal) => (
              <li key={goal.id}>{goal.title}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}
