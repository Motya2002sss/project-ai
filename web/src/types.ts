export type MessageSource = "web_text";
export type TaskStatus = "planned" | "done";
export type LoadState = "idle" | "loading" | "ready" | "error";

export type Task = {
  id: number;
  title: string;
  priority: string;
  estimated_minutes: number | null;
  target_date: string;
  status: TaskStatus;
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
};

export type Plan = {
  id: number;
  date: string;
  summary: string | null;
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
  reply_text: string;
  summary: string | null;
  affected_tasks: Task[];
  affected_goals: Goal[];
  plan_summary: Plan | null;
};

export type TodayData = {
  plan: Plan;
  tasks: Task[];
  goals: Goal[];
};
