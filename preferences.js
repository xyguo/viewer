(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: This file runs as a classic browser script.
  "use strict";

  const STORAGE_PREFIX = "book-viewer-reading:v1:";
  const READING_STATES_URL = "/api/reading-states";
  /** @type {(keyof ReadingState)[]} */
  const PERSISTED_FIELDS = [
    "chapterId",
    "segmentId",
    "progressPercent",
    "sourceScrollTop",
    "targetScrollTop",
    "lastOpenedAt",
    "updatedAt",
  ];
  let serverAvailable = false;

  /** @param {string} slug */
  function storageKey(slug) {
    return `${STORAGE_PREFIX}${slug}`;
  }

  /**
   * @param {string} slug
   * @returns {ReadingState}
   */
  function readLocal(slug) {
    if (!slug) return {};

    try {
      const value = JSON.parse(localStorage.getItem(storageKey(slug)) || "null");
      return value && typeof value === "object" && !Array.isArray(value)
        ? /** @type {ReadingState} */ (value)
        : {};
    } catch {
      return {};
    }
  }

  /**
   * @param {string} slug
   * @param {ReadingState} value
   */
  function writeLocal(slug, value) {
    if (!slug) return;

    try {
      localStorage.setItem(storageKey(slug), JSON.stringify(value));
    } catch {
      // The viewer remains usable when browser storage is unavailable or full.
    }
  }

  function localStates() {
    /** @type {Map<string, ReadingState>} */
    const states = new Map();
    try {
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (!key?.startsWith(STORAGE_PREFIX)) continue;
        const slug = key.slice(STORAGE_PREFIX.length);
        const value = readLocal(slug);
        const hasReaderData = PERSISTED_FIELDS.some(
          (field) => field !== "updatedAt" && value[field] !== undefined && value[field] !== null,
        );
        if (slug && hasReaderData) states.set(slug, value);
      }
    } catch {
      // Browser storage is an optional fallback for the server-owned state.
    }
    return states;
  }

  /** @param {ReadingState} value */
  function stateTimestamp(value) {
    const updatedAt = value.updatedAt;
    if (typeof updatedAt === "number" && Number.isFinite(updatedAt)) return updatedAt;
    const lastOpenedAt = value.lastOpenedAt;
    if (typeof lastOpenedAt === "number" && Number.isFinite(lastOpenedAt)) return lastOpenedAt;
    return 0;
  }

  /** @param {ReadingState} value */
  function ensureUpdatedAt(value) {
    return typeof value.updatedAt === "number" && Number.isFinite(value.updatedAt)
      ? value
      : { ...value, updatedAt: stateTimestamp(value) || Date.now() };
  }

  /**
   * @param {string} slug
   * @param {ReadingState} value
   */
  function serverPayload(slug, value) {
    /** @type {Record<string, string | number>} */
    const payload = { bookSlug: slug };
    PERSISTED_FIELDS.forEach((field) => {
      const fieldValue = value[field];
      if (fieldValue !== undefined && fieldValue !== null) payload[field] = fieldValue;
    });
    return payload;
  }

  /**
   * @param {string} slug
   * @param {ReadingState} value
   */
  function persistToServer(slug, value) {
    if (!serverAvailable) return;
    void fetch(READING_STATES_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serverPayload(slug, value)),
      keepalive: true,
    }).catch(() => {});
  }

  async function initialize() {
    if (typeof fetch !== "function") return;
    try {
      const response = await fetch(READING_STATES_URL, { cache: "no-store" });
      if (!response.ok) return;
      const payload = /** @type {{ states?: ReadingState[] }} */ (await response.json());
      const remoteStates = payload.states;
      if (!Array.isArray(remoteStates)) return;
      serverAvailable = true;

      const local = localStates();
      const remoteSlugs = new Set();
      remoteStates.forEach((remoteValue) => {
        const slug = remoteValue?.bookSlug;
        if (!slug) return;
        remoteSlugs.add(slug);
        const localValue = local.get(slug);
        if (localValue && stateTimestamp(localValue) > stateTimestamp(remoteValue)) {
          const migrated = ensureUpdatedAt(localValue);
          writeLocal(slug, migrated);
          persistToServer(slug, migrated);
        } else {
          writeLocal(slug, remoteValue);
        }
      });

      local.forEach((localValue, slug) => {
        if (remoteSlugs.has(slug)) return;
        const migrated = ensureUpdatedAt(localValue);
        writeLocal(slug, migrated);
        persistToServer(slug, migrated);
      });
    } catch {
      // Static viewing and transient server failures continue to use browser storage.
    }
  }

  /** @param {string} slug */
  function read(slug) {
    return readLocal(slug);
  }

  /**
   * @param {string} slug
   * @param {Partial<ReadingState>} changes
   */
  function update(slug, changes) {
    if (!slug) return;
    const value = { ...read(slug), ...changes, updatedAt: Date.now() };
    writeLocal(slug, value);
    persistToServer(slug, value);
  }

  /** @param {string} slug */
  function touch(slug) {
    update(slug, { lastOpenedAt: Date.now() });
  }

  /**
   * @param {string} slug
   * @param {ReadingPosition} position
   */
  function savePosition(slug, position) {
    update(slug, position);
  }

  /** @param {string} slug */
  function lastOpenedAt(slug) {
    const value = read(slug).lastOpenedAt;
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  }

  /** @param {string} slug */
  function progressPercent(slug) {
    const value = read(slug).progressPercent;
    return typeof value === "number" && Number.isFinite(value)
      ? Math.round(Math.max(0, Math.min(100, value)))
      : 0;
  }

  window.BookViewerPreferences = Object.freeze({
    ready: initialize(),
    read,
    touch,
    savePosition,
    lastOpenedAt,
    progressPercent,
  });
})();
