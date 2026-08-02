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

export async function getTodayData(userExternalId: string): Promise<TodayData> {
  const encodedUserId = encodeURIComponent(userExternalId);

  // The plan request establishes the temporary MVP user before parallel reads.
  const plan = await requestJson<Plan>(`/api/plan/${encodedUserId}?date=today`);
  const [tasks, goals] = await Promise.all([
    requestJson<Task[]>(`/api/tasks/${encodedUserId}`),
    requestJson<Goal[]>(`/api/goals/${encodedUserId}`)
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
