import type { Task, TaskStatus, TaskStatusError } from "../types";

type TaskRowProps = {
  task: Task;
  time: string | null;
  unscheduledReason?: string | null;
  pending: boolean;
  error: TaskStatusError | null;
  changed?: boolean;
  scheduled?: boolean;
  onStatusChange: (task: Task, status: TaskStatus) => Promise<void>;
  onRetry: (task: Task, status: TaskStatus) => Promise<void>;
};

function formatDuration(minutes: number | null): string | null {
  if (!minutes) {
    return null;
  }

  if (minutes < 60) {
    return `${minutes} мин`;
  }

  if (minutes % 60 === 0) {
    return `${minutes / 60} ч`;
  }

  return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

function formatUnscheduledReason(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    preferred_window_passed: "Предпочтённое время прошло",
    no_available_slot: "Нет свободного окна",
    fixed_time_conflict: "Конфликт времени",
    fixed_time_passed: "Указанное время прошло",
    missing_fixed_time: "Нужно уточнить время",
    needs_clarification: "Нужно уточнение"
  };

  return reason ? labels[reason] || "Без времени" : "Без времени";
}

export default function TaskRow({
  task,
  time,
  unscheduledReason = null,
  pending,
  error,
  changed = false,
  scheduled = false,
  onStatusChange,
  onRetry
}: TaskRowProps) {
  const done = task.status === "done";
  const duration = formatDuration(task.estimated_minutes);
  const rowClassName = [
    "task-row",
    scheduled ? "task-row-scheduled" : "task-row-unscheduled",
    done ? "task-row-done" : "",
    pending ? "task-row-pending" : "",
    error ? "task-row-error" : "",
    changed ? "task-row-changed" : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <li className={rowClassName}>
      {scheduled && (
        <time className="task-time" dateTime={time || undefined}>{time || "—"}</time>
      )}
      <div className="task-content">
        <label className="task-control">
          <span className="checkbox-target">
            <input
              type="checkbox"
              checked={done}
              disabled={pending}
              onChange={(event) => {
                const nextStatus: TaskStatus = event.target.checked ? "done" : "planned";
                void onStatusChange(task, nextStatus);
              }}
              aria-label={
                done
                  ? `Вернуть задачу «${task.title}» в план`
                  : `Отметить задачу «${task.title}» выполненной`
              }
            />
          </span>
          <span className="task-copy">
            <strong>{task.title}</strong>
            <span className="task-meta">
              {pending ? (
                "Сохраняю…"
              ) : done ? (
                "Выполнено"
              ) : !scheduled ? (
                formatUnscheduledReason(unscheduledReason)
              ) : duration ? (
                duration
              ) : null}
            </span>
          </span>
        </label>

        {error && (
          <div className="task-error" role="alert">
            <span>Не удалось сохранить</span>
            <button type="button" onClick={() => void onRetry(task, error.retryStatus)}>
              Повторить
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
