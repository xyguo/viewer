(() => {
  "use strict";

  const STORAGE_PREFIX = "book-viewer-reading:v1:";
  const READING_STATES_URL = "/api/reading-states";
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

  function storageKey(slug) {
    return `${STORAGE_PREFIX}${slug}`;
  }

  function readLocal(slug) {
    if (!slug) return {};

    try {
      const value = JSON.parse(localStorage.getItem(storageKey(slug)) || "null");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_error) {
      return {};
    }
  }

  function writeLocal(slug, value) {
    if (!slug) return;

    try {
      localStorage.setItem(storageKey(slug), JSON.stringify(value));
    } catch (_error) {
      // The viewer remains usable when browser storage is unavailable or full.
    }
  }

  function localStates() {
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
    } catch (_error) {
      // Browser storage is an optional fallback for the server-owned state.
    }
    return states;
  }

  function stateTimestamp(value) {
    if (Number.isFinite(value?.updatedAt)) return value.updatedAt;
    if (Number.isFinite(value?.lastOpenedAt)) return value.lastOpenedAt;
    return 0;
  }

  function ensureUpdatedAt(value) {
    return Number.isFinite(value?.updatedAt)
      ? value
      : { ...value, updatedAt: stateTimestamp(value) || Date.now() };
  }

  function serverPayload(slug, value) {
    const payload = { bookSlug: slug };
    PERSISTED_FIELDS.forEach((field) => {
      if (value[field] !== undefined && value[field] !== null) payload[field] = value[field];
    });
    return payload;
  }

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
      const payload = await response.json();
      if (!Array.isArray(payload?.states)) return;
      serverAvailable = true;

      const local = localStates();
      const remoteSlugs = new Set();
      payload.states.forEach((remoteValue) => {
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
    } catch (_error) {
      // Static viewing and transient server failures continue to use browser storage.
    }
  }

  function read(slug) {
    return readLocal(slug);
  }

  function update(slug, changes) {
    if (!slug) return;
    const value = { ...read(slug), ...changes, updatedAt: Date.now() };
    writeLocal(slug, value);
    persistToServer(slug, value);
  }

  function touch(slug) {
    update(slug, { lastOpenedAt: Date.now() });
  }

  function savePosition(slug, position) {
    update(slug, position);
  }

  function lastOpenedAt(slug) {
    const value = read(slug).lastOpenedAt;
    return Number.isFinite(value) ? value : 0;
  }

  function progressPercent(slug) {
    const value = read(slug).progressPercent;
    return Number.isFinite(value) ? Math.round(Math.max(0, Math.min(100, value))) : 0;
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
