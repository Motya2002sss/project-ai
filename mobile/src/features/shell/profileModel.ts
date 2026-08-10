export type ProfileDestination = '/path' | '/setup';

export interface ProfileRowModel {
  id: 'routine' | 'goals' | 'notifications' | 'access';
  title: string;
  detail: string;
  destination: ProfileDestination | null;
  availability: 'available' | 'later';
}

interface ProfileState {
  apiConfigured: boolean;
  hasAuthoritativeToday: boolean;
  hasTodayError: boolean;
}

function backendAccessDetail(state: ProfileState): string {
  if (!state.apiConfigured) return 'Настроить backend';
  if (state.hasAuthoritativeToday && !state.hasTodayError) {
    return 'Backend подключён';
  }
  return 'Проверить подключение';
}

export function buildProfileRows(state: ProfileState): ProfileRowModel[] {
  return [
    {
      id: 'routine',
      title: 'Мой распорядок',
      detail: 'Рабочее время, сон и привычный ритм',
      destination: null,
      availability: 'later',
    },
    {
      id: 'goals',
      title: 'Цели и планы',
      detail: 'Долгосрочные цели и подтверждённый прогресс',
      destination: '/path',
      availability: 'available',
    },
    {
      id: 'notifications',
      title: 'Уведомления',
      detail: 'Напоминания о планах и изменениях',
      destination: null,
      availability: 'later',
    },
    {
      id: 'access',
      title: 'Данные и доступ',
      detail: backendAccessDetail(state),
      destination: '/setup',
      availability: 'available',
    },
  ];
}
