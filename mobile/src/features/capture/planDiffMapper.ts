import type { DaySnapshotDto, PlanDiffDto } from '../../api/types';

export interface PlanDiffLine {
  title: string;
  detail: string | null;
}

function shortTime(value: string): string {
  return value.slice(0, 5);
}

function taskCountLabel(count: number): string {
  const modulo100 = count % 100;
  const modulo10 = count % 10;
  const noun =
    modulo100 >= 11 && modulo100 <= 14
      ? 'задач'
      : modulo10 === 1
        ? 'задача'
        : modulo10 >= 2 && modulo10 <= 4
          ? 'задачи'
          : 'задач';
  return `${count} ${noun}`;
}

export function mapPlanDiff(
  diff: PlanDiffDto,
  snapshot: DaySnapshotDto,
): PlanDiffLine[] {
  const lines: PlanDiffLine[] = [];
  const taskTitles = new Map(snapshot.tasks.map((task) => [task.id, task.title]));
  const routineTitles = new Map(
    snapshot.routines.map((routine) => [routine.id, routine.title]),
  );

  if (diff.availability_change) {
    lines.push({ title: diff.availability_change, detail: null });
  }

  for (const moved of diff.moved_plan_items ?? []) {
    lines.push({
      title: moved.title,
      detail: `${shortTime(moved.old_start)} → ${shortTime(moved.new_start)}`,
    });
  }

  const appendTasks = (ids: number[] | undefined, title: string) => {
    let unresolvedCount = 0;
    for (const id of ids ?? []) {
      const taskTitle = taskTitles.get(id);
      if (taskTitle) lines.push({ title, detail: taskTitle });
      else unresolvedCount += 1;
    }
    if (unresolvedCount > 0) {
      lines.push({ title, detail: taskCountLabel(unresolvedCount) });
    }
  };

  appendTasks(diff.created_task_ids, 'Добавлено');
  appendTasks(diff.updated_task_ids, 'Обновлено');
  appendTasks(diff.completed_task_ids, 'Выполнено');
  appendTasks(diff.cancelled_task_ids, 'Отменено');
  appendTasks(diff.unscheduled_task_ids, 'Без времени');

  for (const id of diff.created_routine_ids ?? []) {
    const title = routineTitles.get(id);
    if (title) lines.push({ title: 'Добавлено в распорядок', detail: title });
  }

  return lines;
}
