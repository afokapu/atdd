// Fixture: TypeScript silent-swallow violations.

interface Match {
  id: string;
}

declare function createMatch(playerId: string): Match;
declare function parsePayload(p: string): unknown;
declare const defaultValue: unknown;

export function seekOpponentSilentReturn(playerId: string): string {
  try {
    return createMatch(playerId).id;
  } catch (e) {
    return "";
  }
}

export function seekOpponentEmptyCatch(playerId: string): string {
  try {
    return createMatch(playerId).id;
  } catch {
    return "fallback";
  }
}

export function parseWithFallback(payload: string): unknown {
  try {
    return parsePayload(payload);
  } catch (e) {
    return defaultValue;
  }
}
