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

import {
  AuthApi,
  AuthApiError,
  type AppleSignInInput,
  SessionRefreshCoordinator,
} from '../../api/authApi';
import { apiBaseUrl } from '../../config/environment';
import { clearUserData } from '../../storage/mobileStorage';
import {
  sessionScopeStorage,
  sessionVault,
} from '../../storage/sessionStorage';
import {
  authReducer,
  initialAuthState,
  type AuthState,
  type AuthenticatedUser,
} from './authReducer';

interface AuthContextValue {
  state: AuthState;
  signInWithApple: (input: AppleSignInInput) => Promise<void>;
  getAccessToken: () => Promise<string | null>;
  recoverAuthentication: () => Promise<string | null>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState);
  const userRef = useRef<AuthenticatedUser | null>(null);
  userRef.current = state.user;
  const api = useMemo(() => new AuthApi({ baseUrl: apiBaseUrl }), []);

  const performRefresh = useCallback(async (): Promise<string | null> => {
    const credentials = await sessionVault.load();
    if (!credentials) return null;
    dispatch({ type: 'refresh/started' });
    try {
      const rotated = await api.refresh(credentials.refreshToken);
      await sessionVault.save(rotated);
      const currentUser = userRef.current;
      if (currentUser) {
        dispatch({ type: 'refresh/succeeded', user: currentUser });
      }
      return rotated.accessToken;
    } catch (error) {
      if (error instanceof AuthApiError && error.status === 401) {
        const scope =
          userRef.current?.publicId ?? (await sessionScopeStorage.load());
        await sessionVault.clear();
        if (scope) await clearUserData(scope);
        await sessionScopeStorage.clear();
        dispatch({ type: 'session/revoked' });
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
    void (async () => {
      const [credentials, storedScope] = await Promise.all([
        sessionVault.load(),
        sessionScopeStorage.load(),
      ]);
      if (!active) return;
      if (!credentials) {
        if (storedScope) await clearUserData(storedScope);
        await sessionScopeStorage.clear();
        dispatch({ type: 'hydrate/unauthenticated' });
        return;
      }
      try {
        const user = await api.me(credentials.accessToken);
        await sessionScopeStorage.save(user.publicId);
        if (active) dispatch({ type: 'hydrate/authenticated', user });
      } catch (error) {
        if (!(error instanceof AuthApiError) || error.status !== 401) {
          if (active) {
            dispatch({
              type: 'session/expired',
              message: 'Не удалось проверить сессию. Данные на устройстве сохранены.',
            });
          }
          return;
        }
        const accessToken = await refreshCoordinator.refresh();
        if (!active || !accessToken) return;
        try {
          const user = await api.me(accessToken);
          await sessionScopeStorage.save(user.publicId);
          if (active) dispatch({ type: 'hydrate/authenticated', user });
        } catch {
          await sessionVault.clear();
          if (storedScope) await clearUserData(storedScope);
          await sessionScopeStorage.clear();
          if (active) dispatch({ type: 'session/revoked' });
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [api, refreshCoordinator]);

  const signInWithApple = useCallback(
    async (input: AppleSignInInput) => {
      const signedIn = await api.signInWithApple(input);
      await sessionVault.save(signedIn.credentials);
      await sessionScopeStorage.save(signedIn.user.publicId);
      dispatch({ type: 'session/authenticated', user: signedIn.user });
    },
    [api],
  );

  const getAccessToken = useCallback(async () => {
    return (await sessionVault.load())?.accessToken ?? null;
  }, []);

  const logout = useCallback(async () => {
    const credentials = await sessionVault.load();
    const scope =
      userRef.current?.publicId ?? (await sessionScopeStorage.load());
    if (credentials) {
      await api.logout(credentials.accessToken).catch(() => undefined);
    }
    await sessionVault.clear();
    if (scope) await clearUserData(scope);
    await sessionScopeStorage.clear();
    dispatch({ type: 'logout/completed' });
  }, [api]);

  const deleteAccount = useCallback(async () => {
    const credentials = await sessionVault.load();
    if (!credentials) throw new AuthApiError(401);
    const scope =
      userRef.current?.publicId ?? (await sessionScopeStorage.load());
    await api.deleteAccount(credentials.accessToken);
    await sessionVault.clear();
    if (scope) await clearUserData(scope);
    await sessionScopeStorage.clear();
    dispatch({ type: 'account/deleted' });
  }, [api]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      signInWithApple,
      getAccessToken,
      recoverAuthentication: () => refreshCoordinator.refresh(),
      logout,
      deleteAccount,
    }),
    [
      deleteAccount,
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
