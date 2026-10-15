import { createHash } from "node:crypto";

const MAX_LISTENERS = 5_000;
const LISTENER_TTL_MS = 30 * 24 * 60 * 60 * 1_000;

interface SavedProgress {
  cursor: string;
  touchedAt: number;
}

export class ListeningProgressStore {
  readonly #entries = new Map<string, SavedProgress>();

  #key(listenerId: string): string {
    return createHash("sha256").update(listenerId.trim(), "utf8").digest("base64url");
  }

  #prune(now: number): void {
    for (const [key, value] of this.#entries) {
      if (now - value.touchedAt > LISTENER_TTL_MS) this.#entries.delete(key);
    }
    while (this.#entries.size >= MAX_LISTENERS) {
      const oldest = this.#entries.keys().next().value as string | undefined;
      if (!oldest) break;
      this.#entries.delete(oldest);
    }
  }

  get(listenerId: string): string | undefined {
    const key = this.#key(listenerId);
    const value = this.#entries.get(key);
    if (!value) return undefined;
    if (Date.now() - value.touchedAt > LISTENER_TTL_MS) {
      this.#entries.delete(key);
      return undefined;
    }
    this.#entries.delete(key);
    this.#entries.set(key, { cursor: value.cursor, touchedAt: Date.now() });
    return value.cursor;
  }

  set(listenerId: string, cursor: string): void {
    const now = Date.now();
    this.#prune(now);
    const key = this.#key(listenerId);
    this.#entries.delete(key);
    this.#entries.set(key, { cursor, touchedAt: now });
  }
}

export const listeningProgress = new ListeningProgressStore();
