import TaskRow from "./TaskRow";
import type {
  LoadState,
  Task,
  TaskPlacement,
  TaskStatus,
  TaskStatusError
} from "../types";

type TodayPlanProps = {
  planStatus: LoadState;
  tasksStatus: LoadState;
  todayTasks: Task[];
  scheduledTasks: Array<{ task: Task; placement: TaskPlacement }>;
  unscheduledTasks: Task[];
  taskPlacements: Map<number, TaskPlacement>;
  pendingTaskIds: Set<number>;
  taskErrors: Map<number, TaskStatusError>;
  changedTaskIds: Set<number>;
  onStatusChange: (task: Task, status: TaskStatus) => Promise<void>;
  onRetry: (task: Task, status: TaskStatus) => Promise<void>;
};

function formatTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null;
}

function TaskSkeletons() {
  return (
    <div className="task-skeletons" aria-label="Загружаю задачи">
      {[0, 1, 2].map((item) => <span key={item} />)}
    </div>
  );
}

export default function TodayPlan({
  planStatus,
  tasksStatus,
  todayTasks,
  scheduledTasks,
  unscheduledTasks,
  taskPlacements,
  pendingTaskIds,
  taskErrors,
  changedTaskIds,
  onStatusChange,
  onRetry
}: TodayPlanProps) {
  const initialLoading = tasksStatus === "loading" && todayTasks.length === 0;

  if (initialLoading) {
    return <TaskSkeletons />;
  }

  if (tasksStatus === "error" && todayTasks.length === 0) {
    return (
      <section className="empty-day" aria-labelledby="tasks-unavailable-title">
        <h2 id="tasks-unavailable-title">Задачи пока недоступны</h2>
        <p>Попробуй обновить день. Твои записи не удалены.</p>
      </section>
    );
  }

  if (todayTasks.length === 0) {
    return (
      <section className="empty-day" aria-labelledby="empty-day-title">
        <h2 id="empty-day-title">На сегодня задач нет</h2>
        <p>Можно оставить день свободным<br />или рассказать, что появилось.</p>
      </section>
    );
  }

  return (
    <div className="task-sections">
      {scheduledTasks.length > 0 && (
        <section className="task-section scheduled-section" aria-labelledby="scheduled-title">
          <div className="section-heading">
            <h2 id="scheduled-title">Запланировано</h2>
            <span>{scheduledTasks.length}</span>
          </div>
          <ul className="task-list scheduled-list">
            {scheduledTasks.map(({ task, placement }) => (
              <TaskRow
                key={`scheduled-${task.id}`}
                task={task}
                time={formatTime(placement.startTime)}
                pending={pendingTaskIds.has(task.id)}
                error={taskErrors.get(task.id) || null}
                changed={changedTaskIds.has(task.id)}
                scheduled
                onStatusChange={onStatusChange}
                onRetry={onRetry}
              />
            ))}
          </ul>
        </section>
      )}

      {unscheduledTasks.length > 0 && (
        <section className="task-section unscheduled-section" aria-labelledby="unscheduled-title">
          <div className="section-heading">
            <h2 id="unscheduled-title">Без времени</h2>
            <span>{unscheduledTasks.length}</span>
          </div>
          <ul className="task-list unscheduled-list">
            {unscheduledTasks.map((task) => (
              <TaskRow
                key={`unscheduled-${task.id}`}
                task={task}
                time={null}
                unscheduledReason={taskPlacements.get(task.id)?.unscheduledReason || null}
                pending={pendingTaskIds.has(task.id)}
                error={taskErrors.get(task.id) || null}
                changed={changedTaskIds.has(task.id)}
                onStatusChange={onStatusChange}
                onRetry={onRetry}
              />
            ))}
          </ul>
          {planStatus === "error" && (
            <p className="section-note">Расписание загрузилось не полностью. Задачи сохранены.</p>
          )}
        </section>
      )}
    </div>
  );
}
