import { describe, expect, it } from 'vitest';

import { ApiClient } from '../../../api/client';
import {
  OnboardingApi,
  type OnboardingPreviewInput,
} from '../onboardingApi';
import { defaultResourceBudget } from '../onboardingReducer';

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const response = {
  id: 'a5aa144a-79d1-4b6d-87a8-cb7a18029a89',
  status: 'ready',
  version: 2,
  structured_summary: {
    work_start: '10:00',
    work_end: '19:00',
    sleep_time: '00:00',
    available_days: [1, 3, 5],
    free_evenings: [1, 3],
    preferred_windows: {},
  },
  goal_candidates: ['Стать senior-разработчиком'],
  resource_budget: {
    weekly_available_minutes: 600,
    available_days: [1, 3, 5],
    minimum_minutes: 180,
    comfortable_minutes: 360,
    maximum_minutes: 480,
    free_evenings: [1, 3],
    preferred_windows: {},
    money_budget: null,
    conflict_priority: null,
    reserve_percent: 20,
    allocatable_minutes: 480,
  },
  allocation: {
    reserved_minutes: 120,
    reserve_percent: 20,
    allocatable_minutes: 480,
    planned_minutes: 360,
    goals: [
      { title: 'Стать senior-разработчиком', minutes: 360, percent: 100 },
    ],
  },
  clarification: null,
  created_at: '2026-08-11T10:00:00Z',
  updated_at: '2026-08-11T10:01:00Z',
};

describe('OnboardingApi', () => {
  it('sends an idempotent correction and maps the authoritative preview', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const client = new ApiClient({
      baseUrl: 'https://api.example.test',
      tokenProvider: async () => 'access-token',
      fetchImpl: async (input, init) => {
        calls.push({ url: String(input), init });
        return json(response);
      },
    });
    const api = new OnboardingApi(client);
    const input: OnboardingPreviewInput = {
      requestId: 'stable-request',
      narrative: 'Работаю с 10 до 19 и хочу стать senior-разработчиком',
      resourceBudget: defaultResourceBudget,
      previewId: response.id,
      expectedVersion: 1,
    };

    const preview = await api.preview(input);

    expect(preview).toMatchObject({
      id: response.id,
      status: 'ready',
      version: 2,
      goalCandidates: ['Стать senior-разработчиком'],
      structuredSummary: { workStart: '10:00', workEnd: '19:00' },
      allocation: { reservedMinutes: 120, plannedMinutes: 360 },
    });
    expect(calls[0]?.url).toBe(
      'https://api.example.test/api/v2/onboarding/preview',
    );
    expect(calls[0]?.init?.headers).toMatchObject({
      Authorization: 'Bearer access-token',
    });
    expect(JSON.parse(String(calls[0]?.init?.body))).toMatchObject({
      request_id: 'stable-request',
      preview_id: response.id,
      expected_version: 1,
      resource_budget: {
        weekly_available_minutes: 600,
        reserve_percent: 20,
      },
    });
  });

  it('applies exactly the loaded preview version and reads completion state', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const client = new ApiClient({
      baseUrl: 'https://api.example.test',
      tokenProvider: async () => 'access-token',
      fetchImpl: async (input, init) => {
        calls.push({ url: String(input), init });
        if (String(input).endsWith('/apply')) {
          return json({ ...response, status: 'applied' });
        }
        return json({ status: 'completed', preview: { ...response, status: 'applied' } });
      },
    });
    const api = new OnboardingApi(client);

    await expect(
      api.apply({ previewId: response.id, expectedVersion: 2 }),
    ).resolves.toMatchObject({ status: 'applied' });
    await expect(api.getState()).resolves.toMatchObject({
      status: 'completed',
      preview: { id: response.id, status: 'applied' },
    });

    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({
      preview_id: response.id,
      expected_version: 2,
    });
  });
});
