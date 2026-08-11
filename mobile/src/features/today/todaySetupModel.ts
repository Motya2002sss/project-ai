const setupMessages = new Set([
  'Доступ к плану не настроен.',
]);

export function shouldOfferTodaySetup(
  apiBaseUrl: string,
  errorMessage: string | null,
): boolean {
  return !apiBaseUrl || Boolean(errorMessage && setupMessages.has(errorMessage));
}
