import { FormEvent, useEffect, useRef } from "react";

import type { ComposerPhase } from "../composerState";
import type {
  Clarification,
  Confirmation,
  ConflictDetails,
  InteractionOption
} from "../types";

type DayComposerProps = {
  open: boolean;
  draft: string;
  phase: ComposerPhase;
  slow: boolean;
  error: string | null;
  clarification: Clarification | null;
  confirmation: Confirmation | null;
  conflict: ConflictDetails | null;
  disabled?: boolean;
  onOpenChange: (open: boolean) => void;
  onDraftChange: (value: string) => void;
  onSubmit: () => Promise<void>;
  onOption: (interactionId: string, option: InteractionOption) => Promise<void>;
};

export default function DayComposer({
  open,
  draft,
  phase,
  slow,
  error,
  clarification,
  confirmation,
  conflict,
  disabled = false,
  onOpenChange,
  onDraftChange,
  onSubmit,
  onOption
}: DayComposerProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const submitting = phase === "submitting";
  const interaction = clarification || confirmation || conflict;
  const interactionId = clarification?.id || confirmation?.id || conflict?.id || null;
  const interactionTitle = confirmation?.title || conflict?.title || clarification?.question || null;
  const interactionBody = confirmation?.summary || conflict?.message || null;
  const interactionOptions = interaction?.options || [];

  useEffect(() => {
    if (!open) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusTimer = window.setTimeout(() => textareaRef.current?.focus(), 30);

    function updateViewportHeight() {
      const height = window.visualViewport?.height || window.innerHeight;
      document.documentElement.style.setProperty("--visual-viewport-height", `${height}px`);
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape" && !submitting) {
        onOpenChange(false);
        return;
      }

      if (event.key !== "Tab" || !sheetRef.current) {
        return;
      }

      const focusable = Array.from(
        sheetRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );

      if (!focusable.length) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    updateViewportHeight();
    window.addEventListener("keydown", handleKeyDown);
    window.visualViewport?.addEventListener("resize", updateViewportHeight);

    return () => {
      window.clearTimeout(focusTimer);
      document.body.style.overflow = previousOverflow;
      document.documentElement.style.removeProperty("--visual-viewport-height");
      window.removeEventListener("keydown", handleKeyDown);
      window.visualViewport?.removeEventListener("resize", updateViewportHeight);
      triggerRef.current?.focus();
    };
  }, [onOpenChange, open, submitting]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!draft.trim() || submitting) {
      return;
    }

    void onSubmit();
  }

  return (
    <>
      <div className="composer-dock">
        {submitting ? (
          <div className="composer-processing" role="status" aria-live="polite">
            <span className="processing-indicator" aria-hidden="true" />
            <span>
              <strong>Пересобираю день…</strong>
              <small>{slow ? "Это занимает чуть дольше обычного. Текст сохранён." : "Текст сохранён"}</small>
            </span>
          </div>
        ) : (
          <button
            ref={triggerRef}
            type="button"
            className="composer-trigger"
            onClick={() => onOpenChange(true)}
            aria-expanded={open}
            aria-controls="day-composer-sheet"
            disabled={disabled}
          >
            <span>{draft.trim() ? "Продолжить сообщение" : "Скажи, что изменилось"}</span>
            <span className="composer-chevron" aria-hidden="true">⌃</span>
          </button>
        )}
      </div>

      {open && (
        <div
          className="composer-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !submitting) {
              onOpenChange(false);
            }
          }}
        >
          <div
            id="day-composer-sheet"
            ref={sheetRef}
            className="composer-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="composer-title"
          >
            <div className="sheet-handle" aria-hidden="true" />
            <header>
              <div>
                <p>Обновить день</p>
                <h2 id="composer-title">Что изменилось?</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => onOpenChange(false)}
                disabled={submitting}
                aria-label="Закрыть поле ввода"
              >
                <span aria-hidden="true">×</span>
              </button>
            </header>

            <form onSubmit={handleSubmit}>
              {interaction && (
                <section className="composer-interaction" aria-live="polite">
                  {interactionTitle && <h3>{interactionTitle}</h3>}
                  {interactionBody && interactionBody !== interactionTitle && <p>{interactionBody}</p>}
                  {interactionOptions.length > 0 && interactionId && (
                    <div className="interaction-options" role="group" aria-label="Варианты ответа">
                      {interactionOptions.map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => void onOption(interactionId, option)}
                          disabled={submitting}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </section>
              )}

              <label className="sr-only" htmlFor="day-message">Что изменилось в твоём дне?</label>
              <textarea
                ref={textareaRef}
                id="day-message"
                value={draft}
                onChange={(event) => onDraftChange(event.target.value)}
                placeholder={interaction ? "Или ответь своими словами" : "Например: задержался до восьми, сил мало, но появился важный звонок"}
                rows={5}
                disabled={submitting}
              />
              <div className="composer-helper-row">
                <span>Пиши как есть</span>
                <span>{draft.length}/4000</span>
              </div>

              {error && (
                <div className="composer-error" role="alert">
                  <span className="error-symbol" aria-hidden="true">!</span>
                  <span>
                    <strong>{error}</strong>
                    <small>Текст сохранён</small>
                  </span>
                </div>
              )}

              <button
                type="submit"
                className="send-button"
                disabled={submitting || !draft.trim() || draft.length > 4000}
              >
                {error ? "Повторить" : "Отправить"}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
