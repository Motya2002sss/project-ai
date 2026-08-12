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

interface PlannerApiOptions {
  apiPrefix?: '/api/v1' | '/api/v2';
}

export class PlannerApi {
  private readonly apiPrefix: '/api/v1' | '/api/v2';

  constructor(
    private readonly client: JsonRequester,
    options: PlannerApiOptions = {},
  ) {
    this.apiPrefix = options.apiPrefix ?? '/api/v1';
  }

  getToday(): Promise<DaySnapshotDto> {
    return this.client.request<DaySnapshotDto>(
      `${this.apiPrefix}/today`,
      undefined,
      isDaySnapshotDto,
    );
  }

  capture(request: CaptureRequestDto): Promise<MobileActionResponseDto> {
    return this.client.request<MobileActionResponseDto>(
      `${this.apiPrefix}/capture`,
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
      `${this.apiPrefix}/interactions/${encodeURIComponent(interactionId)}/responses`,
      { method: 'POST', body: JSON.stringify(request) },
      isMobileActionResponseDto,
    );
  }

  setTaskStatus(
    taskId: number,
    status: TaskStatus,
    mutation?: { requestId: string; expectedPlanVersion: number },
  ): Promise<MobileTaskMutationResponseDto> {
    if (this.apiPrefix === '/api/v2' && !mutation) {
      throw new Error('Versioned task mutation metadata is required');
    }
    const body =
      this.apiPrefix === '/api/v2'
        ? {
            status,
            request_id: mutation!.requestId,
            expected_plan_version: mutation!.expectedPlanVersion,
          }
        : { status };
    return this.client.request<MobileTaskMutationResponseDto>(
      `${this.apiPrefix}/tasks/${taskId}/status`,
      { method: 'PATCH', body: JSON.stringify(body) },
      isMobileTaskMutationResponseDto,
    );
  }
}
