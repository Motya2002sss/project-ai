import type { FocusEvent, KeyboardEvent } from "react";

import type { LoadState } from "../types";

type TodayHeaderProps = {
  dateText: string;
  userIdDraft: string;
  backendStatus: LoadState;
  onUserIdDraftChange: (value: string) => void;
  onApplyUserId: () => void;
};

export default function TodayHeader({
  dateText,
  userIdDraft,
  backendStatus,
  onUserIdDraftChange,
  onApplyUserId
}: TodayHeaderProps) {
  function applyAndClose(input: HTMLInputElement) {
    onApplyUserId();
    input.closest("details")?.removeAttribute("open");
  }

  function handleBlur(event: FocusEvent<HTMLInputElement>) {
    applyAndClose(event.currentTarget);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      applyAndClose(event.currentTarget);
    }
  }

  return (
    <header className="today-header">
      <div className="header-meta">
        <p className="date-line">{dateText}</p>
        <details className="profile-settings">
          <summary aria-label="Открыть локальные настройки" title="Локальные настройки">
            <span aria-hidden="true">{(userIdDraft.trim()[0] || "Я").toUpperCase()}</span>
          </summary>
          <div className="profile-settings-panel">
            <label htmlFor="user-id">Локальный профиль</label>
            <input
              id="user-id"
              value={userIdDraft}
              onChange={(event) => onUserIdDraftChange(event.target.value)}
              onBlur={handleBlur}
              onKeyDown={handleKeyDown}
              autoComplete="off"
            />
            <p>Временный User ID для локального MVP.</p>
            <p className="backend-state">
              <span className={`backend-dot backend-dot-${backendStatus}`} aria-hidden="true" />
              {backendStatus === "ready"
                ? "Backend доступен"
                : backendStatus === "error"
                  ? "Backend недоступен"
                  : "Проверяю backend"}
            </p>
          </div>
        </details>
      </div>
      <h1>Сегодня</h1>
    </header>
  );
}
