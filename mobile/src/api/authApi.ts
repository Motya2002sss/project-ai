import type { AuthenticatedUser } from '../features/auth/authReducer';
import type { SessionCredentials } from '../storage/sessionStorage';

type FetchImplementation = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

interface AuthApiOptions {
  baseUrl: string;
  fetchImpl?: FetchImplementation;
}

interface AuthenticatedUserDto {
  public_id: string;
  name: string | null;
  email: string | null;
  timezone: string;
}

interface TokenPairDto {
  access_token: string;
  refresh_token: string;
}

interface SignInDto extends TokenPairDto {
  user: AuthenticatedUserDto;
}

export interface AppleSignInInput {
  identityToken: string;
  state: string;
  nonce: string;
  name?: string;
  device: {
    deviceId: string;
    deviceName?: string;
    platform?: string;
    osVersion?: string;
  };
}

export interface SignedInSession {
  credentials: SessionCredentials;
  user: AuthenticatedUser;
}

export class AuthApiError extends Error {
  constructor(readonly status: number | null) {
    super('Authentication request failed');
  }
}

export class AuthApi {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchImplementation;

  constructor(options: AuthApiOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.fetchImpl =
      options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  async challenge(deviceId: string): Promise<{ state: string; nonce: string }> {
    const payload = await this.request<{ state: string; nonce: string }>(
      '/api/v2/auth/challenge',
      { method: 'POST', body: JSON.stringify({ device_id: deviceId }) },
    );
    if (!isString(payload.state) || !isString(payload.nonce)) {
      throw new AuthApiError(null);
    }
    return payload;
  }

  async signInWithApple(input: AppleSignInInput): Promise<SignedInSession> {
    const payload = await this.request<SignInDto>('/api/v2/auth/apple', {
      method: 'POST',
      body: JSON.stringify({
        identity_token: input.identityToken,
        state: input.state,
        nonce: input.nonce,
        ...(input.name ? { name: input.name } : {}),
        device: {
          device_id: input.device.deviceId,
          ...(input.device.deviceName
            ? { device_name: input.device.deviceName }
            : {}),
          ...(input.device.platform ? { platform: input.device.platform } : {}),
          ...(input.device.osVersion
            ? { os_version: input.device.osVersion }
            : {}),
        },
      }),
    });
    return toSignedInSession(payload);
  }

  async refresh(refreshToken: string): Promise<SessionCredentials> {
    const payload = await this.request<TokenPairDto>('/api/v2/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    return toCredentials(payload);
  }

  async me(accessToken: string): Promise<AuthenticatedUser> {
    const payload = await this.request<AuthenticatedUserDto>('/api/v2/me', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    return toUser(payload);
  }

  async logout(accessToken: string): Promise<void> {
    await this.request('/api/v2/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  }

  async deleteAccount(accessToken: string): Promise<void> {
    await this.request('/api/v2/account', {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ confirmation: 'DELETE' }),
    });
  }

  private async request<T = unknown>(
    path: string,
    init: RequestInit = {},
  ): Promise<T> {
    if (!this.baseUrl) throw new AuthApiError(null);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          Accept: 'application/json',
          ...(init.body ? { 'Content-Type': 'application/json' } : {}),
          ...(init.headers ?? {}),
        },
      });
    } catch {
      throw new AuthApiError(null);
    }
    if (!response.ok) throw new AuthApiError(response.status);
    if (response.status === 204) return undefined as T;
    try {
      return (await response.json()) as T;
    } catch {
      throw new AuthApiError(response.status);
    }
  }
}

export class SessionRefreshCoordinator {
  private inFlight: Promise<string | null> | null = null;

  constructor(private readonly performRefresh: () => Promise<string | null>) {}

  refresh(): Promise<string | null> {
    if (this.inFlight) return this.inFlight;
    this.inFlight = this.performRefresh().finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }
}

function isString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function toCredentials(payload: TokenPairDto): SessionCredentials {
  if (!isString(payload?.access_token) || !isString(payload?.refresh_token)) {
    throw new AuthApiError(null);
  }
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
  };
}

function toUser(payload: AuthenticatedUserDto): AuthenticatedUser {
  if (
    !isString(payload?.public_id) ||
    !isString(payload?.timezone) ||
    (payload.name !== null && typeof payload.name !== 'string') ||
    (payload.email !== null && typeof payload.email !== 'string')
  ) {
    throw new AuthApiError(null);
  }
  return {
    publicId: payload.public_id,
    name: payload.name,
    email: payload.email,
    timezone: payload.timezone,
  };
}

function toSignedInSession(payload: SignInDto): SignedInSession {
  return { credentials: toCredentials(payload), user: toUser(payload.user) };
}
