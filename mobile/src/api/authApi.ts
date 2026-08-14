import type { AuthenticatedUser } from '../features/auth/authReducer';
import type { SessionCredentials } from '../storage/sessionStorage';

type FetchImplementation = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

interface AuthApiOptions {
  baseUrl: string;
  timeoutMs?: number;
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

export interface DogfoodDeviceInput {
  deviceId: string;
  deviceName?: string;
  platform?: string;
  osVersion?: string;
}

export class AuthApiError extends Error {
  constructor(readonly status: number | null) {
    super('Authentication request failed');
  }
}

export function isProvenSessionRevocation(error: unknown): boolean {
  return error instanceof AuthApiError && error.status === 401;
}

export class AuthApi {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchImplementation;

  constructor(options: AuthApiOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.timeoutMs = Math.max(1, options.timeoutMs ?? 15_000);
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

  async signInWithDogfood(
    token: string,
    device: DogfoodDeviceInput,
  ): Promise<SignedInSession> {
    const payload = await this.request<SignInDto>('/api/v2/auth/dogfood', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        device: {
          device_id: device.deviceId,
          ...(device.deviceName ? { device_name: device.deviceName } : {}),
          ...(device.platform ? { platform: device.platform } : {}),
          ...(device.osVersion ? { os_version: device.osVersion } : {}),
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
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timeout = setTimeout(() => {
        controller.abort();
        reject(new AuthApiError(null));
      }, this.timeoutMs);
    });

    try {
      const response = await Promise.race([
        this.fetchImpl(`${this.baseUrl}${path}`, {
          ...init,
          headers: {
            Accept: 'application/json',
            ...(init.body ? { 'Content-Type': 'application/json' } : {}),
            ...(init.headers ?? {}),
          },
          signal: controller.signal,
        }),
        deadline,
      ]);
      if (!response.ok) throw new AuthApiError(response.status);
      if (response.status === 204) return undefined as T;
      return (await Promise.race([response.json(), deadline])) as T;
    } catch (error) {
      if (error instanceof AuthApiError) throw error;
      throw new AuthApiError(null);
    } finally {
      if (timeout) clearTimeout(timeout);
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

export interface AuthOperationResult<T> {
  current: boolean;
  value: T | null;
}

export class AuthOperationCoordinator {
  private epoch = 0;
  private mutationTail: Promise<void> = Promise.resolve();
  private recoveryAllowed = true;

  currentEpoch(): number {
    return this.epoch;
  }

  invalidate(): number {
    this.epoch += 1;
    return this.epoch;
  }

  blockRecovery(): number {
    this.recoveryAllowed = false;
    return this.invalidate();
  }

  captureRecoveryEpoch(): number | null {
    return this.recoveryAllowed ? this.epoch : null;
  }

  authorizeRecovery(epoch: number): boolean {
    if (!this.isCurrent(epoch)) return false;
    this.recoveryAllowed = true;
    return true;
  }

  isCurrent(epoch: number): boolean {
    return epoch === this.epoch;
  }

  runIfCurrent<T>(
    epoch: number,
    operation: () => Promise<T>,
  ): Promise<AuthOperationResult<T>> {
    const result = this.mutationTail.then(async () => {
      if (!this.isCurrent(epoch)) return { current: false, value: null };
      const value = await operation();
      return { current: this.isCurrent(epoch), value };
    });
    this.mutationTail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}

export async function finalizeProvenSessionRevocation(
  lifecycle: AuthOperationCoordinator,
  clearSession: () => Promise<void>,
  publishRevoked: () => void,
): Promise<void> {
  const epoch = lifecycle.blockRecovery();
  try {
    const clear = await lifecycle.runIfCurrent(epoch, clearSession);
    if (!clear.current) return;
  } catch {
    // A proven revocation is terminal even when native storage is unavailable.
  }
  if (lifecycle.isCurrent(epoch)) publishRevoked();
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
