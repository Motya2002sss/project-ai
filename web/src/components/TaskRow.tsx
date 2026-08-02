import type { Task, TaskStatus } from "../types";

type TaskRowProps = {
  task: Task;
  time: string | null;
  pending: boolean;
  onStatusChange: (task: Task, status: TaskStatus) => Promise<void>;
  compact?: boolean;
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

export default function TaskRow({
  task,
  time,
  pending,
  onStatusChange,
  compact = false
}: TaskRowProps) {
  const done = task.status === "done";
  const duration = formatDuration(task.estimated_minutes);
  const rowClassName = [
    "task-row",
    done ? "task-row-done" : "",
    compact ? "task-row-compact" : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <li className={rowClassName}>
      <label>
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
        <span className="task-copy">
          <strong>{task.title}</strong>
          <span className="task-meta">
            {pending ? (
              "Обновляю..."
            ) : done ? (
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
