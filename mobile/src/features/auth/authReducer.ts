export interface AuthenticatedUser {
  publicId: string;
  name: string | null;
  email: string | null;
  timezone: string;
}

export type AuthStatus =
  | 'hydrating'
  | 'unauthenticated'
  | 'authenticated'
  | 'refreshing'
  | 'expired'
  | 'revoked';

export interface AuthState {
  status: AuthStatus;
  user: AuthenticatedUser | null;
  error: string | null;
}

export type AuthAction =
  | { type: 'hydrate/authenticated'; user: AuthenticatedUser }
  | { type: 'hydrate/unauthenticated' }
  | { type: 'session/authenticated'; user: AuthenticatedUser }
  | { type: 'refresh/started' }
  | { type: 'refresh/succeeded'; user?: AuthenticatedUser }
  | {
      type: 'session/expired';
      message: string;
      user?: AuthenticatedUser | null;
    }
  | { type: 'session/revoked' }
  | { type: 'logout/completed' }
  | { type: 'account/deleted' };

export const initialAuthState: AuthState = {
  status: 'hydrating',
  user: null,
  error: null,
};

const emptyState: AuthState = {
  status: 'unauthenticated',
  user: null,
  error: null,
};

export function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'hydrate/authenticated':
    case 'session/authenticated':
      return { status: 'authenticated', user: action.user, error: null };
    case 'hydrate/unauthenticated':
    case 'logout/completed':
    case 'account/deleted':
      return emptyState;
    case 'refresh/started':
      return { status: 'refreshing', user: state.user, error: null };
    case 'refresh/succeeded':
      return {
        status: 'authenticated',
        user: action.user ?? state.user,
        error: null,
      };
    case 'session/expired':
      return {
        status: 'expired',
        user: action.user === undefined ? state.user : action.user,
        error: action.message,
      };
    case 'session/revoked':
      return { status: 'revoked', user: null, error: null };
    default:
      return state;
  }
}
