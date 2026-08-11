import type { DaySnapshotDto } from '../api/types';
import { decodeSnapshot, encodeSnapshot } from './snapshotCodec';

export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

const legacySnapshotKey = 'ai-life-planner:today:v1';
const legacyDraftKey = 'ai-life-planner:capture-draft:v1';
export const DOGFOOD_CACHE_SCOPE = 'dogfood';

const knownKeyNames = [
  'today',
  'capture-draft',
  'goals',
  'calendar',
  'onboarding',
] as const;

export class MobileCache {
  private migration: Promise<void> | null = null;

  constructor(
    private readonly storage: KeyValueStorage,
    private readonly publicUserId = DOGFOOD_CACHE_SCOPE,
  ) {
    if (!publicUserId.trim()) throw new Error('publicUserId is required');
  }

  private key(name: (typeof knownKeyNames)[number]): string {
    return `ai-life-planner:user:${encodeURIComponent(this.publicUserId)}:${name}:v2`;
  }

  private migrateLegacyDogfoodData(): Promise<void> {
    if (this.publicUserId !== DOGFOOD_CACHE_SCOPE) return Promise.resolve();
    if (!this.migration) {
      this.migration = (async () => {
        const [snapshot, draft] = await Promise.all([
          this.storage.getItem(legacySnapshotKey),
          this.storage.getItem(legacyDraftKey),
        ]);
        if (snapshot !== null && (await this.storage.getItem(this.key('today'))) === null) {
          await this.storage.setItem(this.key('today'), snapshot);
        }
        if (
          draft !== null &&
          (await this.storage.getItem(this.key('capture-draft'))) === null
        ) {
          await this.storage.setItem(this.key('capture-draft'), draft);
        }
        await Promise.all([
          this.storage.removeItem(legacySnapshotKey),
          this.storage.removeItem(legacyDraftKey),
        ]);
      })();
    }
    return this.migration;
  }

  async loadSnapshot(): Promise<DaySnapshotDto | null> {
    await this.migrateLegacyDogfoodData();
    return decodeSnapshot(await this.storage.getItem(this.key('today')));
  }

  async saveSnapshot(snapshot: DaySnapshotDto): Promise<void> {
    await this.storage.setItem(this.key('today'), encodeSnapshot(snapshot));
  }

  async loadDraft(): Promise<string> {
    await this.migrateLegacyDogfoodData();
    return (await this.storage.getItem(this.key('capture-draft'))) ?? '';
  }

  async saveDraft(value: string): Promise<void> {
    if (value.length === 0) {
      await this.storage.removeItem(this.key('capture-draft'));
      return;
    }
    await this.storage.setItem(this.key('capture-draft'), value);
  }

  async clearUserData(): Promise<void> {
    await Promise.all(knownKeyNames.map((name) => this.storage.removeItem(this.key(name))));
    if (this.publicUserId === DOGFOOD_CACHE_SCOPE) {
      await Promise.all([
        this.storage.removeItem(legacySnapshotKey),
        this.storage.removeItem(legacyDraftKey),
      ]);
    }
  }
}
