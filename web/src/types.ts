export type MessageSource = "web_text";
export type TaskStatus = "planned" | "done";
export type StoredTaskStatus = TaskStatus | "cancelled";
export type LoadState = "idle" | "loading" | "ready" | "error";

export type Task = {
  id: number;
  title: string;
  priority: string;
  estimated_minutes: number | null;
  target_date: string;
  scheduling_type: "fixed" | "flexible" | "unscheduled";
  fixed_start: string | null;
  fixed_end: string | null;
  preferred_window: string | null;
  earliest_start: string | null;
  latest_end: string | null;
  deadline: string | null;
  is_locked: boolean;
  status: StoredTaskStatus;
};

export type Goal = {
  id: number;
  title: string;
  category: string;
  priority: string;
  status: string;
};

export type PlanItem = {
  id: number;
  task_id: number | null;
  title: string;
  item_type: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
  unscheduled_reason: string | null;
};

export type Plan = {
  id: number;
  date: string;
  summary: string | null;
  focus_text: string;
  energy_level: string | null;
  budget_limit: number | null;
  status: string;
  items: PlanItem[];
};

export type MessageResponse = {
  user_external_id: string;
  source: MessageSource;
  intent: string;
  parsed: Record<string, unknown>;
  status: "applied" | "needs_clarification" | "conflict";
  needs_clarification: boolean;
  clarification_question: string | null;
  reply_text: string;
  summary: string | null;
  affected_tasks: Task[];
  affected_goals: Goal[];
  plan_summary: Plan | null;
  plan_diff: PlanDiff;
};

export type MovedPlanItem = {
  task_id: number;
  title: string;
  old_start: string;
  new_start: string;
};

export type PlanDiff = {
  created_task_ids: number[];
  updated_task_ids: number[];
  completed_task_ids: number[];
  cancelled_task_ids: number[];
  moved_plan_items: MovedPlanItem[];
  unscheduled_task_ids: number[];
  conflict: string | null;
  clarification: string | null;
};

export type TodayData = {
  plan: Plan;
  tasks: Task[];
  goals: Goal[];
};

export type TaskPlacement = {
  taskId: number;
  startTime: string | null;
  endTime: string | null;
  planStatus: string;
  unscheduledReason: string | null;
};

export type TaskStatusError = {
  retryStatus: TaskStatus;
};

export type PlanChange = {
  kind: "added" | "moved" | "completed" | "cancelled" | "restored" | "unscheduled";
  title: string;
  detail: string | null;
};

export type PlanUpdate = {
  title: string;
  message: string | null;
  changes: PlanChange[];
};
