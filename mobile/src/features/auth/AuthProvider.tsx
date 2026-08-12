import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from 'react';
import { Platform } from 'react-native';

import {
  AuthApi,
  AuthApiError,
  AuthOperationCoordinator,
  finalizeProvenSessionRevocation,
  isProvenSessionRevocation,
  type AppleSignInInput,
  SessionRefreshCoordinator,
} from '../../api/authApi';
import { apiBaseUrl } from '../../config/environment';
import { clearUserData } from '../../storage/mobileStorage';
import {
  type LoadedSession,
  type SessionCredentials,
  sessionVault,
} from '../../storage/sessionStorage';
import {
  authReducer,
  initialAuthState,
  type AuthState,
  type AuthenticatedUser,
} from './authReducer';
import {
  cachedIdentityForScope,
  loadCredentialsForPlatform,
} from './sessionHydrationPolicy';

interface AuthContextValue {
  state: AuthState;
  createAppleChallenge: (
    deviceId: string,
  ) => Promise<{ state: string; nonce: string }>;
  signInWithApple: (input: AppleSignInInput) => Promise<void>;
  getAccessToken: () => Promise<string | null>;
  recoverAuthentication: () => Promise<string | null>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState);
  const lifecycleRef = useRef(new AuthOperationCoordinator());
  const pendingUnboundRefreshRef = useRef<{
    epoch: number;
    credentials: SessionCredentials;
  } | null>(null);
  const api = useMemo(() => new AuthApi({ baseUrl: apiBaseUrl }), []);

  const performRefresh = useCallback(async (): Promise<string | null> => {
    const lifecycle = lifecycleRef.current;
    const epoch = lifecycle.captureRecoveryEpoch();
    if (epoch === null) return null;
    let session: LoadedSession | null = null;
    try {
      session = await sessionVault.load();
      if (!lifecycle.isCurrent(epoch)) return null;
      if (!session) {
        dispatch({
          type: 'session/expired',
          message: 'Сессия недоступна. Данные на устройстве сохранены.',
        });
        return null;
      }
      dispatch({ type: 'refresh/started' });
      const rotated = await api.refresh(session.credentials.refreshToken);
      if (!lifecycle.isCurrent(epoch)) return null;
      if (session.source === 'current' && session.publicUserId) {
        const commit = await lifecycle.runIfCurrent(epoch, () =>
          sessionVault.save(session!.publicUserId!, rotated),
        );
        if (!commit.current) return null;
      } else {
        pendingUnboundRefreshRef.current = { epoch, credentials: rotated };
      }
      if (!lifecycle.isCurrent(epoch)) return null;
      dispatch({ type: 'refresh/succeeded' });
      return rotated.accessToken;
    } catch (error) {
      if (!lifecycle.isCurrent(epoch)) return null;
      if (isProvenSessionRevocation(error)) {
        const scope =
          session?.source === 'current' ? session.publicUserId : null;
        pendingUnboundRefreshRef.current = null;
        if (scope) void clearUserData(scope).catch(() => undefined);
        await finalizeProvenSessionRevocation(
          lifecycle,
          () => sessionVault.clear(),
          () => dispatch({ type: 'session/revoked' }),
        );
        return null;
      }
      dispatch({
        type: 'session/expired',
        message: 'Не удалось обновить сессию. Попробуйте ещё раз.',
      });
      return null;
    }
  }, [api]);

  const refreshCoordinator = useMemo(
    () => new SessionRefreshCoordinator(performRefresh),
    [performRefresh],
  );

  useEffect(() => {
    let active = true;
    const lifecycle = lifecycleRef.current;
    const hydrationEpoch = lifecycle.currentEpoch();
    let fallbackUser: AuthenticatedUser | null = null;
    const canPublish = () =>
      active && lifecycle.isCurrent(hydrationEpoch);
    const hydration = (async () => {
      let credentialStorageUnavailable = false;
      const session = await loadCredentialsForPlatform(
        Platform.OS,
        () => sessionVault.load(),
        () => {
          credentialStorageUnavailable = true;
        },
      );
      if (!canPublish()) return;
      if (!session) {
        if (credentialStorageUnavailable) {
          dispatch({
            type: 'session/expired',
            message:
              'Не удалось прочитать сессию. Данные на устройстве сохранены.',
            user: null,
          });
        } else {
          dispatch({ type: 'hydrate/unauthenticated' });
        }
        return;
      }
      fallbackUser = cachedIdentityForScope(
        session.publicUserId,
        session.source,
      );
      try {
        const user = await api.me(session.credentials.accessToken);
        if (!canPublish()) return;
        const commit = await lifecycle.runIfCurrent(
          hydrationEpoch,
          async () => {
            if (
              session.source === 'legacy' ||
              session.publicUserId !== user.publicId
            ) {
              await sessionVault.save(user.publicId, session.credentials);
            }
          },
        );
        if (
          !active ||
          !commit.current ||
          !lifecycle.authorizeRecovery(hydrationEpoch)
        ) {
          return;
        }
        dispatch({ type: 'hydrate/authenticated', user });
      } catch (error) {
        if (!canPublish()) return;
        if (!isProvenSessionRevocation(error)) {
          dispatch({
            type: 'session/expired',
            message: 'Не удалось проверить сессию. Данные на устройстве сохранены.',
            user: fallbackUser,
          });
          return;
        }
        if (fallbackUser && canPublish()) {
          dispatch({
            type: 'session/expired',
            message: 'Обновляю сессию. Данные на устройстве сохранены.',
            user: fallbackUser,
          });
        }
        const accessToken = await refreshCoordinator.refresh();
        if (!canPublish() || !accessToken) return;
        try {
          const user = await api.me(accessToken);
          if (!canPublish()) return;
          const pending = pendingUnboundRefreshRef.current;
          const latestSession =
            pending?.epoch === hydrationEpoch
              ? null
              : await sessionVault.load();
          if (!canPublish()) return;
          const credentials =
            pending?.epoch === hydrationEpoch
              ? pending.credentials
              : latestSession?.credentials ?? null;
          if (!credentials) {
            dispatch({
              type: 'session/expired',
              message:
                'Не удалось сохранить сессию. Данные на устройстве сохранены.',
              user: fallbackUser,
            });
            return;
          }
          const commit = await lifecycle.runIfCurrent(hydrationEpoch, () =>
            sessionVault.save(user.publicId, credentials),
          );
          if (
            !active ||
            !commit.current ||
            !lifecycle.authorizeRecovery(hydrationEpoch)
          ) {
            return;
          }
          if (pending?.epoch === hydrationEpoch) {
            pendingUnboundRefreshRef.current = null;
          }
          dispatch({ type: 'hydrate/authenticated', user });
        } catch (refreshError) {
          if (!canPublish()) return;
          if (isProvenSessionRevocation(refreshError)) {
            const scope =
              session.source === 'current' ? session.publicUserId : null;
            pendingUnboundRefreshRef.current = null;
            if (scope) void clearUserData(scope).catch(() => undefined);
            await finalizeProvenSessionRevocation(
              lifecycle,
              () => sessionVault.clear(),
              () => {
                if (active) dispatch({ type: 'session/revoked' });
              },
            );
            return;
          }
          dispatch({
            type: 'session/expired',
            message:
              'Не удалось проверить сессию. Данные на устройстве сохранены.',
            user: fallbackUser,
          });
        }
      }
    })();
    void hydration.catch(() => {
      if (canPublish()) {
        dispatch({
          type: 'session/expired',
          message: 'Не удалось проверить сессию. Данные на устройстве сохранены.',
          user: fallbackUser,
        });
      }
    });
    return () => {
      active = false;
      pendingUnboundRefreshRef.current = null;
      lifecycle.blockRecovery();
    };
  }, [api, refreshCoordinator]);

  const signInWithApple = useCallback(
    async (input: AppleSignInInput) => {
      const lifecycle = lifecycleRef.current;
      const epoch = lifecycle.invalidate();
      pendingUnboundRefreshRef.current = null;
      const signedIn = await api.signInWithApple(input);
      if (!lifecycle.isCurrent(epoch)) return;
      const commit = await lifecycle.runIfCurrent(epoch, () =>
        sessionVault.save(signedIn.user.publicId, signedIn.credentials),
      );
      if (!commit.current || !lifecycle.authorizeRecovery(epoch)) return;
      dispatch({ type: 'session/authenticated', user: signedIn.user });
    },
    [api],
  );

  const getAccessToken = useCallback(async () => {
    return (await sessionVault.load())?.credentials.accessToken ?? null;
  }, []);

  const logout = useCallback(async () => {
    const lifecycle = lifecycleRef.current;
    const epoch = lifecycle.blockRecovery();
    pendingUnboundRefreshRef.current = null;
    let localSession: LoadedSession | null = null;
    try {
      const cleared = await lifecycle.runIfCurrent(epoch, async () => {
        const session = await sessionVault.load();
        await sessionVault.clear();
        return session;
      });
      if (!cleared.current) return;
      localSession = cleared.value;
    } catch {
      if (lifecycle.isCurrent(epoch)) {
        dispatch({
          type: 'session/expired',
          message: 'Не удалось завершить выход. Попробуйте ещё раз.',
        });
      }
      return;
    }
    const scope =
      localSession?.source === 'current' ? localSession.publicUserId : null;
    if (scope) void clearUserData(scope).catch(() => undefined);
    dispatch({ type: 'logout/completed' });
    if (localSession) {
      await api
        .logout(localSession.credentials.accessToken)
        .catch(() => undefined);
    }
  }, [api]);

  const deleteAccount = useCallback(async () => {
    const lifecycle = lifecycleRef.current;
    const epoch = lifecycle.blockRecovery();
    pendingUnboundRefreshRef.current = null;
    const loaded = await lifecycle.runIfCurrent(epoch, () =>
      sessionVault.load(),
    );
    if (!loaded.current) return;
    const session = loaded.value;
    if (!session) throw new AuthApiError(401);
    await api.deleteAccount(session.credentials.accessToken);
    const scope =
      session.source === 'current' ? session.publicUserId : null;
    if (scope) void clearUserData(scope).catch(() => undefined);
    if (!lifecycle.isCurrent(epoch)) return;
    try {
      const cleared = await lifecycle.runIfCurrent(epoch, () =>
        sessionVault.clear(),
      );
      if (!cleared.current) return;
    } catch {
      if (!lifecycle.isCurrent(epoch)) return;
    }
    dispatch({ type: 'account/deleted' });
  }, [api]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      createAppleChallenge: (deviceId) => api.challenge(deviceId),
      signInWithApple,
      getAccessToken,
      recoverAuthentication: () => refreshCoordinator.refresh(),
      logout,
      deleteAccount,
    }),
    [
      deleteAccount,
      api,
      getAccessToken,
      logout,
      refreshCoordinator,
      signInWithApple,
      state,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
