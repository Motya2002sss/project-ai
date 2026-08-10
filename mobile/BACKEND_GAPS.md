# Mobile backend gaps

## Optional Task Details context

**Status:** non-blocking for Today P0; the unavailable sections are omitted.

**Existing contract:** `DaySnapshot.tasks[]` supplies the task title, timing,
duration, scheduling type, and status. It does not expose a task-to-goal link or
an execution plan.

**Missing data:** canonical linked-goal identity/title and ordered execution
steps for one task. The mobile client must not derive either from titles or
other snapshot fields.

**Minimal future contract:** an authenticated task-details read returning the
canonical `task`, optional `linked_goal: { id, title } | null`, and optional
ordered `execution_steps: [{ id, title, status, order }]`. Until such a contract
exists, Task Details intentionally shows only the fields already supplied by
`DaySnapshot`.
