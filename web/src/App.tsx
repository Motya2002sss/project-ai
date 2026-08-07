import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  checkHealth,
  getTodayData,
  processMessage,
  setTaskStatus
} from "./api";
import { composerReducer, initialComposerState } from "./composerState";
import DayComposer from "./components/DayComposer";
import DayFocus from "./components/DayFocus";
import DayProgress from "./components/DayProgress";
import PlanUpdateSummary from "./components/PlanUpdateSummary";
import TodayHeader from "./components/TodayHeader";
import TodayPlan from "./components/TodayPlan";
import type {
  Goal,
  DaySnapshot,
  InteractionOption,
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

type DayViewState = {
  plan: Plan | null;
  tasks: Task[];
  goals: Goal[];
  taskPlacements: Map<number, TaskPlacement>;
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

function dateFromValue(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatTaskDate(value: string, referenceDate = localDateValue()): string {
  const today = dateFromValue(referenceDate);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (value === referenceDate) {
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
  const snapshotDate = response.day_snapshot?.date || nextPlan?.date || localDateValue();
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
        : task.target_date !== snapshotDate
          ? formatTaskDate(task.target_date, snapshotDate)
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
      detail: previous?.target_date !== task.target_date
        ? formatTaskDate(task.target_date, snapshotDate)
        : "обновлено"
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

  for (const routineId of response.plan_diff.created_routine_ids) {
    const routine = response.affected_routines.find((item) => item.id === routineId);

    if (routine) {
      changes.push({ kind: "routine", title: routine.title, detail: "регулярно" });
    }
  }

  if (response.plan_diff.availability_change) {
    changes.push({
      kind: "availability",
      title: response.plan_diff.availability_change,
      detail: null
    });
  }

  const limitedChanges = changes.slice(0, 5);
  const goalOnly = response.affected_goals.length > 0 && limitedChanges.length === 0;

  const titles: Record<string, string> = {
    applied: response.plan_summary ? "План обновлён" : "Изменения сохранены",
    clarification_required: "Нужно уточнение",
    needs_clarification: "Нужно уточнение",
    confirmation_required: "Нужно подтверждение",
    conflict: "Конфликт в плане",
    no_change: "План не изменён",
    unsupported_capability: "Функция пока недоступна",
    failed: "Не получилось обновить план"
  };
  const statusMessage = ["no_change", "unsupported_capability", "failed"].includes(response.status)
    ? response.reply_text
    : null;

  return {
    title: titles[response.status] || "План обновлён",
    message: response.clarification?.question
      || response.confirmation?.summary
      || response.conflict_details?.message
      || statusMessage
      || (goalOnly
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
  const [composer, dispatchComposer] = useReducer(composerReducer, initialComposerState);
  const [backendStatus, setBackendStatus] = useState<LoadState>("idle");
  const [planStatus, setPlanStatus] = useState<LoadState>("idle");
  const [tasksStatus, setTasksStatus] = useState<LoadState>("idle");
  const [goalsStatus, setGoalsStatus] = useState<LoadState>("idle");
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);
  const [pendingTaskIds, setPendingTaskIds] = useState<Set<number>>(new Set());
  const [taskErrors, setTaskErrors] = useState<Map<number, TaskStatusError>>(new Map());
  const [changedTaskIds, setChangedTaskIds] = useState<Set<number>>(new Set());
  const [day, setDay] = useState<DayViewState>({
    plan: null,
    tasks: [],
    goals: [],
    taskPlacements: new Map()
  });
  const [lastUpdate, setLastUpdate] = useState<PlanUpdate | null>(null);
  const activeLoadKey = useRef<string | null>(null);
  const activeSubmitRequest = useRef<string | null>(null);
  const submitAbortController = useRef<AbortController | null>(null);
  const highlightTimer = useRef<number | null>(null);
  const { plan, tasks, goals, taskPlacements } = day;

  const localTodayValue = localDateValue(currentDate);
  const todayValue = plan?.date || localTodayValue;
  const todayText = formatToday(dateFromValue(todayValue));
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

  function applySnapshot(snapshot: DaySnapshot, resetPlacements = true): void {
    setDay((current) => ({
      plan: snapshot.plan,
      tasks: snapshot.tasks,
      goals: snapshot.goals,
      taskPlacements: mergePlacements(current.taskPlacements, snapshot.plan, resetPlacements)
    }));
    setPlanStatus("ready");
    setTasksStatus("ready");
    setGoalsStatus("ready");
  }

  async function refreshData(
    nextUserId = userId,
    options: { initial?: boolean; resetPlacements?: boolean } = {}
  ): Promise<DaySnapshot | null> {
    const loadKey = `${nextUserId}:${localTodayValue}`;
    activeLoadKey.current = loadKey;

    if (options.initial) {
      setPlanStatus("loading");
      setTasksStatus("loading");
      setGoalsStatus("loading");
    }

    try {
      const snapshot = await getTodayData(nextUserId);

      if (activeLoadKey.current !== loadKey) {
        return null;
      }

      applySnapshot(
        snapshot,
        options.resetPlacements !== false
      );
      return snapshot;
    } catch {
      setPlanStatus("error");
      setTasksStatus("error");
      setGoalsStatus("error");
      return null;
    }
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
    submitAbortController.current?.abort();
    submitAbortController.current = null;
    activeSubmitRequest.current = null;
    dispatchComposer({ type: "reset" });
    setDay({ plan: null, tasks: [], goals: [], taskPlacements: new Map() });
    setTaskErrors(new Map());
    setLastUpdate(null);
    setRefreshNotice(null);

    void refreshData(userId, { initial: true, resetPlacements: true }).then((snapshot) => {
      if (!snapshot) {
        setRefreshNotice("Не удалось загрузить день. Проверь подключение и попробуй ещё раз.");
      }
    });
  }, [localTodayValue, userId]);

  useEffect(() => () => {
    submitAbortController.current?.abort();
    if (highlightTimer.current) {
      window.clearTimeout(highlightTimer.current);
    }
  }, []);

  function applyUserId() {
    const normalizedUserId = userIdDraft.trim() || "web-demo-user";
    setUserIdDraft(normalizedUserId);
    setUserId(normalizedUserId);
  }

  async function handleSubmit(
    interactionId: string | null = null,
    option: InteractionOption | null = null
  ): Promise<void> {
    const text = (option?.value || composer.draft).trim();

    if (!text || composer.phase === "submitting") {
      return;
    }

    const previousTasks = tasks.map((task) => ({ ...task }));
    const requestId = option || interactionId
      ? crypto.randomUUID()
      : composer.retryRequestId || crypto.randomUUID();
    const controller = new AbortController();
    submitAbortController.current?.abort();
    submitAbortController.current = controller;
    activeSubmitRequest.current = requestId;
    dispatchComposer({ type: "submit", requestId });
    setRefreshNotice(null);
    const slowTimer = window.setTimeout(
      () => dispatchComposer({ type: "slow", requestId }),
      5_000
    );

    try {
      const response = await processMessage(
        userId,
        {
          text,
          requestId,
          interactionId,
          optionId: option?.id || null
        },
        controller.signal
      );

      if (activeSubmitRequest.current !== requestId || response.request_id !== requestId) {
        return;
      }

      if (!response.day_snapshot) {
        throw new Error("Message response did not include a day snapshot");
      }

      const snapshot = response.day_snapshot;
      applySnapshot(snapshot, true);
      const update = buildPlanUpdate(
        response,
        previousTasks,
        snapshot.tasks,
        snapshot.plan
      );

      setLastUpdate(update);
      setChangedTaskIds(new Set(response.affected_tasks.map((task) => task.id)));
      dispatchComposer({
        type: "response",
        requestId,
        status: response.status,
        clarification: response.clarification,
        confirmation: response.confirmation,
        conflict: response.conflict_details
      });
    } catch {
      if (activeSubmitRequest.current === requestId) {
        dispatchComposer({
          type: "error",
          requestId,
          message: "Не получилось обновить план"
        });
      }
      return;
    } finally {
      window.clearTimeout(slowTimer);
      if (activeSubmitRequest.current === requestId) {
        activeSubmitRequest.current = null;
      }
      if (submitAbortController.current === controller) {
        submitAbortController.current = null;
      }
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
    setDay((current) => ({
      ...current,
      tasks: current.tasks.map((item) =>
        item.id === task.id ? { ...item, status: nextStatus } : item
      )
    }));

    try {
      const savedTask = await setTaskStatus(userId, task.id, nextStatus);
      setDay((current) => ({
        ...current,
        tasks: current.tasks.map((item) => item.id === task.id ? savedTask : item)
      }));
    } catch {
      setDay((current) => ({
        ...current,
        tasks: current.tasks.map((item) =>
          item.id === task.id ? { ...item, status: previousStatus } : item
        )
      }));
      setTaskErrors((current) => new Map(current).set(task.id, { retryStatus: nextStatus }));
      setPendingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
      return;
    }

    const snapshot = await refreshData(userId, { resetPlacements: true });

    if (!snapshot) {
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
                    if (!snapshot) {
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
        open={composer.open}
        draft={composer.draft}
        phase={composer.phase}
        slow={composer.slow}
        error={composer.error}
        clarification={composer.clarification}
        confirmation={composer.confirmation}
        conflict={composer.conflict}
        disabled={criticalLoading}
        onOpenChange={(open) => dispatchComposer({ type: open ? "open" : "close" })}
        onDraftChange={(value) => dispatchComposer({ type: "edit", value })}
        onSubmit={handleSubmit}
        onOption={(interactionId, option) => handleSubmit(interactionId, option)}
      />
    </div>
  );
}
