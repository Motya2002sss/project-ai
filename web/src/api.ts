import type { DaySnapshot, MessageResponse, MessageSubmission, Task, TaskStatus } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const MESSAGE_TIMEOUT_MS = 15_000;

async function requestJson<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = MESSAGE_TIMEOUT_MS
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = options?.signal;
  const abortFromExternal = () => controller.abort();
  externalSignal?.addEventListener("abort", abortFromExternal, { once: true });

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...options?.headers
      },
      ...options,
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }

    return response.json() as Promise<T>;
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}

export function checkHealth(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/health");
}

export function getTodayData(userExternalId: string): Promise<DaySnapshot> {
  const encodedUserId = encodeURIComponent(userExternalId);
  return requestJson<DaySnapshot>(`/api/day/${encodedUserId}?date=today`);
}

export function processMessage(
  userExternalId: string,
  submission: MessageSubmission,
  signal?: AbortSignal
): Promise<MessageResponse> {
  return requestJson<MessageResponse>("/api/message", {
    method: "POST",
    signal,
    body: JSON.stringify({
      user_external_id: userExternalId,
      source: "web_text",
      text: submission.text,
      request_id: submission.requestId,
      interaction_id: submission.interactionId || undefined,
      option_id: submission.optionId || undefined
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
