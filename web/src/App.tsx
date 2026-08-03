import { useEffect, useMemo, useRef, useState } from "react";

import {
  checkHealth,
  getGoals,
  getTodayPlan,
  getTodayTasks,
  processMessage,
  setTaskStatus
} from "./api";
import DayComposer from "./components/DayComposer";
import DayFocus from "./components/DayFocus";
import DayProgress from "./components/DayProgress";
import PlanUpdateSummary from "./components/PlanUpdateSummary";
import TodayHeader from "./components/TodayHeader";
import TodayPlan from "./components/TodayPlan";
import type {
  Goal,
  LoadState,
  MessageResponse,
  Plan,
  PlanChange,
  PlanUpdate,
  Task,
  TaskPlacement,
  TaskStatus,
  TaskStatusError
} from "./types";

const USER_ID_STORAGE_KEY = "ai-life-planner-user-id";

type TodaySnapshot = {
  plan: Plan | null;
  tasks: Task[] | null;
  goals: Goal[] | null;
  failed: number;
};

function localDateValue(value = new Date()): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function formatToday(value: Date): string {
  const formatted = new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long"
  }).format(value);

  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}

function formatTaskDate(value: string): string {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (value === localDateValue(today)) {
    return "сегодня";
  }

  if (value === localDateValue(tomorrow)) {
    return "завтра";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short"
  }).format(new Date(`${value}T00:00:00`));
}

function energyLabel(energy: string | null): string | null {
  const labels: Record<string, string> = {
    low: "Бережный темп",
    medium: "Обычный темп",
    high: "Энергичный темп"
  };

  return energy ? labels[energy] || null : null;
}

function placementsFromPlan(plan: Plan | null): Map<number, TaskPlacement> {
  const placements = new Map<number, TaskPlacement>();

  for (const item of plan?.items || []) {
    if (item.task_id === null) {
      continue;
    }

    placements.set(item.task_id, {
      taskId: item.task_id,
      startTime: item.start_time,
      endTime: item.end_time,
      planStatus: item.status,
      unscheduledReason: item.unscheduled_reason
    });
  }

  return placements;
}

function mergePlacements(
  current: Map<number, TaskPlacement>,
  plan: Plan,
  reset: boolean
): Map<number, TaskPlacement> {
  const next = reset ? new Map<number, TaskPlacement>() : new Map(current);

  for (const [taskId, placement] of placementsFromPlan(plan)) {
    next.set(taskId, placement);
  }

  return next;
}

function buildPlanUpdate(
  response: MessageResponse,
  previousTasks: Task[],
  nextTasks: Task[],
  nextPlan: Plan | null
): PlanUpdate {
  const previousById = new Map(previousTasks.map((task) => [task.id, task]));
  const nextById = new Map(nextTasks.map((task) => [task.id, task]));
  const affectedById = new Map(response.affected_tasks.map((task) => [task.id, task]));
  const nextPlacements = placementsFromPlan(nextPlan);
  const changes: PlanChange[] = [];

  const taskForId = (taskId: number): Task | undefined =>
    nextById.get(taskId) || affectedById.get(taskId) || previousById.get(taskId);

  for (const taskId of response.plan_diff.created_task_ids) {
    const task = taskForId(taskId);

    if (!task) continue;

    const placement = nextPlacements.get(taskId);
    changes.push({
      kind: "added",
      title: task.title,
      detail: placement?.startTime
        ? placement.startTime.slice(0, 5)
        : task.target_date !== localDateValue()
          ? formatTaskDate(task.target_date)
          : null
    });
  }

  for (const taskId of response.plan_diff.updated_task_ids) {
    const task = taskForId(taskId);
    const previous = previousById.get(taskId);

    if (!task) continue;

    changes.push({
      kind: "moved",
      title: task.title,
      detail: previous?.target_date !== task.target_date ? formatTaskDate(task.target_date) : "обновлено"
    });
  }

  for (const taskId of response.plan_diff.completed_task_ids) {
    const task = taskForId(taskId);
    if (task) changes.push({ kind: "completed", title: task.title, detail: "выполнено" });
  }

  for (const taskId of response.plan_diff.cancelled_task_ids) {
    const task = taskForId(taskId);
    if (task) changes.push({ kind: "cancelled", title: task.title, detail: "отменено" });
  }

  for (const moved of response.plan_diff.moved_plan_items) {
    changes.push({ kind: "moved", title: moved.title, detail: moved.new_start.slice(0, 5) });
  }

  for (const taskId of response.plan_diff.unscheduled_task_ids) {
    const task = taskForId(taskId);
    if (task) changes.push({ kind: "unscheduled", title: task.title, detail: "без времени" });
  }

  const limitedChanges = changes.slice(0, 5);
  const goalOnly = response.affected_goals.length > 0 && limitedChanges.length === 0;

  return {
    title: response.status === "applied" ? response.plan_summary ? "План обновлён" : "Изменения сохранены" : "Нужно уточнение",
    message: response.clarification_question || (goalOnly
      ? "Цели обновлены. Они будут учитываться в следующих планах."
      : limitedChanges.length === 0
        ? "День актуализирован без дополнительных изменений в задачах."
        : null),
    changes: limitedChanges
  };
}

export default function App() {
  const initialUserId = localStorage.getItem(USER_ID_STORAGE_KEY) || "web-demo-user";
  const [userId, setUserId] = useState(initialUserId);
  const [userIdDraft, setUserIdDraft] = useState(initialUserId);
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [draft, setDraft] = useState("");
  const [composerOpen, setComposerOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState<LoadState>("idle");
  const [planStatus, setPlanStatus] = useState<LoadState>("idle");
  const [tasksStatus, setTasksStatus] = useState<LoadState>("idle");
  const [goalsStatus, setGoalsStatus] = useState<LoadState>("idle");
  const [submitStatus, setSubmitStatus] = useState<LoadState>("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);
  const [pendingTaskIds, setPendingTaskIds] = useState<Set<number>>(new Set());
  const [taskErrors, setTaskErrors] = useState<Map<number, TaskStatusError>>(new Map());
  const [changedTaskIds, setChangedTaskIds] = useState<Set<number>>(new Set());
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [taskPlacements, setTaskPlacements] = useState<Map<number, TaskPlacement>>(new Map());
  const [lastUpdate, setLastUpdate] = useState<PlanUpdate | null>(null);
  const activeLoadKey = useRef<string | null>(null);
  const highlightTimer = useRef<number | null>(null);

  const todayValue = localDateValue(currentDate);
  const todayText = formatToday(currentDate);
  const todayTasks = useMemo(
    () => tasks.filter((task) => task.target_date === todayValue),
    [tasks, todayValue]
  );
  const doneCount = todayTasks.filter((task) => task.status === "done").length;
  const allDone = todayTasks.length > 0 && doneCount === todayTasks.length;
  const scheduledTasks = useMemo(
    () =>
      todayTasks
        .flatMap((task) => {
          const placement = taskPlacements.get(task.id);
          return placement?.startTime ? [{ task, placement }] : [];
        })
        .sort((left, right) =>
          (left.placement.startTime || "").localeCompare(right.placement.startTime || "")
        ),
    [taskPlacements, todayTasks]
  );
  const scheduledTaskIds = useMemo(
    () => new Set(scheduledTasks.map(({ task }) => task.id)),
    [scheduledTasks]
  );
  const unscheduledTasks = useMemo(
    () => todayTasks.filter((task) => !scheduledTaskIds.has(task.id)),
    [scheduledTaskIds, todayTasks]
  );
  const focusText = allDone
    ? "На сегодня достаточно."
    : plan?.focus_text ||
      (planStatus === "error"
        ? todayTasks.length > 0
          ? "Задачи на сегодня видны, но расписание пока недоступно."
          : "Не удалось загрузить фокус дня. Попробуй обновить."
        : tasksStatus === "ready" && todayTasks.length === 0
          ? "План пока пуст. Добавь дела одним сообщением — я распределю их по дню."
          : "Собираю актуальный фокус дня.");

  async function refreshData(
    nextUserId = userId,
    options: { initial?: boolean; resetPlacements?: boolean; preservePlacements?: boolean } = {}
  ): Promise<TodaySnapshot> {
    const loadKey = `${nextUserId}:${todayValue}`;
    activeLoadKey.current = loadKey;

    if (options.initial) {
      setPlanStatus("loading");
      setTasksStatus("loading");
      setGoalsStatus("loading");
    }

    let failed = 0;
    let nextPlan: Plan | null = null;
    let nextTasks: Task[] | null = null;
    let nextGoals: Goal[] | null = null;

    try {
      nextPlan = await getTodayPlan(nextUserId);

      if (activeLoadKey.current !== loadKey) {
        return { plan: null, tasks: null, goals: null, failed: 3 };
      }

      setPlan(nextPlan);
      if (!options.preservePlacements) {
        setTaskPlacements((current) =>
          mergePlacements(current, nextPlan as Plan, Boolean(options.resetPlacements))
        );
      }
      setPlanStatus("ready");
    } catch {
      failed += 1;
      setPlanStatus("error");
    }

    try {
      nextTasks = await getTodayTasks(nextUserId);

      if (activeLoadKey.current !== loadKey) {
        return { plan: null, tasks: null, goals: null, failed: 3 };
      }

      setTasks(nextTasks);
      setTasksStatus("ready");
    } catch {
      failed += 1;
      setTasksStatus("error");
    }

    try {
      nextGoals = await getGoals(nextUserId);

      if (activeLoadKey.current !== loadKey) {
        return { plan: null, tasks: null, goals: null, failed: 3 };
      }

      setGoals(nextGoals);
      setGoalsStatus("ready");
    } catch {
      failed += 1;
      setGoalsStatus("error");
    }

    return { plan: nextPlan, tasks: nextTasks, goals: nextGoals, failed };
  }

  useEffect(() => {
    let timer = 0;

    function scheduleRollover() {
      const now = new Date();
      const nextDay = new Date(now);
      nextDay.setHours(24, 0, 1, 0);
      timer = window.setTimeout(() => {
        setCurrentDate(new Date());
        scheduleRollover();
      }, nextDay.getTime() - now.getTime());
    }

    scheduleRollover();
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    setBackendStatus("loading");
    void checkHealth()
      .then(() => setBackendStatus("ready"))
      .catch(() => setBackendStatus("error"));
  }, []);

  useEffect(() => {
    localStorage.setItem(USER_ID_STORAGE_KEY, userId);
    setPlan(null);
    setTasks([]);
    setGoals([]);
    setTaskPlacements(new Map());
    setTaskErrors(new Map());
    setLastUpdate(null);
    setRefreshNotice(null);

    void refreshData(userId, { initial: true, resetPlacements: true }).then((snapshot) => {
      if (snapshot.failed >= 2) {
        setRefreshNotice("Не удалось загрузить день. Проверь подключение и попробуй ещё раз.");
      }
    });
  }, [todayValue, userId]);

  useEffect(() => () => {
    if (highlightTimer.current) {
      window.clearTimeout(highlightTimer.current);
    }
  }, []);

  function applyUserId() {
    const normalizedUserId = userIdDraft.trim() || "web-demo-user";
    setUserIdDraft(normalizedUserId);
    setUserId(normalizedUserId);
  }

  async function handleSubmit(): Promise<void> {
    const text = draft.trim();

    if (!text || submitStatus === "loading") {
      return;
    }

    const previousTasks = tasks.map((task) => ({ ...task }));
    setSubmitStatus("loading");
    setSubmitError(null);
    setComposerOpen(false);
    setRefreshNotice(null);

    let response: MessageResponse;

    try {
      response = await processMessage(userId, text);
    } catch {
      setSubmitStatus("error");
      setSubmitError("Не получилось обновить план");
      setComposerOpen(true);
      return;
    }

    if (response.plan_summary) {
      setPlan(response.plan_summary);
      setTaskPlacements((current) => mergePlacements(current, response.plan_summary as Plan, false));
    }

    const snapshot = await refreshData(userId);
    const nextTasks = snapshot.tasks || tasks;
    const nextPlan = snapshot.plan || response.plan_summary || plan;
    const update = buildPlanUpdate(
      response,
      previousTasks,
      nextTasks,
      nextPlan
    );

    setLastUpdate(update);
    setChangedTaskIds(new Set(response.affected_tasks.map((task) => task.id)));
    setDraft("");
    setComposerOpen(response.needs_clarification);
    setSubmitStatus("ready");

    if (snapshot.failed > 0) {
      setRefreshNotice("Изменения сохранены, но часть дня не обновилась. Можно повторить загрузку.");
    }

    if (highlightTimer.current) {
      window.clearTimeout(highlightTimer.current);
    }

    highlightTimer.current = window.setTimeout(() => setChangedTaskIds(new Set()), 1800);
  }

  async function handleTaskStatusChange(task: Task, nextStatus: TaskStatus): Promise<void> {
    if (task.status === nextStatus || pendingTaskIds.has(task.id)) {
      return;
    }

    const previousStatus = task.status;
    setLastUpdate(null);
    setPendingTaskIds((current) => new Set(current).add(task.id));
    setTaskErrors((current) => {
      const next = new Map(current);
      next.delete(task.id);
      return next;
    });
    setTasks((current) =>
      current.map((item) => item.id === task.id ? { ...item, status: nextStatus } : item)
    );

    try {
      const savedTask = await setTaskStatus(userId, task.id, nextStatus);
      setTasks((current) =>
        current.map((item) => item.id === task.id ? savedTask : item)
      );
    } catch {
      setTasks((current) =>
        current.map((item) => item.id === task.id ? { ...item, status: previousStatus } : item)
      );
      setTaskErrors((current) => new Map(current).set(task.id, { retryStatus: nextStatus }));
      setPendingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
      return;
    }

    const snapshot = await refreshData(userId, { preservePlacements: true });

    if (snapshot.failed > 0) {
      setRefreshNotice("Статус сохранён, но часть дня не обновилась.");
    }

    setPendingTaskIds((current) => {
      const next = new Set(current);
      next.delete(task.id);
      return next;
    });
  }

  const criticalLoading = tasksStatus === "loading" && tasks.length === 0;

  return (
    <div className="page-shell">
      <main className="app-canvas">
        <TodayHeader
          dateText={todayText}
          userIdDraft={userIdDraft}
          backendStatus={backendStatus}
          onUserIdDraftChange={setUserIdDraft}
          onApplyUserId={applyUserId}
        />

        <DayFocus
          text={focusText}
          loading={planStatus === "loading" && plan === null}
        />

        <DayProgress
          done={doneCount}
          total={todayTasks.length}
          contextLabel={energyLabel(plan?.energy_level || null)}
          loading={tasksStatus === "loading" && tasks.length === 0}
        />

        {refreshNotice && (
          <div className="global-notice" role="alert">
            <p>{refreshNotice}</p>
            <button
              type="button"
              onClick={() => {
                setRefreshNotice(null);
                void refreshData(userId, { initial: true }).then((snapshot) => {
                  if (snapshot.failed >= 2) {
                    setRefreshNotice("Не удалось загрузить день. Проверь подключение и попробуй ещё раз.");
                  }
                });
              }}
            >
              Обновить
            </button>
          </div>
        )}

        <TodayPlan
          planStatus={planStatus}
          tasksStatus={tasksStatus}
          todayTasks={todayTasks}
          scheduledTasks={scheduledTasks}
          unscheduledTasks={unscheduledTasks}
          taskPlacements={taskPlacements}
          pendingTaskIds={pendingTaskIds}
          taskErrors={taskErrors}
          changedTaskIds={changedTaskIds}
          onStatusChange={handleTaskStatusChange}
          onRetry={handleTaskStatusChange}
        />

        {lastUpdate && <PlanUpdateSummary update={lastUpdate} />}

        {goalsStatus === "ready" && goals.length > 0 && (
          <details className="extra-section">
            <summary>
              <span>Цели</span>
              <small>{goals.length}</small>
            </summary>
            <ul>
              {goals.map((goal) => <li key={goal.id}>{goal.title}</li>)}
            </ul>
          </details>
        )}
      </main>

      <DayComposer
        open={composerOpen}
        draft={draft}
        status={submitStatus}
        error={submitError}
        disabled={criticalLoading}
        onOpenChange={setComposerOpen}
        onDraftChange={setDraft}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
