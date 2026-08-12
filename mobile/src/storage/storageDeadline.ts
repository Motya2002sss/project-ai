export const defaultStorageTimeoutMs = 5_000;

export class StorageDeadlineError extends Error {
  constructor() {
    super('Native storage request timed out');
    this.name = 'StorageDeadlineError';
  }
}

export async function withStorageDeadline<T>(
  operation: Promise<T>,
  timeoutMs = defaultStorageTimeoutMs,
): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_resolve, reject) => {
    timeout = setTimeout(
      () => reject(new StorageDeadlineError()),
      Math.max(1, timeoutMs),
    );
  });
  try {
    return await Promise.race([operation, deadline]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
