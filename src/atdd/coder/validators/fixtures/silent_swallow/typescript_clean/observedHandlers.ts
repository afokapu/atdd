// Fixture: acceptable TS shapes.

interface Match {
  id: string;
}

declare const logger: {
  warn: (msg: string, ctx?: unknown) => void;
  info: (msg: string, ctx?: unknown) => void;
};

declare function createMatch(playerId: string): Match;
declare function remoteLookup(playerId: string): string;
declare function cachedValue(playerId: string): string;

export function reThrowAfterLog(playerId: string): string {
  try {
    return createMatch(playerId).id;
  } catch (e) {
    logger.warn("match_creator failed", { playerId, error: e });
    throw e;
  }
}

export function fallbackAfterLog(playerId: string): string {
  try {
    return remoteLookup(playerId);
  } catch (e) {
    logger.warn("remote lookup failed, using fallback", { playerId, error: e });
    return cachedValue(playerId);
  }
}

export function rethrowWithContext(playerId: string): string {
  try {
    return createMatch(playerId).id;
  } catch (e) {
    throw new Error(`match creation failed for ${playerId}: ${e}`);
  }
}

export function suppressedSwallow(playerId: string): string {
  try {
    return createMatch(playerId).id;
  } catch (e) { // atdd:suppress(coder.logging.coach-silent-swallow)
    return "";
  }
}
