import * as Crypto from 'expo-crypto';
import * as Haptics from 'expo-haptics';
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import { ApiClient } from '../../api/client';
import {
  ApiError,
  toCapturePresentationError,
  toCompletionPresentationError,
  toTodayPresentationError,
} from '../../api/errors';
import { PlannerApi } from '../../api/plannerApi';
import type { TaskStatus } from '../../api/types';
import {
  apiBaseUrl,
  captureTimeoutMs,
  dogfoodRuntimeEnabled,
  slowCaptureDelayMs,
} from '../../config/environment';
import {
  getDogfoodToken,
  loadCachedSnapshot,
  loadCaptureDraft,
  saveCachedSnapshot,
  saveCaptureDraft,
  saveDogfoodToken,
} from '../../storage/mobileStorage';
import { useAuth } from '../auth/AuthProvider';
import {
  type CaptureOperation,
  initialPlannerState,
  plannerReducer,
  type PlannerState,
  retryDescriptor,
} from './plannerReducer';
import {
  KeyedOperationRegistry,
  LatestRequestGate,
  SerialMutationQueue,
} from './mutationQueue';
import { resolvePlannerAccess } from './plannerAuthPolicy';

interface PlannerContextValue {
  state: PlannerState;
  completionOverrides: Readonly<Record<number, TaskStatus>>;
  apiBaseUrl: string;
  openCapture: () => void;
  closeCapture: () => void;
  setDraft: (value: string) => void;
  submitCapture: () => void;
  respondToInteraction: (
    interactionId: string,
    optionId?: string,
    text?: string,
  ) => void;
  retryCapture: () => void;
  retryCompletion: () => void;
  refreshToday: () => void;
  toggleTaskStatus: (taskId: number, currentStatus: TaskStatus) => void;
  updateDogfoodToken: (token: string) => Promise<void>;
}

const PlannerContext = createContext<PlannerContextValue | null>(null);

export function PlannerProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(plannerReducer, initialPlannerState);
  const {
    state: authState,
    getAccessToken,
    recoverAuthentication,
  } = useAuth();
  const [dogfoodTokenAvailable, setDogfoodTokenAvailable] = useState(false);
  const plannerAccess = resolvePlannerAccess(
    authState.status,
    authState.user?.publicId ?? null,
    dogfoodRuntimeEnabled,
    dogfoodTokenAvailable,
  );
  const cacheScope = plannerAccess.scope;
  const plannerLocked = plannerAccess.kind === 'locked';
  const productionApi = plannerAccess.kind !== 'dogfood';
  const scopedState = useMemo(
    () =>
      state.scope === cacheScope
        ? state
        : { ...initialPlannerState, scope: cacheScope },
    [cacheScope, state],
  );
  const stateRef = useRef(state);
  stateRef.current = scopedState;
  const activeCaptureRef = useRef<string | null>(null);
  const activeTasksRef = useRef(new KeyedOperationRegistry<number>());
  const mutationQueueRef = useRef(new SerialMutationQueue());
  const completionRetryRef = useRef<{
    taskId: number;
    targetStatus: TaskStatus;
    requestId: string;
    expectedPlanVersion: number;
  } | null>(null);
  const todayRequestGateRef = useRef(new LatestRequestGate());
  const authoritativeEpochRef = useRef(0);

  useEffect(() => {
    if (!dogfoodRuntimeEnabled) {
      setDogfoodTokenAvailable(false);
      return;
    }
    let active = true;
    void getDogfoodToken().then((token) => {
      if (active) setDogfoodTokenAvailable(Boolean(token));
    });
    return () => {
      active = false;
    };
  }, []);

  const api = useMemo(
    () =>
      new PlannerApi(
        new ApiClient({
          baseUrl: apiBaseUrl,
          tokenProvider: productionApi ? getAccessToken : getDogfoodToken,
          ...(productionApi ? { recoverAuthentication } : {}),
          timeoutMs: captureTimeoutMs,
        }),
        { apiPrefix: productionApi ? '/api/v2' : '/api/v1' },
      ),
    [getAccessToken, productionApi, recoverAuthentication],
  );

  const refreshToday = useCallback(() => {
    if (plannerLocked || !cacheScope) return;
    const requestScope = cacheScope;
    const requestEpoch = authoritativeEpochRef.current;
    const requestId = todayRequestGateRef.current.begin();
    dispatch({ type: 'today/refreshStarted' });
    void api
      .getToday()
      .then((snapshot) => {
        if (
          requestEpoch !== authoritativeEpochRef.current ||
          !todayRequestGateRef.current.isCurrent(requestId)
        ) {
          return;
        }
        dispatch({ type: 'today/refreshSucceeded', snapshot });
        void mutationQueueRef.current
          .enqueue(() =>
            requestEpoch === authoritativeEpochRef.current &&
              todayRequestGateRef.current.isCurrent(requestId)
              ? saveCachedSnapshot(snapshot, requestScope)
              : Promise.resolve(),
          )
          .catch(() => undefined);
      })
      .catch((error: unknown) => {
        if (
          requestEpoch !== authoritativeEpochRef.current ||
          !todayRequestGateRef.current.isCurrent(requestId)
        ) {
          return;
        }
        const presentation = toTodayPresentationError(
          error,
          Boolean(stateRef.current.today.snapshot),
        );
        dispatch({
          type: 'today/refreshFailed',
          message: presentation.message,
          retryable: presentation.retryable,
        });
      });
  }, [api, cacheScope, plannerLocked]);

  useEffect(() => {
    if (plannerLocked || !cacheScope) {
      activeCaptureRef.current = null;
      activeTasksRef.current = new KeyedOperationRegistry<number>();
      mutationQueueRef.current = new SerialMutationQueue();
      todayRequestGateRef.current.invalidate();
      authoritativeEpochRef.current += 1;
      dispatch({ type: 'scope/changed', scope: null });
      return;
    }
    let mounted = true;
    activeCaptureRef.current = null;
    activeTasksRef.current = new KeyedOperationRegistry<number>();
    mutationQueueRef.current = new SerialMutationQueue();
    todayRequestGateRef.current.invalidate();
    authoritativeEpochRef.current += 1;
    dispatch({ type: 'scope/changed', scope: cacheScope });
    void Promise.all([
      loadCachedSnapshot(cacheScope).catch(() => null),
      loadCaptureDraft(cacheScope).catch(() => ''),
    ]).then(([snapshot, draft]) => {
      if (!mounted) return;
      dispatch({ type: 'today/cacheLoaded', snapshot });
      dispatch({ type: 'draft/hydrated', value: draft });
    });
    refreshToday();
    return () => {
      mounted = false;
    };
  }, [cacheScope, plannerLocked, refreshToday]);

  useEffect(() => {
    if (!cacheScope || plannerLocked || !scopedState.draftHydrated) return;
    void saveCaptureDraft(scopedState.draft, cacheScope).catch(() => undefined);
  }, [cacheScope, plannerLocked, scopedState.draft, scopedState.draftHydrated]);

  const sendOperation = useCallback(
    (
      operation: CaptureOperation,
      requestId: string,
      explicitCancel = false,
    ) => {
      if (plannerLocked || !cacheScope || activeCaptureRef.current) return;
      const operationScope = cacheScope;
      activeCaptureRef.current = requestId;
      authoritativeEpochRef.current += 1;
      dispatch({ type: 'capture/requestStarted', requestId, operation });

      const slowTimer = setTimeout(() => {
        dispatch({ type: 'capture/requestSlow', requestId });
      }, slowCaptureDelayMs);

      void mutationQueueRef.current.enqueue(async () => {
        try {
          const response = await (operation.kind === 'capture'
            ? api.capture({ request_id: requestId, text: operation.text })
            : api.respondToInteraction(operation.interactionId, {
                request_id: requestId,
                text: operation.text,
                ...(operation.optionId ? { option_id: operation.optionId } : {}),
              }));
          if (activeCaptureRef.current !== requestId) return;
          if (response.request_id !== requestId) {
            throw new ApiError('invalid_response', true);
          }
          clearTimeout(slowTimer);
          authoritativeEpochRef.current += 1;
          dispatch({
            type: 'capture/responseReceived',
            requestId,
            response,
            explicitCancel,
          });
          activeCaptureRef.current = null;
          await saveCachedSnapshot(response.day_snapshot, operationScope).catch(
            () => undefined,
          );
        } catch (error: unknown) {
          if (activeCaptureRef.current !== requestId) return;
          const presentation = toCapturePresentationError(error);
          dispatch({
            type: 'capture/requestFailed',
            requestId,
            message: presentation.message,
            retryable: presentation.retryable,
          });
        } finally {
          clearTimeout(slowTimer);
          if (activeCaptureRef.current === requestId) {
            activeCaptureRef.current = null;
          }
        }
      });
    },
    [api, cacheScope, plannerLocked],
  );

  const submitCapture = useCallback(() => {
    const text = stateRef.current.draft.trim();
    if (!text) return;
    sendOperation({ kind: 'capture', text }, Crypto.randomUUID());
  }, [sendOperation]);

  const respondToInteraction = useCallback(
    (interactionId: string, optionId?: string, text = '') => {
      if (!optionId && !text.trim()) return;
      const operation: CaptureOperation = {
        kind: 'interaction',
        interactionId,
        text: text.trim(),
        ...(optionId ? { optionId } : {}),
      };
      sendOperation(operation, Crypto.randomUUID(), optionId === 'cancel');
    },
    [sendOperation],
  );

  const retryCapture = useCallback(() => {
    const retry = retryDescriptor(stateRef.current.capture);
    if (!retry) return;
    sendOperation(
      retry.operation,
      retry.requestId,
      retry.explicitCancel,
    );
  }, [sendOperation]);

  const requestTaskStatus = useCallback(
    (
      taskId: number,
      targetStatus: TaskStatus,
      retry?: { requestId: string; expectedPlanVersion: number },
    ) => {
      if (plannerLocked || !cacheScope) return;
      const expectedPlanVersion =
        retry?.expectedPlanVersion ??
        stateRef.current.today.snapshot?.plan_version;
      if (expectedPlanVersion === undefined) return;
      const operationScope = cacheScope;
      const operationId = retry?.requestId ?? Crypto.randomUUID();
      if (!activeTasksRef.current.start(taskId, operationId)) return;
      authoritativeEpochRef.current += 1;
      dispatch({
        type: 'task/requestStarted',
        taskId,
        operationId,
        targetStatus,
      });

      void mutationQueueRef.current.enqueue(async () => {
        try {
          const response = await api.setTaskStatus(taskId, targetStatus, {
            requestId: operationId,
            expectedPlanVersion,
          });
          if (!activeTasksRef.current.isActive(taskId, operationId)) return;
          if (completionRetryRef.current?.requestId === operationId) {
            completionRetryRef.current = null;
          }
          authoritativeEpochRef.current += 1;
          dispatch({
            type: 'task/requestSucceeded',
            taskId,
            operationId,
            snapshot: response.day_snapshot,
          });
          activeTasksRef.current.finish(taskId, operationId);
          void Haptics.notificationAsync(
            Haptics.NotificationFeedbackType.Success,
          ).catch(() => undefined);
          await saveCachedSnapshot(response.day_snapshot, operationScope).catch(
            () => undefined,
          );
        } catch (error: unknown) {
          if (!activeTasksRef.current.isActive(taskId, operationId)) return;
          const presentation = toCompletionPresentationError(error);
          completionRetryRef.current = {
            taskId,
            targetStatus,
            requestId: operationId,
            expectedPlanVersion,
          };
          dispatch({
            type: 'task/requestFailed',
            taskId,
            operationId,
            message: presentation.message,
            retryable: presentation.retryable,
          });
        } finally {
          activeTasksRef.current.finish(taskId, operationId);
        }
      });
    },
    [api, cacheScope, plannerLocked],
  );

  const toggleTaskStatus = useCallback(
    (taskId: number, currentStatus: TaskStatus) => {
      requestTaskStatus(
        taskId,
        currentStatus === 'done' ? 'planned' : 'done',
      );
    },
    [requestTaskStatus],
  );

  const retryCompletion = useCallback(() => {
    const failed = stateRef.current.completion.error;
    const retry = completionRetryRef.current;
    if (!failed?.retryable || !retry) return;
    requestTaskStatus(retry.taskId, retry.targetStatus, retry);
  }, [requestTaskStatus]);

  const completionOverrides = useMemo(() => {
    const overrides: Record<number, TaskStatus> = {};
    for (const [taskId, pending] of Object.entries(
      scopedState.completion.pendingByTask,
    )) {
      overrides[Number(taskId)] = pending.targetStatus;
    }
    return overrides;
  }, [scopedState.completion.pendingByTask]);

  const value = useMemo<PlannerContextValue>(
    () => ({
      state: scopedState,
      completionOverrides,
      apiBaseUrl,
      openCapture: () => dispatch({ type: 'capture/opened' }),
      closeCapture: () => dispatch({ type: 'capture/closed' }),
      setDraft: (draft) => dispatch({ type: 'draft/changed', value: draft }),
      submitCapture,
      respondToInteraction,
      retryCapture,
      retryCompletion,
      refreshToday,
      toggleTaskStatus,
      updateDogfoodToken: async (token) => {
        if (!dogfoodRuntimeEnabled) {
          throw new Error('Dogfood access is disabled');
        }
        todayRequestGateRef.current.invalidate();
        try {
          await saveDogfoodToken(token);
        } catch (error) {
          throw error;
        }
        const available = Boolean(token.trim());
        setDogfoodTokenAvailable(available);
        if (available && !plannerLocked) refreshToday();
      },
    }),
    [
      completionOverrides,
      plannerLocked,
      refreshToday,
      respondToInteraction,
      retryCapture,
      retryCompletion,
      scopedState,
      submitCapture,
      toggleTaskStatus,
    ],
  );

  return (
    <PlannerContext.Provider value={value}>{children}</PlannerContext.Provider>
  );
}

export function usePlanner(): PlannerContextValue {
  const value = useContext(PlannerContext);
  if (!value) throw new Error('usePlanner must be used inside PlannerProvider');
  return value;
}
