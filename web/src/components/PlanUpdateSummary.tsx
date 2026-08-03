import type { PlanChange, PlanUpdate } from "../types";

function changeMarker(change: PlanChange): string {
  const markers: Record<PlanChange["kind"], string> = {
    added: "+",
    moved: "→",
    completed: "✓",
    restored: "↺",
    unscheduled: "○"
  };

  return markers[change.kind];
}

export default function PlanUpdateSummary({ update }: { update: PlanUpdate }) {
  return (
    <section className="plan-update" aria-live="polite" aria-labelledby="plan-update-title">
      <h2 id="plan-update-title">{update.title}</h2>
      {update.message && <p>{update.message}</p>}
      {update.changes.length > 0 && (
        <ul>
          {update.changes.map((change, index) => (
            <li key={`${change.kind}-${change.title}-${index}`}>
              <span aria-hidden="true">{changeMarker(change)}</span>
              <strong>{change.title}</strong>
              {change.detail && <small>{change.detail}</small>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
