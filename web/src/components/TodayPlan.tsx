import TaskRow from "./TaskRow";
import type { LoadState, Plan, PlanItem, Task, TaskStatus } from "../types";

type TodayPlanProps = {
  dataStatus: LoadState;
  plan: Plan | null;
  todayTasks: Task[];
  scheduledItems: PlanItem[];
  pendingTaskIds: Set<number>;
  onStatusChange: (task: Task, status: TaskStatus) => Promise<void>;
};

function formatTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null;
}

function energyLabel(energy: string): string {
  const labels: Record<string, string> = {
    low: "Бережный темп",
    medium: "Обычный темп",
    high: "Много энергии"
  };

  return labels[energy] || energy;
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

export default function TodayPlan({
  dataStatus,
  plan,
  todayTasks,
  scheduledItems,
  pendingTaskIds,
  onStatusChange
}: TodayPlanProps) {
  const doneToday = todayTasks.filter((task) => task.status === "done");
  const taskById = new Map(todayTasks.map((task) => [task.id, task]));
  const progressPercent = todayTasks.length
    ? Math.round((doneToday.length / todayTasks.length) * 100)
    : 0;
  const allTodayDone = todayTasks.length > 0 && doneToday.length === todayTasks.length;

  return (
    <section className="today-plan" aria-labelledby="today-plan-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Вот твой день</p>
          <h2 id="today-plan-title">План на сегодня</h2>
        </div>
        {todayTasks.length > 0 && (
          <div
            className="plan-progress"
            aria-label={`Сделано ${doneToday.length} из ${todayTasks.length}`}
          >
            <span>
              {allTodayDone
                ? "Все задачи закрыты"
                : `Сделано ${doneToday.length} из ${todayTasks.length}`}
            </span>
            <span className="progress-track" aria-hidden="true">
              <span style={{ width: `${progressPercent}%` }} />
            </span>
          </div>
        )}
      </div>

      {plan?.energy_level && <p className="energy-line">{energyLabel(plan.energy_level)}</p>}

      {dataStatus === "loading" ? (
        <EmptyState text="Собираю план дня..." />
      ) : dataStatus === "error" && !plan ? (
        <EmptyState text="План сейчас недоступен. Попробуй обновить страницу чуть позже." />
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
                pending={pendingTaskIds.has(task.id)}
                onStatusChange={onStatusChange}
              />
            );
          })}
          {doneToday.map((task) => (
            <TaskRow
              key={`done-${task.id}`}
              task={task}
              time={null}
              pending={pendingTaskIds.has(task.id)}
              onStatusChange={onStatusChange}
            />
          ))}
        </ul>
      ) : (
        <EmptyState text="На сегодня пока ничего не запланировано" />
      )}

      {allTodayDone && (
        <p className="completion-note">День закрыт мягко. Можно выдохнуть.</p>
      )}
    </section>
  );
}
