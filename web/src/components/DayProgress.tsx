type DayProgressProps = {
  done: number;
  total: number;
  contextLabel: string | null;
  loading?: boolean;
};

export default function DayProgress({
  done,
  total,
  contextLabel,
  loading = false
}: DayProgressProps) {
  const percent = total ? Math.round((done / total) * 100) : 0;

  if (loading) {
    return <div className="progress-skeleton" aria-label="Загружаю прогресс дня" />;
  }

  if (!total) {
    return null;
  }

  return (
    <section
      className="day-progress"
      aria-label={`Выполнено ${done} из ${total} задач`}
    >
      <div className="progress-copy">
        <strong>{done} из {total}</strong>
        {contextLabel && <span>{contextLabel}</span>}
      </div>
      <span className="progress-track" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </span>
    </section>
  );
}
