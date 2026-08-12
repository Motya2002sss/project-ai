import { ApiError } from './errors';
import type { RuntimeValidator } from './validation';

type FetchImplementation = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

interface ApiClientOptions {
  baseUrl: string;
  tokenProvider: () => Promise<string | null>;
  recoverAuthentication?: () => Promise<string | null>;
  timeoutMs?: number;
  fetchImpl?: FetchImplementation;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: () => Promise<string | null>;
  private readonly recoverAuthentication?: () => Promise<string | null>;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchImplementation;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.tokenProvider = options.tokenProvider;
    this.recoverAuthentication = options.recoverAuthentication;
    this.timeoutMs = Math.max(1, options.timeoutMs ?? 15_000);
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
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timeout = setTimeout(() => {
        controller.abort();
        reject(new ApiError('timeout', true));
      }, this.timeoutMs);
    });

    try {
      const execute = async (): Promise<T> => {
        const token = await this.tokenProvider();
        if (controller.signal.aborted) throw new ApiError('timeout', true);
        if (!token) throw new ApiError('configuration', false);

        const headers: Record<string, string> = {
          Accept: 'application/json',
          Authorization: `Bearer ${token}`,
        };
        if (init.body != null) headers['Content-Type'] = 'application/json';
        const performRequest = (accessToken: string) =>
          this.fetchImpl(`${this.baseUrl}${path}`, {
            ...init,
            headers: {
              ...headers,
              Authorization: `Bearer ${accessToken}`,
              ...(init.headers ?? {}),
            },
            signal: controller.signal,
          });
        let response = await performRequest(token);
        if (response.status === 401 && this.recoverAuthentication) {
          const recoveredToken = await this.recoverAuthentication().catch(
            () => null,
          );
          if (controller.signal.aborted) throw new ApiError('timeout', true);
          if (recoveredToken) response = await performRequest(recoveredToken);
        }

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
      };
      return await Promise.race([execute(), deadline]);
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
      if (timeout) clearTimeout(timeout);
    }
  }
}
