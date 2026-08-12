import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { CalendarApi } from '../../api/calendarApi';
import { ApiClient } from '../../api/client';
import { ApiError } from '../../api/errors';
import { apiBaseUrl } from '../../config/environment';
import { useAuth } from '../auth/AuthProvider';
import { CalendarCache } from './calendarCache';
import { mondayForDate, monthForDate } from './calendarModel';
import type { CalendarCacheSnapshot } from './calendarTypes';

interface CalendarDataState extends CalendarCacheSnapshot {
  status: 'loading' | 'ready' | 'error';
  source: 'cache' | 'network' | null;
  errorMessage: string | null;
}

const empty: CalendarDataState = {
  day: null, week: null, month: null,
  status: 'loading', source: null, errorMessage: null,
};

export function useCalendarData(selectedDate: string) {
  const { state: authState, getAccessToken, recoverAuthentication } = useAuth();
  const publicUserId = authState.user?.publicId ?? null;
  const tokenRef = useRef(getAccessToken);
  const recoveryRef = useRef(recoverAuthentication);
  tokenRef.current = getAccessToken;
  recoveryRef.current = recoverAuthentication;
  const api = useMemo(
    () => new CalendarApi(new ApiClient({
      baseUrl: apiBaseUrl,
      tokenProvider: () => tokenRef.current(),
      recoverAuthentication: () => recoveryRef.current(),
    })),
    [],
  );
  const cache = useMemo(
    () => publicUserId ? new CalendarCache(AsyncStorage, publicUserId) : null,
    [publicUserId],
  );
  const [state, setState] = useState<CalendarDataState>(empty);
  const gate = useRef(0);

  const refresh = useCallback(async () => {
    if (!cache || !publicUserId) return;
    const request = ++gate.current;
    setState((value) => ({ ...value, status: 'loading', errorMessage: null }));
    try {
      const [day, week, month] = await Promise.all([
        api.getDay(selectedDate),
        api.getWeek(mondayForDate(selectedDate)),
        api.getMonth(monthForDate(selectedDate)),
      ]);
      if (gate.current !== request) return;
      const snapshot = { day, week, month };
      setState({ ...snapshot, status: 'ready', source: 'network', errorMessage: null });
      void cache.save(snapshot).catch(() => undefined);
    } catch (error) {
      if (gate.current !== request) return;
      setState((value) => ({ ...value, status: 'error', errorMessage: calendarError(error) }));
    }
  }, [api, cache, publicUserId, selectedDate]);

  useEffect(() => {
    const request = ++gate.current;
    setState(empty);
    if (!cache) {
      if (authState.status !== 'hydrating' && authState.status !== 'refreshing') {
        setState({ ...empty, status: 'error', errorMessage: 'Войдите в аккаунт, чтобы открыть календарь.' });
      }
      return;
    }
    void cache.load().catch(() => null).then((snapshot) => {
      if (gate.current !== request) return;
      if (snapshot) setState({ ...snapshot, status: 'loading', source: 'cache', errorMessage: null });
      void refresh();
    });
    return () => { gate.current += 1; };
  }, [authState.status, cache, refresh]);

  return { state, refresh, canRefresh: Boolean(publicUserId) };
}

function calendarError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось обновить календарь.';
  if (error.kind === 'network') return 'Нет соединения.';
  if (error.kind === 'timeout') return 'Сервер не ответил вовремя.';
  if (error.kind === 'authentication' || error.kind === 'configuration') return 'Сессия недоступна. Войдите снова.';
  return 'Не удалось обновить календарь.';
}
