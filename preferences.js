(() => {
  "use strict";

  const STORAGE_PREFIX = "book-viewer-reading:v1:";

  function storageKey(slug) {
    return `${STORAGE_PREFIX}${slug}`;
  }

  function read(slug) {
    if (!slug) return {};

    try {
      const value = JSON.parse(localStorage.getItem(storageKey(slug)) || "null");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_error) {
      return {};
    }
  }

  function update(slug, changes) {
    if (!slug) return;

    try {
      localStorage.setItem(storageKey(slug), JSON.stringify({ ...read(slug), ...changes }));
    } catch (_error) {
      // The viewer remains usable when browser storage is unavailable or full.
    }
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
    read,
    touch,
    savePosition,
    lastOpenedAt,
    progressPercent,
  });
})();
