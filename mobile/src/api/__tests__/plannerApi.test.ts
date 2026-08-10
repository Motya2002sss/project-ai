import { describe, expect, it } from 'vitest';

import { PlannerApi, type JsonRequester } from '../plannerApi';

describe('PlannerApi mobile v1 boundary', () => {
  it('uses only authenticated mobile routes and contract payloads', async () => {
    const calls: [string, RequestInit?][] = [];
    const client: JsonRequester = {
      async request<T>(path: string, init?: RequestInit): Promise<T> {
        calls.push([path, init]);
        return { ok: true } as T;
      },
    };
    const api = new PlannerApi(client);

    await api.getToday();
    await api.capture({ request_id: 'capture-1', text: 'Изменение' });
    await api.respondToInteraction('interaction/unsafe', {
      request_id: 'answer-1',
      option_id: 'apply',
      text: 'Применить',
    });
    await api.setTaskStatus(42, 'done');

    expect(calls).toEqual([
      ['/api/v1/today', undefined],
      [
        '/api/v1/capture',
        {
          method: 'POST',
          body: JSON.stringify({ request_id: 'capture-1', text: 'Изменение' }),
        },
      ],
      [
        '/api/v1/interactions/interaction%2Funsafe/responses',
        {
          method: 'POST',
          body: JSON.stringify({
            request_id: 'answer-1',
            option_id: 'apply',
            text: 'Применить',
          }),
        },
      ],
      [
        '/api/v1/tasks/42/status',
        { method: 'PATCH', body: JSON.stringify({ status: 'done' }) },
      ],
    ]);
  });
});
