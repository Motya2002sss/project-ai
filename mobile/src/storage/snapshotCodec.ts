import type { DaySnapshotDto } from '../api/types';
import { isDaySnapshotDto } from '../api/validation';

interface SnapshotEnvelope {
  schemaVersion: 1;
  snapshot: DaySnapshotDto;
}

export function encodeSnapshot(snapshot: DaySnapshotDto): string {
  const envelope: SnapshotEnvelope = { schemaVersion: 1, snapshot };
  return JSON.stringify(envelope);
}

export function decodeSnapshot(serialized: string | null): DaySnapshotDto | null {
  if (!serialized) return null;
  try {
    const parsed = JSON.parse(serialized) as Record<string, unknown>;
    if (parsed.schemaVersion !== 1 || !isDaySnapshotDto(parsed.snapshot)) {
      return null;
    }
    return parsed.snapshot;
  } catch {
    return null;
  }
}
