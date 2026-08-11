import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../client';
import {
  ApiError,
  toCapturePresentationError,
  toCompletionPresentationError,
  toPresentationError,
  toTodayPresentationError,
} from '../errors';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ApiClient', () => {
  it('adds bearer auth without logging or adding user identity', async () => {
    const fetchImpl = vi.fn(
      async (_input: string | URL | Request, _request?: RequestInit) =>
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );
    const client = new ApiClient({
      baseUrl: 'http://localhost:8000/',
      tokenProvider: async () => 'dogfood-token',
      fetchImpl,
    });

    await client.request('/api/v1/capture', {
      method: 'POST',
      body: JSON.stringify({ request_id: 'one', text: 'Изменение' }),
    });

    const call = fetchImpl.mock.calls[0];
    expect(call).toBeDefined();
    const [url, request] = call!;
    expect(url).toBe('http://localhost:8000/api/v1/capture');
    expect(request?.headers).toMatchObject({
      Authorization: 'Bearer dogfood-token',
      'Content-Type': 'application/json',
    });
    expect(request?.body).not.toContain('user_external_id');
  });

  it('fails before transport when dogfood token is missing', async () => {
    const fetchImpl = vi.fn();
    const client = new ApiClient({
      baseUrl: 'http://localhost:8000',
      tokenProvider: async () => null,
      fetchImpl,
    });

    await expect(client.request('/api/v1/today')).rejects.toMatchObject({
      kind: 'configuration',
      retryable: false,
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('does not rebind the browser fetch receiver', async () => {
    vi.stubGlobal(
      'fetch',
      function receiverSensitiveFetch(this: unknown) {
        if (this !== globalThis) {
          throw new TypeError('Illegal invocation');
        }
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      },
    );
    const client = new ApiClient({
      baseUrl: 'http://localhost:8000',
      tokenProvider: async () => 'dogfood-token',
    });

    await expect(client.request('/api/v1/today')).resolves.toEqual({ ok: true });
  });

  it('maps a transport abort to a retryable timeout error', async () => {
    vi.useFakeTimers();
    const fetchImpl = vi.fn(
      (_url: string | URL | Request, request?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          request?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          );
        }),
    );
    const client = new ApiClient({
      baseUrl: 'http://localhost:8000',
      tokenProvider: async () => 'token',
      timeoutMs: 25,
      fetchImpl,
    });

    const request = expect(client.request('/api/v1/today')).rejects.toMatchObject({
      kind: 'timeout',
      retryable: true,
    });
    await vi.advanceTimersByTimeAsync(25);

    await request;
    vi.useRealTimers();
  });

  it('rejects valid JSON that does not satisfy the endpoint DTO', async () => {
    const client = new ApiClient({
      baseUrl: 'http://localhost:8000',
      tokenProvider: async () => 'token',
      fetchImpl: async () =>
        new Response(JSON.stringify({ date: '2026-08-10' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    });

    await expect(
      client.request(
        '/api/v1/today',
        {},
        (_value): _value is { date: string } => false,
      ),
    ).rejects.toMatchObject({ kind: 'invalid_response', retryable: true });
  });
});

describe('toPresentationError', () => {
  it('never exposes backend technical detail', () => {
    const error = new ApiError('server', true, 500, 'Pydantic traceback');

    expect(toPresentationError(error)).toEqual({
      message: 'Не получилось обновить данные.',
      retryable: true,
    });
  });

  it('uses product copy for missing local configuration', () => {
    const error = new ApiError('configuration', false);

    expect(toPresentationError(error)).toEqual({
      message: 'Доступ к плану не настроен.',
      retryable: false,
    });
  });

  it('uses operation-specific recovery copy', () => {
    const network = new ApiError('network', true);
    const timeout = new ApiError('timeout', true);

    expect(toTodayPresentationError(network, true).message).toContain(
      'сохранённый день',
    );
    expect(toTodayPresentationError(network, false).message).not.toContain(
      'сохранённый день',
    );
    expect(toCapturePresentationError(timeout).message).toContain(
      'Текст сохранён',
    );
    expect(toCompletionPresentationError(network).message).toBe(
      'Не удалось сохранить выполнение.',
    );
  });
});
