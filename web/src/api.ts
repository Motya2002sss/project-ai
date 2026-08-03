import type { Goal, MessageResponse, Plan, Task, TaskStatus, TodayData } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function checkHealth(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/health");
}

export function getTodayPlan(userExternalId: string): Promise<Plan> {
  const encodedUserId = encodeURIComponent(userExternalId);
  return requestJson<Plan>(`/api/plan/${encodedUserId}?date=today`);
}

export function getTodayTasks(userExternalId: string): Promise<Task[]> {
  const encodedUserId = encodeURIComponent(userExternalId);
  return requestJson<Task[]>(`/api/tasks/${encodedUserId}?date=today`);
}

export function getGoals(userExternalId: string): Promise<Goal[]> {
  const encodedUserId = encodeURIComponent(userExternalId);
  return requestJson<Goal[]>(`/api/goals/${encodedUserId}`);
}

export async function getTodayData(userExternalId: string): Promise<TodayData> {
  const plan = await getTodayPlan(userExternalId);
  const [tasks, goals] = await Promise.all([
    getTodayTasks(userExternalId),
    getGoals(userExternalId)
  ]);

  return { plan, tasks, goals };
}

export function processMessage(userExternalId: string, text: string): Promise<MessageResponse> {
  return requestJson<MessageResponse>("/api/message", {
    method: "POST",
    body: JSON.stringify({
      user_external_id: userExternalId,
      source: "web_text",
      text
    })
  });
}

export function setTaskStatus(
  userExternalId: string,
  taskId: number,
  status: TaskStatus
): Promise<Task> {
  return requestJson<Task>(`/api/tasks/${taskId}/status`, {
    method: "PATCH",
    body: JSON.stringify({
      user_external_id: userExternalId,
      status
    })
  });
}
