import { ApiError } from './errors';
import type { RuntimeValidator } from './validation';

type FetchImplementation = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

interface ApiClientOptions {
  baseUrl: string;
  tokenProvider: () => Promise<string | null>;
  timeoutMs?: number;
  fetchImpl?: FetchImplementation;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: () => Promise<string | null>;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchImplementation;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.tokenProvider = options.tokenProvider;
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.fetchImpl =
      options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  async request<T>(
    path: string,
    init: RequestInit = {},
    validator?: RuntimeValidator<T>,
  ): Promise<T> {
    if (!this.baseUrl) {
      throw new ApiError('configuration', false);
    }

    const token = await this.tokenProvider();
    if (!token) {
      throw new ApiError('configuration', false);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const headers: Record<string, string> = {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    };
    if (init.body != null) headers['Content-Type'] = 'application/json';

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: { ...headers, ...(init.headers ?? {}) },
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new ApiError('authentication', false, response.status);
        }
        if (response.status === 404) {
          throw new ApiError('not_found', false, response.status);
        }
        if (response.status === 400 || response.status === 422) {
          throw new ApiError('validation', false, response.status);
        }
        throw new ApiError(
          'server',
          response.status >= 500,
          response.status,
        );
      }

      try {
        const payload: unknown = await response.json();
        if (validator && !validator(payload)) {
          throw new ApiError('invalid_response', true, response.status);
        }
        return payload as T;
      } catch {
        throw new ApiError('invalid_response', true, response.status);
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError('timeout', true);
      }
      if (error instanceof TypeError) {
        throw new ApiError('network', true);
      }
      throw new ApiError('unknown', true);
    } finally {
      clearTimeout(timeout);
    }
  }
}
