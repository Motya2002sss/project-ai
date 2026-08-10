export type ApiErrorKind =
  | 'configuration'
  | 'authentication'
  | 'timeout'
  | 'network'
  | 'validation'
  | 'not_found'
  | 'server'
  | 'invalid_response'
  | 'unknown';

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly retryable: boolean,
    public readonly status?: number,
    message: string = kind,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface PresentationError {
  message: string;
  retryable: boolean;
}

export function toPresentationError(error: unknown): PresentationError {
  if (!(error instanceof ApiError)) {
    return { message: 'Не получилось обновить данные.', retryable: true };
  }

  switch (error.kind) {
    case 'configuration':
      return {
        message: 'Подключите локальный backend для dogfooding.',
        retryable: false,
      };
    case 'authentication':
      return { message: 'Доступ к плану не настроен.', retryable: false };
    case 'timeout':
      return {
        message: 'Не получилось обновить план. Текст сохранён.',
        retryable: true,
      };
    case 'network':
      return {
        message: 'Нет соединения. Показываю сохранённый день.',
        retryable: true,
      };
    case 'validation':
      return {
        message: 'Не получилось отправить запрос. Проверьте текст.',
        retryable: false,
      };
    case 'not_found':
      return { message: 'Данные больше недоступны.', retryable: false };
    case 'server':
    case 'invalid_response':
    case 'unknown':
      return {
        message: 'Не получилось обновить данные.',
        retryable: error.retryable,
      };
  }
}

export function toTodayPresentationError(
  error: unknown,
  hasCachedSnapshot: boolean,
): PresentationError {
  const fallback = toPresentationError(error);
  if (!(error instanceof ApiError)) {
    return { message: 'Не получилось загрузить план.', retryable: true };
  }
  if (error.kind === 'network') {
    return {
      message: hasCachedSnapshot
        ? 'Нет соединения. Показываю сохранённый день.'
        : 'Нет соединения. План дня не загрузился.',
      retryable: true,
    };
  }
  if (error.kind === 'timeout') {
    return {
      message: hasCachedSnapshot
        ? 'Не удалось обновить план. Показываю сохранённый день.'
        : 'Не удалось загрузить план.',
      retryable: true,
    };
  }
  if (
    error.kind === 'server' ||
    error.kind === 'invalid_response' ||
    error.kind === 'unknown'
  ) {
    return { message: 'Не получилось загрузить план.', retryable: error.retryable };
  }
  return fallback;
}

export function toCapturePresentationError(error: unknown): PresentationError {
  const fallback = toPresentationError(error);
  if (!(error instanceof ApiError)) {
    return {
      message: 'Не получилось обновить день. Текст сохранён.',
      retryable: true,
    };
  }
  if (error.kind === 'network') {
    return { message: 'Нет соединения. Текст сохранён.', retryable: true };
  }
  if (error.kind === 'timeout') {
    return {
      message: 'Не получилось обновить план. Текст сохранён.',
      retryable: true,
    };
  }
  if (
    error.kind === 'server' ||
    error.kind === 'invalid_response' ||
    error.kind === 'unknown'
  ) {
    return {
      message: 'Не получилось обновить день. Текст сохранён.',
      retryable: error.retryable,
    };
  }
  return fallback;
}

export function toCompletionPresentationError(
  error: unknown,
): PresentationError {
  const fallback = toPresentationError(error);
  if (!(error instanceof ApiError)) {
    return { message: 'Не удалось сохранить выполнение.', retryable: true };
  }
  if (
    error.kind === 'network' ||
    error.kind === 'timeout' ||
    error.kind === 'server' ||
    error.kind === 'invalid_response' ||
    error.kind === 'unknown'
  ) {
    return {
      message: 'Не удалось сохранить выполнение.',
      retryable: error.retryable,
    };
  }
  return fallback;
}
