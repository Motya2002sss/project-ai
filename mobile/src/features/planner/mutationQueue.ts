export class SerialMutationQueue {
  private tail: Promise<void> = Promise.resolve();

  enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.tail.then(operation, operation);
    this.tail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}

export class KeyedOperationRegistry<Key> {
  private readonly active = new Map<Key, string>();

  start(key: Key, operationId: string): boolean {
    if (this.active.has(key)) return false;
    this.active.set(key, operationId);
    return true;
  }

  isActive(key: Key, operationId: string): boolean {
    return this.active.get(key) === operationId;
  }

  finish(key: Key, operationId: string): void {
    if (this.isActive(key, operationId)) this.active.delete(key);
  }
}

export class LatestRequestGate {
  private current = 0;

  begin(): number {
    this.current += 1;
    return this.current;
  }

  isCurrent(requestId: number): boolean {
    return requestId === this.current;
  }

  invalidate(): void {
    this.current += 1;
  }
}
