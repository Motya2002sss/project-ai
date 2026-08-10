import type {
  CaptureRequestDto,
  DaySnapshotDto,
  InteractionResponseRequestDto,
  MobileActionResponseDto,
  MobileTaskMutationResponseDto,
  TaskStatus,
} from './types';
import type { RuntimeValidator } from './validation';
import {
  isDaySnapshotDto,
  isMobileActionResponseDto,
  isMobileTaskMutationResponseDto,
} from './validation';

export interface JsonRequester {
  request<T>(
    path: string,
    init?: RequestInit,
    validator?: RuntimeValidator<T>,
  ): Promise<T>;
}

export class PlannerApi {
  constructor(private readonly client: JsonRequester) {}

  getToday(): Promise<DaySnapshotDto> {
    return this.client.request<DaySnapshotDto>(
      '/api/v1/today',
      undefined,
      isDaySnapshotDto,
    );
  }

  capture(request: CaptureRequestDto): Promise<MobileActionResponseDto> {
    return this.client.request<MobileActionResponseDto>(
      '/api/v1/capture',
      {
        method: 'POST',
        body: JSON.stringify(request),
      },
      isMobileActionResponseDto,
    );
  }

  respondToInteraction(
    interactionId: string,
    request: InteractionResponseRequestDto,
  ): Promise<MobileActionResponseDto> {
    return this.client.request<MobileActionResponseDto>(
      `/api/v1/interactions/${encodeURIComponent(interactionId)}/responses`,
      { method: 'POST', body: JSON.stringify(request) },
      isMobileActionResponseDto,
    );
  }

  setTaskStatus(
    taskId: number,
    status: TaskStatus,
  ): Promise<MobileTaskMutationResponseDto> {
    return this.client.request<MobileTaskMutationResponseDto>(
      `/api/v1/tasks/${taskId}/status`,
      { method: 'PATCH', body: JSON.stringify({ status }) },
      isMobileTaskMutationResponseDto,
    );
  }
}
