import { describe, expect, it } from 'vitest';

import { buildProfileRows } from '../profileModel';

const connectedState = {
  apiConfigured: true,
  hasAuthoritativeToday: true,
  hasTodayError: false,
};

describe('buildProfileRows', () => {
  it('keeps unavailable P1 profile rows non-actionable', () => {
    const rows = buildProfileRows(connectedState);

    expect(rows.find((row) => row.id === 'routine')?.destination).toBeNull();
    expect(
      rows.find((row) => row.id === 'notifications')?.destination,
    ).toBeNull();
  });

  it('exposes only the real Path and backend access destinations', () => {
    const rows = buildProfileRows(connectedState);

    expect(
      rows
        .filter((row) => row.destination !== null)
        .map((row) => row.destination),
    ).toEqual(['/path', '/setup']);
  });

  it('describes a healthy connection without development terminology', () => {
    const rows = buildProfileRows(connectedState);

    expect(rows.find((row) => row.id === 'access')?.detail).toBe(
      'Подключение настроено',
    );
  });

  it('does not claim backend connection while Today has an error', () => {
    const rows = buildProfileRows({
      apiConfigured: true,
      hasAuthoritativeToday: true,
      hasTodayError: true,
    });

    expect(rows.find((row) => row.id === 'access')?.detail).toBe(
      'Проверить подключение',
    );
  });
});
