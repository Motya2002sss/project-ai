import * as Crypto from 'expo-crypto';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { CalendarApi } from '../../api/calendarApi';
import { ApiClient } from '../../api/client';
import { apiBaseUrl } from '../../config/environment';
import { getAppleDeviceMetadata } from '../../integrations/apple/appleAuthAdapter';
import { createExpoCalendarAdapter } from '../../integrations/calendar/expoCalendarAdapter';
import { useAuth } from '../auth/AuthProvider';
import {
  calendarSyncWeekRange,
  CalendarSyncCoordinator,
} from './calendarSyncService';

export function useCalendarSync(selectedDate: string, onSynced: () => void) {
  const { state: authState, getAccessToken, recoverAuthentication } = useAuth();
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
  const coordinator = useRef(new CalendarSyncCoordinator());
  const retryRequestId = useRef<string | null>(null);
  const [state, setState] = useState<{
    status: 'idle' | 'syncing' | 'success' | 'denied' | 'error';
    message: string | null;
  }>({ status: 'idle', message: null });

  useEffect(() => {
    retryRequestId.current = null;
    setState({ status: 'idle', message: null });
  }, [selectedDate]);

  const sync = useCallback(async () => {
    if (!authState.user) {
      setState({ status: 'error', message: 'Войдите в аккаунт, чтобы учесть календарь.' });
      return;
    }
    setState({ status: 'syncing', message: null });
    const requestId = retryRequestId.current ?? Crypto.randomUUID();
    retryRequestId.current = requestId;
    try {
      const [adapter, device] = await Promise.all([
        createExpoCalendarAdapter(),
        getAppleDeviceMetadata(),
      ]);
      const result = await coordinator.current.run({
        adapter,
        transport: api,
        deviceId: device.deviceId,
        timezone: authState.user.timezone,
        requestId,
        range: calendarSyncWeekRange(selectedDate, authState.user.timezone),
      });
      if (result.status === 'permission_denied') {
        retryRequestId.current = null;
        setState({
          status: 'denied',
          message: 'Доступ не предоставлен. План продолжит работать без Apple Calendar.',
        });
        return;
      }
      retryRequestId.current = null;
      setState({
        status: 'success',
        message: result.replanRequired
          ? 'Занятые интервалы учтены. Изменённые дни готовы к перепланированию.'
          : 'Занятые интервалы Apple Calendar учтены.',
      });
      onSynced();
    } catch {
      setState({
        status: 'error',
        message: 'Не удалось синхронизировать. Ничего не отмечено как успешно.',
      });
    }
  }, [api, authState.user, onSynced, selectedDate]);

  return { state, sync };
}
