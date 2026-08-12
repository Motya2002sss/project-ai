import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from 'react';

import { ApiClient } from '../../api/client';
import { ApiError } from '../../api/errors';
import { PathApi } from '../../api/pathApi';
import { apiBaseUrl } from '../../config/environment';
import { useAuth } from '../auth/AuthProvider';
import type { AuthStatus } from '../auth/authReducer';
import { PathCache } from './pathCache';
import {
  goalDetailsDataReducer,
  goalDetailsStateForScope,
  initialGoalDetailsDataState,
  initialPathDataState,
  pathDataReducer,
  pathDataStateForScope,
  resolvePathCacheScope,
} from './pathDataState';

function usePathSession() {
  const { getAccessToken, recoverAuthentication } = useAuth();
  const accessTokenRef = useRef(getAccessToken);
  const recoveryRef = useRef(recoverAuthentication);
  accessTokenRef.current = getAccessToken;
  recoveryRef.current = recoverAuthentication;

  const api = useMemo(
    () =>
      new PathApi(
        new ApiClient({
          baseUrl: apiBaseUrl,
          tokenProvider: () => accessTokenRef.current(),
        }),
      ),
    [],
  );

  const request = useCallback(
    async <T,>(operation: (pathApi: PathApi) => Promise<T>): Promise<T> => {
      try {
        return await operation(api);
      } catch (error) {
        if (!(error instanceof ApiError) || error.kind !== 'authentication') {
          throw error;
        }
        const recovered = await recoveryRef.current();
        if (!recovered) throw error;
        return operation(api);
      }
    },
    [api],
  );

  return request;
}

export function usePathData() {
  const { state: authState } = useAuth();
  const publicUserId = authState.user?.publicId ?? null;
  const cacheScope = usePathCacheScope(authState.status, publicUserId);
  const authMode = publicUserId ? 'authenticated' : authState.status;
  const offlineAuthError = publicUserId ? null : authState.error;
  const request = usePathSession();
  const cache = useMemo(
    () => (cacheScope ? new PathCache(AsyncStorage, cacheScope) : null),
    [cacheScope],
  );
  const [state, dispatch] = useReducer(pathDataReducer, initialPathDataState);
  const visibleState = pathDataStateForScope(state, cacheScope);
  const requestGate = useRef(0);

  const refresh = useCallback(async () => {
    if (!cache || !publicUserId) return;
    const requestId = ++requestGate.current;
    dispatch({ type: 'refresh/started' });
    try {
      const response = await request((api) => api.getPath());
      if (requestGate.current !== requestId) return;
      dispatch({ type: 'refresh/succeeded', response });
      void cache.save(response).catch(() => undefined);
    } catch (error) {
      if (requestGate.current !== requestId) return;
      dispatch({
        type: 'refresh/failed',
        message: pathErrorMessage(error),
      });
    }
  }, [cache, publicUserId, request]);

  useEffect(() => {
    const scopeRequestId = ++requestGate.current;
    dispatch({ type: 'scope/changed', scope: cacheScope });
    if (!cache) return;

    void cache
      .load()
      .catch(() => null)
      .then((response) => {
        if (requestGate.current !== scopeRequestId) return;
        dispatch({ type: 'cache/loaded', response });
        if (publicUserId) {
          void refresh();
        } else if (authMode !== 'hydrating' && authMode !== 'refreshing') {
          dispatch({
            type: 'refresh/failed',
            message: offlineAuthError ?? 'Не удалось проверить сессию.',
          });
        }
      });

    return () => {
      requestGate.current += 1;
    };
  }, [authMode, cache, cacheScope, offlineAuthError, publicUserId, refresh]);

  useEffect(() => {
    if (
      publicUserId ||
      authState.status === 'hydrating' ||
      authState.status === 'refreshing'
    ) {
      return;
    }
    dispatch({
      type: 'refresh/failed',
      message: 'Войдите в аккаунт, чтобы открыть путь.',
    });
  }, [authState.status, publicUserId]);

  return { state: visibleState, refresh, canRefresh: Boolean(publicUserId) };
}

export function useGoalDetailsData(publicId: string | null) {
  const { state: authState } = useAuth();
  const publicUserId = authState.user?.publicId ?? null;
  const cacheScope = usePathCacheScope(authState.status, publicUserId);
  const authMode = publicUserId ? 'authenticated' : authState.status;
  const offlineAuthError = publicUserId ? null : authState.error;
  const request = usePathSession();
  const cache = useMemo(
    () => (cacheScope ? new PathCache(AsyncStorage, cacheScope) : null),
    [cacheScope],
  );
  const [state, dispatch] = useReducer(
    goalDetailsDataReducer,
    initialGoalDetailsDataState,
  );
  const visibleState = goalDetailsStateForScope(state, cacheScope);
  const requestGate = useRef(0);
  const evidenceGate = useRef(0);
  const loadingMore = useRef(false);

  const refresh = useCallback(async () => {
    if (!cache || !publicUserId || !publicId) return;
    const requestId = ++requestGate.current;
    evidenceGate.current += 1;
    loadingMore.current = false;
    dispatch({ type: 'refresh/started' });
    dispatch({ type: 'evidence/started', mode: 'replace' });

    const [detailResult, evidenceResult] = await Promise.allSettled([
      request((api) => api.getGoal(publicId)),
      request((api) => api.getEvidence(publicId)),
    ]);
    if (requestGate.current !== requestId) return;

    const detailUnavailable =
      detailResult.status === 'rejected' &&
      detailResult.reason instanceof ApiError &&
      detailResult.reason.kind === 'not_found';
    if (detailResult.status === 'fulfilled') {
      dispatch({ type: 'detail/succeeded', detail: detailResult.value });
    } else if (detailUnavailable) {
      dispatch({
        type: 'detail/unavailable',
        message: 'Цель больше недоступна.',
      });
      void cache.removeGoal(publicId).catch(() => undefined);
    } else {
      dispatch({
        type: 'detail/failed',
        message: goalErrorMessage(detailResult.reason),
      });
    }

    if (detailUnavailable) return;
    if (evidenceResult.status === 'fulfilled') {
      dispatch({
        type: 'evidence/succeeded',
        mode: 'replace',
        items: evidenceResult.value.items,
        nextCursor: evidenceResult.value.next_cursor,
      });
    } else {
      dispatch({
        type: 'evidence/failed',
        message: 'Не удалось обновить историю подтверждений.',
      });
    }
  }, [cache, publicId, publicUserId, request]);

  const loadMoreEvidence = useCallback(async () => {
    const cursor = visibleState.nextCursor;
    if (!publicId || !cursor || loadingMore.current) return;
    loadingMore.current = true;
    const pageId = ++evidenceGate.current;
    dispatch({ type: 'evidence/started', mode: 'append' });
    try {
      const page = await request((api) =>
        api.getEvidence(publicId, { cursor }),
      );
      if (evidenceGate.current !== pageId) return;
      dispatch({
        type: 'evidence/succeeded',
        mode: 'append',
        items: page.items,
        nextCursor: page.next_cursor,
      });
    } catch {
      if (evidenceGate.current !== pageId) return;
      dispatch({
        type: 'evidence/failed',
        message: 'Не удалось загрузить следующую часть истории.',
      });
    } finally {
      if (evidenceGate.current === pageId) loadingMore.current = false;
    }
  }, [publicId, request, visibleState.nextCursor]);

  useEffect(() => {
    const scopeRequestId = ++requestGate.current;
    evidenceGate.current += 1;
    loadingMore.current = false;
    dispatch({ type: 'scope/changed', scope: cacheScope });
    if (!cache || !publicId) return;

    void cache
      .load()
      .catch(() => null)
      .then((response) => {
        if (requestGate.current !== scopeRequestId) return;
        const detail =
          response?.goals.find((item) => item.goal.public_id === publicId) ??
          null;
        dispatch({ type: 'cache/loaded', detail });
        if (publicUserId) {
          void refresh();
        } else if (authMode !== 'hydrating' && authMode !== 'refreshing') {
          dispatch({
            type: 'detail/failed',
            message: offlineAuthError ?? 'Не удалось проверить сессию.',
          });
        }
      });

    return () => {
      requestGate.current += 1;
      evidenceGate.current += 1;
      loadingMore.current = false;
    };
  }, [
    authMode,
    cache,
    cacheScope,
    offlineAuthError,
    publicId,
    publicUserId,
    refresh,
  ]);

  useEffect(() => {
    if (publicId) return;
    dispatch({ type: 'detail/failed', message: 'Цель не найдена.' });
  }, [publicId]);

  useEffect(() => {
    if (
      publicUserId ||
      authState.status === 'hydrating' ||
      authState.status === 'refreshing'
    ) {
      return;
    }
    dispatch({
      type: 'detail/failed',
      message: 'Войдите в аккаунт, чтобы открыть цель.',
    });
  }, [authState.status, publicUserId]);

  return {
    state: visibleState,
    refresh,
    loadMoreEvidence,
    canRefresh: Boolean(publicUserId && publicId),
  };
}

function pathErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось загрузить путь.';
  if (error.kind === 'network') return 'Нет соединения.';
  if (error.kind === 'timeout') return 'Сервер не ответил вовремя.';
  if (error.kind === 'authentication' || error.kind === 'configuration') {
    return 'Сессия недоступна. Войдите снова.';
  }
  return 'Не удалось загрузить путь.';
}

function goalErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.kind === 'not_found') {
    return 'Цель больше недоступна.';
  }
  return pathErrorMessage(error).replace('путь', 'цель');
}

function usePathCacheScope(
  authStatus: AuthStatus,
  authenticatedPublicUserId: string | null,
): string | null {
  return resolvePathCacheScope(authStatus, authenticatedPublicUserId);
}
