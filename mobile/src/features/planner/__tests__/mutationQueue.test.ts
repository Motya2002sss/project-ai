import { describe, expect, it } from 'vitest';

import {
  KeyedOperationRegistry,
  LatestRequestGate,
  SerialMutationQueue,
} from '../mutationQueue';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('SerialMutationQueue', () => {
  it('does not start a later mutation until the previous one and its cache write finish', async () => {
    const queue = new SerialMutationQueue();
    const firstResponse = deferred<void>();
    const firstCacheWrite = deferred<void>();
    const order: string[] = [];

    const first = queue.enqueue(async () => {
      order.push('first:start');
      await firstResponse.promise;
      order.push('first:response');
      await firstCacheWrite.promise;
      order.push('first:cache');
    });
    const second = queue.enqueue(async () => {
      order.push('second:start');
    });

    await Promise.resolve();
    expect(order).toEqual(['first:start']);

    firstResponse.resolve();
    await Promise.resolve();
    expect(order).toEqual(['first:start', 'first:response']);

    firstCacheWrite.resolve();
    await Promise.all([first, second]);
    expect(order).toEqual([
      'first:start',
      'first:response',
      'first:cache',
      'second:start',
    ]);
  });

  it('continues with the next mutation after a rejected operation', async () => {
    const queue = new SerialMutationQueue();
    const order: string[] = [];

    const failed = queue.enqueue(async () => {
      order.push('failed');
      throw new Error('expected');
    });
    const next = queue.enqueue(async () => {
      order.push('next');
    });

    await expect(failed).rejects.toThrow('expected');
    await next;
    expect(order).toEqual(['failed', 'next']);
  });
});

describe('KeyedOperationRegistry', () => {
  it('does not let an older finally block clear a newer operation for the same task', () => {
    const registry = new KeyedOperationRegistry<number>();
    expect(registry.start(42, 'first')).toBe(true);
    registry.finish(42, 'first');
    expect(registry.start(42, 'second')).toBe(true);

    registry.finish(42, 'first');

    expect(registry.isActive(42, 'second')).toBe(true);
  });
});

describe('LatestRequestGate', () => {
  it('accepts only the newest overlapping read', () => {
    const gate = new LatestRequestGate();
    const first = gate.begin();
    const second = gate.begin();

    expect(gate.isCurrent(first)).toBe(false);
    expect(gate.isCurrent(second)).toBe(true);
  });

  it('invalidates a read as soon as credentials begin changing', () => {
    const gate = new LatestRequestGate();
    const request = gate.begin();

    gate.invalidate();

    expect(gate.isCurrent(request)).toBe(false);
  });
});
