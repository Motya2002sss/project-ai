import type { DaySnapshotDto } from '../api/types';
import { decodeSnapshot, encodeSnapshot } from './snapshotCodec';

export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

const snapshotKey = 'ai-life-planner:today:v1';
const draftKey = 'ai-life-planner:capture-draft:v1';

export class MobileCache {
  constructor(private readonly storage: KeyValueStorage) {}

  async loadSnapshot(): Promise<DaySnapshotDto | null> {
    return decodeSnapshot(await this.storage.getItem(snapshotKey));
  }

  async saveSnapshot(snapshot: DaySnapshotDto): Promise<void> {
    await this.storage.setItem(snapshotKey, encodeSnapshot(snapshot));
  }

  async loadDraft(): Promise<string> {
    return (await this.storage.getItem(draftKey)) ?? '';
  }

  async saveDraft(value: string): Promise<void> {
    if (value.length === 0) {
      await this.storage.removeItem(draftKey);
      return;
    }
    await this.storage.setItem(draftKey, value);
  }
}
