from math import ceil

from app.models.task import Task


def estimate_task_minutes(task: Task) -> int:
    if task.estimated_minutes:
        return task.estimated_minutes

    if task.fixed_start is not None and task.fixed_end is not None:
        start_seconds = (
            task.fixed_start.hour * 3600
            + task.fixed_start.minute * 60
            + task.fixed_start.second
        )
        end_seconds = (
            task.fixed_end.hour * 3600
            + task.fixed_end.minute * 60
            + task.fixed_end.second
        )
        duration_seconds = end_seconds - start_seconds
        if duration_seconds <= 0:
            duration_seconds += 24 * 3600
        return max(1, ceil(duration_seconds / 60))

    title = task.title.lower()
    if "собес" in title or "подготов" in title:
        return 90
    if "зал" in title or "трен" in title:
        return 60
    if "магаз" in title or "продукт" in title:
        return 30
    return 60
