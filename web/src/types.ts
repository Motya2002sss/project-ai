export type MessageSource = "web_text";
export type TaskStatus = "planned" | "done";
export type StoredTaskStatus = TaskStatus | "cancelled";
export type LoadState = "idle" | "loading" | "ready" | "error";
export type MessageStatus =
  | "applied"
  | "clarification_required"
  | "confirmation_required"
  | "conflict"
  | "no_change"
  | "unsupported_capability"
  | "failed"
  | "needs_clarification";

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
  routine_id: number | null;
  occurrence_date: string | null;
};

export type Goal = {
  id: number;
  title: string;
  category: string;
  priority: string;
  status: string;
};

export type Routine = {
  id: number;
  title: string;
  cadence: "daily" | "weekdays" | "selected_weekdays";
  weekdays: number[];
  fixed_time: string | null;
  preferred_window: string | null;
  estimated_minutes: number | null;
  start_date: string;
  end_date: string | null;
  active: boolean;
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
  version: number;
  items: PlanItem[];
};

export type InteractionOption = {
  id: string;
  label: string;
  value: string;
};

export type Clarification = {
  id: string;
  question: string;
  options: InteractionOption[];
  free_text_allowed: boolean;
  expires_at: string;
};

export type Confirmation = {
  id: string;
  title: string;
  summary: string;
  changes: PlanDiff;
  options: InteractionOption[];
  expires_at: string;
  base_plan_version: number | null;
};

export type ConflictDetails = {
  id: string | null;
  title: string;
  message: string;
  options: InteractionOption[];
  expires_at: string | null;
};

export type DaySnapshot = {
  date: string;
  focus_text: string;
  progress: { done: number; total: number };
  scheduled_items: PlanItem[];
  unscheduled_items: PlanItem[];
  completed_count: number;
  total_count: number;
  day_context: { energy_level: string | null; budget_limit: number | null };
  tasks: Task[];
  goals: Goal[];
  routines: Routine[];
  plan: Plan;
  plan_version: number;
};

export type MessageResponse = {
  request_id: string | null;
  user_external_id: string;
  source: MessageSource;
  intent: string;
  parsed: Record<string, unknown>;
  status: MessageStatus;
  needs_clarification: boolean;
  clarification_question: string | null;
  reply_text: string;
  summary: string | null;
  affected_tasks: Task[];
  affected_goals: Goal[];
  affected_routines: Routine[];
  plan_summary: Plan | null;
  plan_diff: PlanDiff;
  clarification: Clarification | null;
  confirmation: Confirmation | null;
  conflict_details: ConflictDetails | null;
  day_snapshot: DaySnapshot | null;
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
  created_routine_ids: number[];
  conflict: string | null;
  clarification: string | null;
};

export type TodayData = {
  plan: Plan;
  tasks: Task[];
  goals: Goal[];
};

export type MessageSubmission = {
  text: string;
  requestId: string;
  interactionId?: string | null;
  optionId?: string | null;
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
  kind: "added" | "moved" | "completed" | "cancelled" | "restored" | "unscheduled" | "routine";
  title: string;
  detail: string | null;
};

export type PlanUpdate = {
  title: string;
  message: string | null;
  changes: PlanChange[];
};
