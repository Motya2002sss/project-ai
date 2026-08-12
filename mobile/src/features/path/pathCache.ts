import { isPathResponseDto } from '../../api/pathApi';
import {
  defaultStorageTimeoutMs,
  withStorageDeadline,
} from '../../storage/storageDeadline';
import type { PathResponseDto } from './pathTypes';

export interface PublicPathStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export class PathCache {
  private readonly storageKey: string;

  constructor(
    private readonly storage: PublicPathStorage,
    publicUserId: string,
    private readonly timeoutMs = defaultStorageTimeoutMs,
  ) {
    if (!publicUserId.trim()) throw new Error('publicUserId is required');
    this.storageKey = `ai-life-planner:user:${encodeURIComponent(publicUserId)}:goals:v2`;
  }

  async load(): Promise<PathResponseDto | null> {
    const encoded = await withStorageDeadline(
      this.storage.getItem(this.storageKey),
      this.timeoutMs,
    );
    if (encoded === null) return null;
    try {
      const value: unknown = JSON.parse(encoded);
      if (isPathResponseDto(value)) return value;
    } catch {
      // Invalid cache is removed below and never reaches presentation code.
    }
    await withStorageDeadline(
      this.storage.removeItem(this.storageKey),
      this.timeoutMs,
    );
    return null;
  }

  async save(response: PathResponseDto): Promise<void> {
    await withStorageDeadline(
      this.storage.setItem(this.storageKey, JSON.stringify(response)),
      this.timeoutMs,
    );
  }

  async removeGoal(publicId: string): Promise<void> {
    const response = await this.load();
    if (!response) return;
    const goals = response.goals.filter(
      (item) => item.goal.public_id !== publicId,
    );
    if (goals.length === response.goals.length) return;
    await this.save({ goals });
  }
}
