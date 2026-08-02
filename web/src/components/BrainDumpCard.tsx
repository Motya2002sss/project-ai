import type { FormEvent } from "react";

type BrainDumpCardProps = {
  draft: string;
  submitting: boolean;
  onDraftChange: (value: string) => void;
  onSubmit: () => Promise<void>;
};

export default function BrainDumpCard({
  draft,
  submitting,
  onDraftChange,
  onSubmit
}: BrainDumpCardProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!draft.trim() || submitting) {
      return;
    }

    void onSubmit();
  }

  return (
    <section className="input-surface" aria-labelledby="mind-input-title">
      <form onSubmit={handleSubmit}>
        <div className="input-heading">
          <span className="input-eyebrow">Разгрузить мысли</span>
          <label id="mind-input-title" htmlFor="mind-input">
            Что у тебя в голове?
          </label>
          <p>Напиши как есть — я соберу из этого реалистичный план.</p>
        </div>
        <div className="thought-field">
          <textarea
            id="mind-input"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder="Например: сегодня мало сил, надо оплатить счета и 40 минут поделать проект"
            rows={3}
          />
        </div>
        <div className="input-actions">
          <span className="input-hint">Без формата и правильных слов</span>
          <button type="submit" disabled={submitting || !draft.trim()}>
            {submitting ? "Собираю..." : "Собрать день"}
          </button>
        </div>
      </form>
    </section>
  );
}
