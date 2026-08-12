import { mergeEvidence } from './pathModel';
import type { AuthStatus } from '../auth/authReducer';
import type {
  EvidenceSummaryDto,
  GoalPathDto,
  PathResponseDto,
} from './pathTypes';

export interface PathDataState {
  scope: string | null;
  response: PathResponseDto | null;
  status: 'loading' | 'ready' | 'error';
  source: 'cache' | 'network' | null;
  errorMessage: string | null;
}

export const initialPathDataState: PathDataState = {
  scope: null,
  response: null,
  status: 'loading',
  source: null,
  errorMessage: null,
};

export function resolvePathCacheScope(
  _authStatus: AuthStatus,
  authenticatedPublicUserId: string | null,
  _legacyStoredPublicUserId?: string | null,
): string | null {
  return authenticatedPublicUserId;
}

export type PathDataAction =
  | { type: 'scope/changed'; scope: string | null }
  | { type: 'cache/loaded'; response: PathResponseDto | null }
  | { type: 'refresh/started' }
  | { type: 'refresh/succeeded'; response: PathResponseDto }
  | { type: 'refresh/failed'; message: string };

export function pathDataReducer(
  state: PathDataState,
  action: PathDataAction,
): PathDataState {
  switch (action.type) {
    case 'scope/changed':
      return { ...initialPathDataState, scope: action.scope };
    case 'cache/loaded':
      if (!action.response) return state;
      return {
        scope: state.scope,
        response: action.response,
        status: 'loading',
        source: 'cache',
        errorMessage: null,
      };
    case 'refresh/started':
      return { ...state, status: 'loading', errorMessage: null };
    case 'refresh/succeeded':
      return {
        scope: state.scope,
        response: action.response,
        status: 'ready',
        source: 'network',
        errorMessage: null,
      };
    case 'refresh/failed':
      return { ...state, status: 'error', errorMessage: action.message };
    default:
      return state;
  }
}

export function pathDataStateForScope(
  state: PathDataState,
  scope: string | null,
): PathDataState {
  return state.scope === scope
    ? state
    : { ...initialPathDataState, scope };
}

export interface GoalDetailsDataState {
  scope: string | null;
  detail: GoalPathDto | null;
  source: 'cache' | 'network' | null;
  status: 'loading' | 'ready' | 'error';
  errorMessage: string | null;
  evidence: EvidenceSummaryDto[];
  nextCursor: string | null;
  evidenceStatus: 'idle' | 'loading' | 'loadingMore' | 'ready' | 'error';
  evidenceError: string | null;
}

export const initialGoalDetailsDataState: GoalDetailsDataState = {
  scope: null,
  detail: null,
  source: null,
  status: 'loading',
  errorMessage: null,
  evidence: [],
  nextCursor: null,
  evidenceStatus: 'idle',
  evidenceError: null,
};

export type GoalDetailsDataAction =
  | { type: 'scope/changed'; scope: string | null }
  | { type: 'cache/loaded'; detail: GoalPathDto | null }
  | { type: 'refresh/started' }
  | { type: 'detail/succeeded'; detail: GoalPathDto }
  | { type: 'detail/failed'; message: string }
  | { type: 'detail/unavailable'; message: string }
  | { type: 'evidence/started'; mode: 'replace' | 'append' }
  | {
      type: 'evidence/succeeded';
      mode: 'replace' | 'append';
      items: EvidenceSummaryDto[];
      nextCursor: string | null;
    }
  | { type: 'evidence/failed'; message: string };

export function goalDetailsDataReducer(
  state: GoalDetailsDataState,
  action: GoalDetailsDataAction,
): GoalDetailsDataState {
  switch (action.type) {
    case 'scope/changed':
      return { ...initialGoalDetailsDataState, scope: action.scope };
    case 'cache/loaded':
      if (!action.detail) return state;
      return {
        ...state,
        detail: action.detail,
        source: 'cache',
        evidence: action.detail.recent_evidence,
      };
    case 'refresh/started':
      return { ...state, status: 'loading', errorMessage: null };
    case 'detail/succeeded':
      return {
        ...state,
        detail: action.detail,
        source: 'network',
        status: 'ready',
        errorMessage: null,
        evidence:
          state.evidenceStatus === 'ready'
            ? state.evidence
            : action.detail.recent_evidence,
      };
    case 'detail/failed':
      return { ...state, status: 'error', errorMessage: action.message };
    case 'detail/unavailable':
      return {
        ...initialGoalDetailsDataState,
        scope: state.scope,
        status: 'error',
        errorMessage: action.message,
      };
    case 'evidence/started':
      return {
        ...state,
        evidenceStatus:
          action.mode === 'append' ? 'loadingMore' : 'loading',
        evidenceError: null,
      };
    case 'evidence/succeeded':
      return {
        ...state,
        evidence:
          action.mode === 'append'
            ? mergeEvidence(state.evidence, action.items)
            : action.items,
        nextCursor: action.nextCursor,
        evidenceStatus: 'ready',
        evidenceError: null,
      };
    case 'evidence/failed':
      return {
        ...state,
        evidenceStatus: 'error',
        evidenceError: action.message,
      };
    default:
      return state;
  }
}

export function goalDetailsStateForScope(
  state: GoalDetailsDataState,
  scope: string | null,
): GoalDetailsDataState {
  return state.scope === scope
    ? state
    : { ...initialGoalDetailsDataState, scope };
}
