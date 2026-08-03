type DayFocusProps = {
  text: string;
  loading?: boolean;
};

export default function DayFocus({ text, loading = false }: DayFocusProps) {
  return (
    <section className="day-focus" aria-labelledby="day-focus-title">
      <div className="focus-label-row">
        <span className="focus-accent" aria-hidden="true" />
        <h2 id="day-focus-title">Фокус дня</h2>
      </div>
      {loading ? (
        <span className="focus-skeleton" aria-label="Собираю фокус дня" />
      ) : (
        <p>{text}</p>
      )}
    </section>
  );
}
