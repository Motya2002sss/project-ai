import type {
  ClarificationDto,
  ConfirmationDto,
  ConflictDto,
  DaySnapshotDto,
  MobileActionResponseDto,
  PlanDiffDto,
  TaskStatus,
} from '../../api/types';

export type CaptureOperation =
  | { kind: 'capture'; text: string }
  | {
      kind: 'interaction';
      interactionId: string;
      text: string;
      optionId?: string;
    };

export type InteractionCaptureState =
  | { status: 'clarification'; value: ClarificationDto }
  | { status: 'confirmation'; value: ConfirmationDto }
  | { status: 'conflict'; value: ConflictDto };

export type CaptureState =
  | { status: 'idle' }
  | { status: 'editing' }
  | {
      status: 'submitting';
      requestId: string;
      operation: CaptureOperation;
      slow: boolean;
      interaction?: InteractionCaptureState;
    }
  | InteractionCaptureState
  | {
      status: 'success';
      planDiff: PlanDiffDto;
      replyText: string;
      didChange: boolean;
    }
  | {
      status: 'error';
      message: string;
      retryable: boolean;
      requestId?: string;
      operation?: CaptureOperation;
      interaction?: InteractionCaptureState;
    };

export interface PlannerState {
  today: {
    snapshot: DaySnapshotDto | null;
    source: 'none' | 'cache' | 'server';
    refreshing: boolean;
    error: { message: string; retryable: boolean } | null;
  };
  draft: string;
  draftHydrated: boolean;
  capture: CaptureState;
  completion: {
    pendingByTask: Record<
      number,
      { operationId: string; targetStatus: TaskStatus }
    >;
    error: {
      taskId: number;
      targetStatus: TaskStatus;
      message: string;
      retryable: boolean;
    } | null;
  };
}

export const initialPlannerState: PlannerState = {
  today: {
    snapshot: null,
    source: 'none',
    refreshing: false,
    error: null,
  },
  draft: '',
  draftHydrated: false,
  capture: { status: 'idle' },
  completion: { pendingByTask: {}, error: null },
};

export interface RetryDescriptor {
  requestId: string;
  operation: CaptureOperation;
  explicitCancel: boolean;
}

export function retryDescriptor(capture: CaptureState): RetryDescriptor | null {
  if (
    capture.status !== 'error' ||
    !capture.retryable ||
    !capture.requestId ||
    !capture.operation
  ) {
    return null;
  }
  return {
    requestId: capture.requestId,
    operation: capture.operation,
    explicitCancel:
      capture.operation.kind === 'interaction' &&
      capture.operation.optionId === 'cancel',
  };
}

function captureInteraction(
  capture: CaptureState,
): InteractionCaptureState | undefined {
  if (
    capture.status === 'clarification' ||
    capture.status === 'confirmation' ||
    capture.status === 'conflict'
  ) {
    return capture;
  }
  if (capture.status === 'submitting' || capture.status === 'error') {
    return capture.interaction;
  }
  return undefined;
}

export type PlannerAction =
  | { type: 'draft/hydrated'; value: string }
  | { type: 'draft/changed'; value: string }
  | { type: 'capture/opened' }
  | { type: 'capture/closed' }
  | {
      type: 'capture/requestStarted';
      requestId: string;
      operation: CaptureOperation;
    }
  | { type: 'capture/requestSlow'; requestId: string }
  | {
      type: 'capture/requestFailed';
      requestId: string;
      message: string;
      retryable: boolean;
    }
  | {
      type: 'capture/responseReceived';
      requestId: string;
      response: MobileActionResponseDto;
      explicitCancel: boolean;
    }
  | { type: 'today/cacheLoaded'; snapshot: DaySnapshotDto | null }
  | { type: 'today/refreshStarted' }
  | { type: 'today/refreshSucceeded'; snapshot: DaySnapshotDto }
  | { type: 'today/refreshFailed'; message: string; retryable: boolean }
  | {
      type: 'task/requestStarted';
      taskId: number;
      operationId: string;
      targetStatus: TaskStatus;
    }
  | {
      type: 'task/requestSucceeded';
      taskId: number;
      operationId: string;
      snapshot: DaySnapshotDto;
    }
  | {
      type: 'task/requestFailed';
      taskId: number;
      operationId: string;
      message: string;
      retryable: boolean;
    };

function responseCaptureState(
  response: MobileActionResponseDto,
  submitting: Extract<CaptureState, { status: 'submitting' }>,
): CaptureState {
  if (
    (response.status === 'clarification_required' ||
      response.status === 'needs_clarification') &&
    response.clarification
  ) {
    return { status: 'clarification', value: response.clarification };
  }

  if (response.status === 'confirmation_required' && response.confirmation) {
    return { status: 'confirmation', value: response.confirmation };
  }

  if (response.status === 'conflict' && response.conflict) {
    return { status: 'conflict', value: response.conflict };
  }

  if (
    response.status === 'failed' ||
    response.status === 'unsupported_capability' ||
    response.reason === 'request_in_progress'
  ) {
    return {
      status: 'error',
      message: response.reply_text,
      retryable: response.retryable,
      requestId: submitting.requestId,
      operation: submitting.operation,
      ...(submitting.interaction
        ? { interaction: submitting.interaction }
        : {}),
    };
  }

  return {
    status: 'success',
    planDiff: response.plan_diff,
    replyText: response.reply_text,
    didChange: response.status === 'applied',
  };
}

export function plannerReducer(
  state: PlannerState,
  action: PlannerAction,
): PlannerState {
  switch (action.type) {
    case 'draft/hydrated':
      return { ...state, draft: action.value, draftHydrated: true };
    case 'draft/changed':
      return { ...state, draft: action.value };
    case 'capture/opened':
      if (state.capture.status === 'submitting') return state;
      return { ...state, capture: { status: 'editing' } };
    case 'capture/closed':
      if (state.capture.status === 'submitting') return state;
      return { ...state, capture: { status: 'idle' } };
    case 'capture/requestStarted': {
      if (state.capture.status === 'submitting') return state;
      const interaction = captureInteraction(state.capture);
      return {
        ...state,
        capture: {
          status: 'submitting',
          requestId: action.requestId,
          operation: action.operation,
          slow: false,
          ...(interaction ? { interaction } : {}),
        },
      };
    }
    case 'capture/requestSlow':
      if (
        state.capture.status !== 'submitting' ||
        state.capture.requestId !== action.requestId
      ) {
        return state;
      }
      return { ...state, capture: { ...state.capture, slow: true } };
    case 'capture/requestFailed':
      if (
        state.capture.status !== 'submitting' ||
        state.capture.requestId !== action.requestId
      ) {
        return state;
      }
      return {
        ...state,
        capture: {
          status: 'error',
          message: action.message,
          retryable: action.retryable,
          requestId: state.capture.requestId,
          operation: state.capture.operation,
          ...(state.capture.interaction
            ? { interaction: state.capture.interaction }
            : {}),
        },
      };
    case 'capture/responseReceived': {
      if (
        state.capture.status !== 'submitting' ||
        state.capture.requestId !== action.requestId ||
        action.response.request_id !== action.requestId
      ) {
        return state;
      }

      const shouldClearDraft =
        action.response.status === 'applied' || action.explicitCancel;
      return {
        ...state,
        draft: shouldClearDraft ? '' : state.draft,
        today: {
          snapshot: action.response.day_snapshot,
          source: 'server',
          refreshing: false,
          error: null,
        },
        capture: responseCaptureState(action.response, state.capture),
      };
    }
    case 'today/cacheLoaded':
      if (state.today.snapshot || !action.snapshot) return state;
      return {
        ...state,
        today: {
          ...state.today,
          snapshot: action.snapshot,
          source: 'cache',
        },
      };
    case 'today/refreshStarted':
      return {
        ...state,
        today: { ...state.today, refreshing: true, error: null },
      };
    case 'today/refreshSucceeded':
      return {
        ...state,
        today: {
          snapshot: action.snapshot,
          source: 'server',
          refreshing: false,
          error: null,
        },
      };
    case 'today/refreshFailed':
      return {
        ...state,
        today: {
          ...state.today,
          refreshing: false,
          error: { message: action.message, retryable: action.retryable },
        },
      };
    case 'task/requestStarted':
      if (state.completion.pendingByTask[action.taskId]) return state;
      return {
        ...state,
        completion: {
          pendingByTask: {
            ...state.completion.pendingByTask,
            [action.taskId]: {
              operationId: action.operationId,
              targetStatus: action.targetStatus,
            },
          },
          error: null,
        },
      };
    case 'task/requestSucceeded': {
      const pending = state.completion.pendingByTask[action.taskId];
      if (!pending || pending.operationId !== action.operationId) return state;
      const pendingByTask = { ...state.completion.pendingByTask };
      delete pendingByTask[action.taskId];
      return {
        ...state,
        today: {
          snapshot: action.snapshot,
          source: 'server',
          refreshing: false,
          error: null,
        },
        completion: { pendingByTask, error: null },
      };
    }
    case 'task/requestFailed': {
      const pending = state.completion.pendingByTask[action.taskId];
      if (!pending || pending.operationId !== action.operationId) return state;
      const pendingByTask = { ...state.completion.pendingByTask };
      delete pendingByTask[action.taskId];
      return {
        ...state,
        completion: {
          pendingByTask,
          error: {
            taskId: action.taskId,
            targetStatus: pending.targetStatus,
            message: action.message,
            retryable: action.retryable,
          },
        },
      };
    }
  }
}
