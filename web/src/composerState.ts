import type { Clarification, Confirmation, ConflictDetails, MessageStatus } from "./types";

export type ComposerPhase =
  | "idle"
  | "editing"
  | "submitting"
  | "clarification"
  | "confirmation"
  | "conflict"
  | "success"
  | "error";

export type ComposerState = {
  phase: ComposerPhase;
  open: boolean;
  draft: string;
  activeRequestId: string | null;
  retryRequestId: string | null;
  slow: boolean;
  error: string | null;
  clarification: Clarification | null;
  confirmation: Confirmation | null;
  conflict: ConflictDetails | null;
};

export type ComposerAction =
  | { type: "open" }
  | { type: "close" }
  | { type: "edit"; value: string }
  | { type: "submit"; requestId: string }
  | { type: "slow"; requestId: string }
  | {
      type: "response";
      requestId: string;
      status: MessageStatus;
      clarification: Clarification | null;
      confirmation: Confirmation | null;
      conflict: ConflictDetails | null;
    }
  | { type: "error"; requestId: string; message: string }
  | { type: "reset" };

export const initialComposerState: ComposerState = {
  phase: "idle",
  open: false,
  draft: "",
  activeRequestId: null,
  retryRequestId: null,
  slow: false,
  error: null,
  clarification: null,
  confirmation: null,
  conflict: null
};

export function composerReducer(state: ComposerState, action: ComposerAction): ComposerState {
  if (action.type === "open") {
    return { ...state, open: true, phase: state.phase === "idle" ? "editing" : state.phase };
  }

  if (action.type === "close") {
    if (state.phase === "submitting") return state;
    return { ...state, open: false, phase: state.phase === "editing" ? "idle" : state.phase };
  }

  if (action.type === "edit") {
    return {
      ...state,
      draft: action.value,
      phase: "editing",
      error: null,
      retryRequestId: null
    };
  }

  if (action.type === "submit") {
    return {
      ...state,
      phase: "submitting",
      open: false,
      activeRequestId: action.requestId,
      slow: false,
      error: null
    };
  }

  if (action.type === "slow") {
    return state.activeRequestId === action.requestId ? { ...state, slow: true } : state;
  }

  if (action.type === "response") {
    if (state.activeRequestId !== action.requestId) return state;

    const phase: ComposerPhase = action.status === "clarification_required"
      ? "clarification"
      : action.status === "confirmation_required"
        ? "confirmation"
        : action.status === "conflict"
          ? "conflict"
          : "success";
    const interactive = ["clarification", "confirmation", "conflict"].includes(phase);

    return {
      ...state,
      phase,
      open: interactive,
      draft: action.status === "applied" ? "" : state.draft,
      activeRequestId: null,
      retryRequestId: null,
      slow: false,
      error: null,
      clarification: action.clarification,
      confirmation: action.confirmation,
      conflict: action.conflict
    };
  }

  if (action.type === "error") {
    if (state.activeRequestId !== action.requestId) return state;

    return {
      ...state,
      phase: "error",
      open: true,
      activeRequestId: null,
      retryRequestId: action.requestId,
      slow: false,
      error: action.message
    };
  }

  return initialComposerState;
}
