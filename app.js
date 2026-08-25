(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: This file runs as a classic browser script.
  "use strict";

  /** @type {BookDocument} */
  let data;
  const shell = requiredElement(".app-shell", HTMLElement);
  const sourceContent = requiredElement("#source-content", HTMLElement);
  const targetContent = requiredElement("#target-content", HTMLElement);
  const sourceScroll = requiredElement("#source-scroll", HTMLElement);
  const targetScroll = requiredElement("#target-scroll", HTMLElement);
  const emptyState = requiredElement("#empty-state", HTMLElement);
  const emptyStateMessage = requiredElement("#empty-state-message", HTMLElement);
  const brandTitle = requiredElement("#brand-title", HTMLElement);
  const sourceHeading = requiredElement("#source-heading", HTMLElement);
  const targetHeading = requiredElement("#target-heading", HTMLElement);
  const sourceViewButton = requiredElement('[data-view-choice="source"]', HTMLButtonElement);
  const targetViewButton = requiredElement('[data-view-choice="target"]', HTMLButtonElement);
  const countLabel = requiredElement("#segment-count", HTMLElement);
  const statusLabel = requiredElement("#reader-status", HTMLElement);
  const modeNote = requiredElement("#mode-note", HTMLElement);
  const liveLanguageControls = requiredElement("#live-language-controls", HTMLElement);
  const liveTargetLanguageSelect = requiredElement("#live-target-language", HTMLSelectElement);
  const chapterPosition = requiredElement("#chapter-position", HTMLElement);
  const previousChapter = requiredElement("#previous-chapter", HTMLButtonElement);
  const nextChapter = requiredElement("#next-chapter", HTMLButtonElement);
  const tocList = requiredElement("#toc-list", HTMLElement);
  const tocPanel = requiredElement("#toc-panel", HTMLElement);
  const tocToggle = requiredElement("#toc-toggle", HTMLButtonElement);
  const tocClose = requiredElement("#toc-close", HTMLButtonElement);
  const tocScrim = requiredElement("#toc-scrim", HTMLElement);
  const popover = requiredElement("#translation-popover", HTMLElement);
  const popoverContent = requiredElement("#popover-content", HTMLElement);
  const popoverLabel = requiredElement("#popover-label", HTMLElement);
  const popoverClose = requiredElement("#popover-close", HTMLButtonElement);
  const toast = requiredElement("#toast", HTMLElement);
  /** @type {Record<ReaderLanguage, HTMLElement>} */
  const progressLabels = {
    source: requiredElement("#source-progress", HTMLElement),
    target: requiredElement("#target-progress", HTMLElement),
  };

  /** @type {ReaderAppState} */
  const state = {
    mode: "offline",
    view: "both",
    offlineView: "both",
    activeId: null,
    syncLock: false,
    toastTimer: null,
    popoverAnchor: null,
    popoverReturnFocus: null,
    tocOpen: false,
    liveTargetLanguage: "English",
    liveRequestId: 0,
    liveController: null,
    chapterRequestId: 0,
    currentChapterId: null,
    currentTocId: null,
    resumePosition: null,
    readingPositionTimer: null,
    pendingReadingSegmentId: null,
    mathReady: false,
    mathQueue: Promise.resolve(),
    chunkPromises: new Map(),
    chaptersById: new Map(),
    chapterIndexes: new Map(),
    segmentChapters: new Map(),
    segmentIndexes: new Map(),
    tocLinks: new Map(),
    scrollFrames: { source: null, target: null },
    segmentLists: { source: [], target: [] },
    segmentMaps: { source: new Map(), target: new Map() },
  };

  /** @param {BookDocument} documentData */
  function initialize(documentData) {
    data = documentData;
    if (!Array.isArray(data.chapters) || !data.chapters.length || !Array.isArray(data.toc)) {
      showLoadError("The selected book data is incomplete.");
      return;
    }

    const offlineTranslationAvailable = hasOfflineTranslation();
    state.mode = offlineTranslationAvailable ? "offline" : "online";
    state.view = offlineTranslationAvailable ? "both" : "source";
    state.offlineView = offlineTranslationAvailable ? "both" : "source";
    shell.dataset.mode = state.mode;
    shell.dataset.view = state.view;

    document.title = data.readerTitle;
    requiredElement('meta[name="description"]', HTMLMetaElement).content = data.description;
    brandTitle.textContent = data.readerTitle;
    sourceHeading.textContent = data.sourceLabel;
    targetHeading.textContent = data.targetLabel || "Translation";
    sourceViewButton.textContent = data.sourceLabel;
    targetViewButton.textContent = data.targetLabel || "Translation";
    sourceContent.lang = data.sourceHtmlLang;
    targetContent.lang = data.targetHtmlLang || "";
    const supportedLiveLanguages = [...liveTargetLanguageSelect.options].map(
      (option) => option.value,
    );
    state.liveTargetLanguage =
      data.targetLanguage && supportedLiveLanguages.includes(data.targetLanguage)
        ? data.targetLanguage
        : "English";
    liveTargetLanguageSelect.value = state.liveTargetLanguage;
    indexChapters();
    buildToc();
    installEvents();
    updateTocAccessibility();
    updateControls();
    countLabel.textContent = `${data.segmentCount.toLocaleString()} ${offlineTranslationAvailable ? "aligned segments" : "segments"}`;
    statusLabel.textContent = "Loading chapter";

    const hashMatch = location.hash.match(/^#seg=(.+)$/);
    const requestedSegment = hashMatch ? decodeURIComponent(hashMatch[1]) : null;
    state.resumePosition = requestedSegment ? null : savedReadingPosition();
    const initialChapterId = requestedSegment
      ? state.segmentChapters.get(requestedSegment)
      : state.resumePosition?.chapterId || data.initialChapterId;
    if (!initialChapterId) {
      showLoadError("The selected chapter could not be found.");
      return;
    }
    void loadChapter(initialChapterId, requestedSegment);
  }

  function hasOfflineTranslation() {
    return data.hasOfflineTranslation !== false;
  }

  function indexChapters() {
    data.chapters.forEach((chapter, chapterIndex) => {
      state.chaptersById.set(chapter.id, chapter);
      state.chapterIndexes.set(chapter.id, chapterIndex);
      chapter.segmentIds.forEach((segmentId) => {
        if (state.segmentChapters.has(segmentId)) {
          throw new Error(`Duplicate segment ID in chapter metadata: ${segmentId}`);
        }
        state.segmentChapters.set(segmentId, chapter.id);
        state.segmentIndexes.set(segmentId, state.segmentIndexes.size);
      });
    });
  }

  /**
   * @param {ReaderLanguage} language
   * @param {HTMLElement} container
   */
  function prepareSegments(language, container) {
    const segments = matchingElements(container, ".segment[data-seg]", HTMLElement);
    /** @type {Map<string, HTMLElement>} */
    const map = new Map();

    segments.forEach((segment) => {
      const id = segment.dataset.seg;
      if (!id || map.has(id)) {
        throw new Error(`Invalid or duplicate segment ID in ${language}: ${id || "(missing)"}`);
      }
      map.set(id, segment);
      segment.dataset.plainText = normalizeText(segment.textContent);
      segment.tabIndex = 0;
      const hasInteractiveChild = Boolean(
        segment.querySelector("a, button, input, select, textarea, [tabindex]"),
      );
      segment.setAttribute("role", hasInteractiveChild ? "group" : "button");
      if (!hasOfflineTranslation() && language === "source") {
        segment.setAttribute("aria-label", `Translate ${data.sourceLanguage} sentence`);
      } else {
        const counterpartLabel =
          language === "source" ? data.targetLabel || "translation" : data.sourceLabel;
        segment.setAttribute("aria-label", `Show ${counterpartLabel} counterpart`);
      }
    });

    state.segmentLists[language] = segments;
    state.segmentMaps[language] = map;
  }

  function validateAlignment() {
    const sourceIds = state.segmentLists.source.map((segment) => segment.dataset.seg);
    const targetIds = state.segmentLists.target.map((segment) => segment.dataset.seg);
    const expectedIds = state.currentChapterId
      ? state.chaptersById.get(state.currentChapterId)?.segmentIds || []
      : [];
    const mismatch =
      sourceIds.length !== targetIds.length ||
      sourceIds.some((id, index) => id !== targetIds[index]) ||
      sourceIds.length !== expectedIds.length ||
      sourceIds.some((id, index) => id !== expectedIds[index]);
    if (mismatch) {
      showToast(
        "The bilingual files have mismatched sentence IDs. Some alignment features may be unavailable.",
        7000,
      );
    }
  }

  function buildToc() {
    const fragment = document.createDocumentFragment();

    data.toc.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `toc-link level-${entry.level}`;
      button.dataset.seg = entry.segmentId;
      button.textContent = entry.title;
      button.addEventListener("click", () => {
        void navigateToSegment(entry.segmentId, true);
        closeToc();
      });
      state.tocLinks.set(entry.segmentId, button);
      fragment.append(button);
    });

    tocList.replaceChildren(fragment);
  }

  function installEvents() {
    matchingElements(document, "[data-mode-choice]", HTMLButtonElement).forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.modeChoice));
    });

    matchingElements(document, "[data-view-choice]", HTMLButtonElement).forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.viewChoice));
    });

    liveTargetLanguageSelect.addEventListener("change", () => {
      setLiveTargetLanguage(liveTargetLanguageSelect.value);
    });

    [sourceContent, targetContent].forEach((container) => {
      container.addEventListener("click", onSegmentActivation);
      container.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        if (!(event.target instanceof Element)) return;
        const segment = event.target.closest(".segment[data-seg]");
        if (!(segment instanceof HTMLElement) || event.target !== segment) return;
        event.preventDefault();
        activateSegment(segment, container === sourceContent ? "source" : "target");
      });
    });

    sourceScroll.addEventListener("scroll", () => onPaneScroll("source"), { passive: true });
    targetScroll.addEventListener("scroll", () => onPaneScroll("target"), { passive: true });

    previousChapter.addEventListener("click", () => navigateChapter(-1));
    nextChapter.addEventListener("click", () => navigateChapter(1));

    popoverClose.addEventListener("click", () => hidePopover(true));
    tocToggle.addEventListener("click", openToc);
    tocClose.addEventListener("click", () => closeToc(true));
    tocScrim.addEventListener("click", () => closeToc(true));

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hidePopover(true);
        closeToc(true);
      }
    });

    window.addEventListener("resize", () => {
      if (!popover.hidden && state.popoverAnchor) positionPopover(state.popoverAnchor);
      if (window.innerWidth > 1050) closeToc(false);
      updateTocAccessibility();
    });

    window.addEventListener("mathjax-ready", () => {
      state.mathReady = true;
      void typesetCurrentChapter(state.chapterRequestId);
    });

    window.addEventListener("pagehide", flushReadingPosition);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") flushReadingPosition();
    });
  }

  /**
   * @param {string} chapterId
   * @param {ReaderLanguage} language
   */
  function chunkKey(chapterId, language) {
    return `${data.slug}:${chapterId}:${language}`;
  }

  /**
   * @param {BookChapter} chapter
   * @param {ReaderLanguage} language
   * @returns {Promise<BookChunk>}
   */
  function loadChunk(chapter, language) {
    const key = chunkKey(chapter.id, language);
    const loaded = window.BOOK_VIEWER_CHUNKS?.[key];
    if (loaded) return Promise.resolve(validateChunk(loaded, chapter.id, language));
    const pending = state.chunkPromises.get(key);
    if (pending) return pending;

    const dataFile = language === "source" ? chapter.sourceDataFile : chapter.targetDataFile;
    if (!dataFile) {
      return Promise.reject(new Error(`The ${language} chapter data is not available.`));
    }
    /** @type {Promise<BookChunk>} */
    const promise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = dataFile;
      script.onload = () => {
        script.remove();
        try {
          const payload = window.BOOK_VIEWER_CHUNKS?.[key];
          resolve(validateChunk(payload, chapter.id, language));
        } catch (error) {
          reject(error);
        }
      };
      script.onerror = () => {
        script.remove();
        reject(new Error(`The ${language} data for '${chapter.sourceTitle}' could not be loaded.`));
      };
      document.head.append(script);
    }).finally(() => {
      state.chunkPromises.delete(key);
    });
    state.chunkPromises.set(key, promise);
    return promise;
  }

  /**
   * @param {BookChunk | undefined} payload
   * @param {string} chapterId
   * @param {ReaderLanguage} language
   * @returns {BookChunk}
   */
  function validateChunk(payload, chapterId, language) {
    if (
      !payload ||
      payload.schemaVersion !== data.schemaVersion ||
      payload.slug !== data.slug ||
      payload.chapterId !== chapterId ||
      payload.language !== language ||
      !payload.html
    ) {
      throw new Error(`The ${language} chapter data is missing or incompatible.`);
    }
    return payload;
  }

  /**
   * @param {string} chapterId
   * @param {string | null} [segmentId]
   */
  async function loadChapter(chapterId, segmentId = null) {
    const chapter = state.chaptersById.get(chapterId);
    if (!chapter) {
      showToast("The requested chapter is not available.");
      return;
    }
    if (state.currentChapterId === chapterId) {
      if (segmentId) navigateWithinChapter(segmentId, true, true);
      return;
    }

    const resumePosition =
      state.resumePosition?.chapterId === chapterId ? state.resumePosition : null;
    state.resumePosition = null;
    const destinationSegmentId = segmentId || resumePosition?.segmentId || chapter.segmentIds[0];

    const requestId = ++state.chapterRequestId;
    shell.classList.add("is-loading-chapter");
    shell.setAttribute("aria-busy", "true");
    statusLabel.textContent = "Loading chapter";
    cancelLiveTranslation();

    try {
      const sourceChunkPromise = loadChunk(chapter, "source");
      const targetChunkPromise = hasOfflineTranslation()
        ? loadChunk(chapter, "target")
        : Promise.resolve(null);
      const [sourceChunk, targetChunk] = await Promise.all([
        sourceChunkPromise,
        targetChunkPromise,
      ]);
      await state.mathQueue.catch(() => {});
      if (requestId !== state.chapterRequestId) return;

      window.MathJax?.typesetClear?.(currentContentElements());
      sourceContent.innerHTML = sourceChunk.html;
      targetContent.innerHTML = targetChunk?.html || "";
      sourceContent.querySelectorAll("img").forEach(prepareImage);
      if (targetChunk) targetContent.querySelectorAll("img").forEach(prepareImage);
      state.currentChapterId = chapterId;
      state.activeId = null;
      prepareSegments("source", sourceContent);
      if (targetChunk) {
        prepareSegments("target", targetContent);
        validateAlignment();
      } else {
        state.segmentLists.target = [];
        state.segmentMaps.target = new Map();
      }
      sourceScroll.scrollTop = 0;
      targetScroll.scrollTop = 0;
      updateChapterControls();
      updateCurrentTocForSegment(destinationSegmentId);
      shell.classList.remove("is-loading-chapter");
      shell.removeAttribute("aria-busy");
      updateModeCopy();

      await typesetCurrentChapter(requestId);
      if (requestId !== state.chapterRequestId) return;
      await nextFrame();
      if (!restoreReadingPosition(resumePosition)) {
        navigateWithinChapter(destinationSegmentId, false, Boolean(segmentId));
      }
      updateVisibleProgress();
      scheduleReadingPosition(destinationSegmentId);
      prefetchAdjacentChapters(state.chapterIndexes.get(chapter.id));
    } catch (error) {
      if (requestId !== state.chapterRequestId) return;
      shell.classList.remove("is-loading-chapter");
      shell.removeAttribute("aria-busy");
      showLoadError(error instanceof Error ? error.message : "The chapter could not be loaded.");
    }
  }

  /** @param {HTMLImageElement} image */
  function prepareImage(image) {
    image.loading = "lazy";
    image.decoding = "async";
  }

  /**
   * @param {number} requestId
   * @returns {Promise<void>}
   */
  function typesetCurrentChapter(requestId) {
    const mathJax = window.MathJax;
    const typesetPromise = mathJax?.typesetPromise;
    if (!state.mathReady || !typesetPromise) return Promise.resolve();
    const chapterId = state.currentChapterId;
    state.mathQueue = state.mathQueue
      .catch(() => {})
      .then(async () => {
        if (requestId !== state.chapterRequestId || chapterId !== state.currentChapterId) return;
        const elements = currentContentElements();
        mathJax.typesetClear?.(elements);
        await typesetPromise(elements);
      })
      .catch(() => {
        showToast("Some mathematical notation could not be rendered.");
      });
    return state.mathQueue;
  }

  /** @returns {HTMLElement[]} */
  function currentContentElements() {
    return hasOfflineTranslation() ? [sourceContent, targetContent] : [sourceContent];
  }

  /** @returns {Promise<void>} */
  function nextFrame() {
    return new Promise((resolve) => requestAnimationFrame(() => resolve()));
  }

  /** @param {number | undefined} chapterIndex */
  function prefetchAdjacentChapters(chapterIndex) {
    if (chapterIndex === undefined) return;
    const prefetch = () => {
      [chapterIndex - 1, chapterIndex + 1].forEach((index) => {
        const chapter = data.chapters[index];
        if (!chapter) return;
        void loadChunk(chapter, "source").catch(() => {});
        if (hasOfflineTranslation()) void loadChunk(chapter, "target").catch(() => {});
      });
    };
    if (window.requestIdleCallback) {
      window.requestIdleCallback(prefetch, { timeout: 1500 });
    } else {
      window.setTimeout(prefetch, 250);
    }
  }

  /** @param {number} direction */
  function navigateChapter(direction) {
    if (!state.currentChapterId) return;
    const current = state.chaptersById.get(state.currentChapterId);
    if (!current) return;
    const currentIndex = state.chapterIndexes.get(current.id);
    if (currentIndex === undefined) return;
    const chapter = data.chapters[currentIndex + direction];
    if (!chapter) return;
    void loadChapter(chapter.id, chapter.segmentIds[0]);
  }

  function updateChapterControls() {
    if (!state.currentChapterId) return;
    const chapter = state.chaptersById.get(state.currentChapterId);
    if (!chapter) return;
    const chapterIndex = state.chapterIndexes.get(chapter.id);
    if (chapterIndex === undefined) return;
    chapterPosition.textContent = `${chapterIndex + 1} / ${data.chapters.length}`;
    chapterPosition.title = chapter.targetTitle
      ? `${chapter.sourceTitle} / ${chapter.targetTitle}`
      : chapter.sourceTitle;
    previousChapter.disabled = chapterIndex === 0;
    nextChapter.disabled = chapterIndex === data.chapters.length - 1;
  }

  /** @param {MouseEvent} event */
  function onSegmentActivation(event) {
    if (!(event.target instanceof Element)) return;
    const segment = event.target.closest(".segment[data-seg]");
    if (!(segment instanceof HTMLElement)) return;
    if (event.target !== segment && event.target.closest("a, button, input, select, textarea"))
      return;
    const language = event.currentTarget === sourceContent ? "source" : "target";
    activateSegment(segment, language);
  }

  /**
   * @param {HTMLElement} segment
   * @param {ReaderLanguage} language
   */
  function activateSegment(segment, language) {
    const id = segment.dataset.seg;
    if (!id) return;
    setActiveSegment(id);

    if (state.mode === "online") {
      if (language !== "source") return;
      requestLiveTranslation(segment);
      return;
    }

    if (state.view === "both" && window.innerWidth > 780) {
      alignCounterpart(language, id, segment, true);
      hidePopover(false);
    } else {
      const otherLanguage = language === "source" ? "target" : "source";
      const counterpart = state.segmentMaps[otherLanguage].get(id);
      if (!counterpart) {
        showToast("No mapped counterpart was found for this segment.");
        return;
      }
      const label =
        otherLanguage === "target"
          ? `${data.targetLabel || "Offline"} translation`
          : `${data.sourceLabel} source`;
      showPopover(segment, label, counterpart.innerHTML, true);
    }
  }

  /** @param {string} id */
  function setActiveSegment(id) {
    if (state.activeId) {
      state.segmentMaps.source.get(state.activeId)?.classList.remove("is-active");
      state.segmentMaps.target.get(state.activeId)?.classList.remove("is-active");
    }
    state.activeId = id;
    state.segmentMaps.source.get(id)?.classList.add("is-active");
    state.segmentMaps.target.get(id)?.classList.add("is-active");
    history.replaceState(null, "", `#seg=${encodeURIComponent(id)}`);
    scheduleReadingPosition(id);
  }

  /** @param {string | undefined} mode */
  function setMode(mode) {
    if (mode !== "offline" && mode !== "online") return;
    if (mode === "offline" && !hasOfflineTranslation()) return;
    if (state.mode === mode) return;

    hidePopover(false);
    cancelLiveTranslation();
    state.mode = mode;
    shell.dataset.mode = mode;

    if (mode === "online") {
      state.offlineView = state.view;
      applyView("source");
    } else {
      applyView(state.offlineView || "both");
    }

    updateModeCopy();
    updateControls();
    requestAnimationFrame(updateVisibleProgress);
  }

  /** @param {string} language */
  function setLiveTargetLanguage(language) {
    const supported = [...liveTargetLanguageSelect.options].some(
      (option) => option.value === language,
    );
    if (!supported) {
      liveTargetLanguageSelect.value = state.liveTargetLanguage;
      return;
    }
    if (language === state.liveTargetLanguage) return;

    cancelLiveTranslation();
    hidePopover(false);
    state.liveTargetLanguage = language;
    updateModeCopy();
  }

  function updateModeCopy() {
    if (state.mode === "online") {
      statusLabel.textContent = `Live translation to ${state.liveTargetLanguage}`;
      modeNote.textContent = `Click a ${data.sourceLanguage} sentence to translate it into ${state.liveTargetLanguage} with nearby context. Live mode requires the reader server and a configured Chat Completions service.`;
      return;
    }
    statusLabel.textContent = "Offline edition";
    modeNote.textContent =
      "Scroll either column. Click a sentence to align and highlight its counterpart.";
  }

  /** @param {string | undefined} view */
  function setView(view) {
    if (state.mode === "online") return;
    if (view !== "both" && view !== "source" && view !== "target") return;

    applyView(view);
    hidePopover(false);
    updateControls();
    requestAnimationFrame(updateVisibleProgress);
  }

  /** @param {ReaderView} view */
  function applyView(view) {
    state.view = view;
    if (state.mode === "offline") state.offlineView = view;
    shell.dataset.view = view;
  }

  function updateControls() {
    matchingElements(document, "[data-mode-choice]", HTMLButtonElement).forEach((button) => {
      const selected = button.dataset.modeChoice === state.mode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.disabled = button.dataset.modeChoice === "offline" && !hasOfflineTranslation();
    });

    matchingElements(document, "[data-view-choice]", HTMLButtonElement).forEach((button) => {
      const selected = button.dataset.viewChoice === state.view;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.disabled = state.mode === "online";
    });
    liveLanguageControls.hidden = state.mode !== "online";
  }

  /** @param {ReaderLanguage} language */
  function onPaneScroll(language) {
    if (state.scrollFrames[language]) return;
    state.scrollFrames[language] = requestAnimationFrame(() => {
      state.scrollFrames[language] = null;
      updateProgress(language);
      hidePopover(false);
      const anchor = firstVisibleSegment(language);
      if (language === "source" && anchor) updateCurrentTocForSegment(anchor.dataset.seg);
      scheduleReadingPosition(anchor?.dataset.seg || null);

      if (
        state.mode !== "offline" ||
        state.view !== "both" ||
        window.innerWidth <= 780 ||
        state.syncLock ||
        !anchor
      )
        return;
      syncFrom(language, anchor);
    });
  }

  /**
   * @param {ReaderLanguage} language
   * @returns {HTMLElement | null}
   */
  function firstVisibleSegment(language) {
    const scroller = language === "source" ? sourceScroll : targetScroll;
    const segments = state.segmentLists[language];
    if (!segments.length) return null;
    const paneTop = scroller.getBoundingClientRect().top + 8;
    let low = 0;
    let high = segments.length - 1;
    let firstVisible = segments[high];

    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      const segment = segments[middle];
      if (segment.getBoundingClientRect().bottom > paneTop) {
        firstVisible = segment;
        high = middle - 1;
      } else {
        low = middle + 1;
      }
    }
    return firstVisible;
  }

  /** @returns {ReadingPosition | null} */
  function savedReadingPosition() {
    const saved = window.BookViewerPreferences.read(data.slug);
    const chapterId = typeof saved.chapterId === "string" ? saved.chapterId : null;
    if (!chapterId || !state.chaptersById.has(chapterId)) return null;

    const chapter = state.chaptersById.get(chapterId);
    if (!chapter) return null;
    const segmentId =
      typeof saved.segmentId === "string" &&
      state.segmentChapters.get(saved.segmentId) === chapterId
        ? saved.segmentId
        : chapter.segmentIds[0];
    if (!segmentId) return null;
    const sourceScrollTop = isFiniteNumber(saved.sourceScrollTop)
      ? Math.max(0, saved.sourceScrollTop)
      : null;
    const targetScrollTop = isFiniteNumber(saved.targetScrollTop)
      ? Math.max(0, saved.targetScrollTop)
      : null;

    return { chapterId, segmentId, sourceScrollTop, targetScrollTop };
  }

  /** @param {ReadingPosition | null} position */
  function restoreReadingPosition(position) {
    if (!position) return false;
    const sourceScrollTop = position.sourceScrollTop;
    const targetScrollTop = position.targetScrollTop;
    const hasSourcePosition = isFiniteNumber(sourceScrollTop);
    const hasTargetPosition = isFiniteNumber(targetScrollTop);
    if (!hasSourcePosition && !hasTargetPosition) return false;

    state.syncLock = true;
    if (hasSourcePosition) sourceScroll.scrollTop = sourceScrollTop;
    if (hasOfflineTranslation() && hasTargetPosition) targetScroll.scrollTop = targetScrollTop;
    window.setTimeout(() => {
      state.syncLock = false;
    }, 50);
    return true;
  }

  /** @param {string | null} segmentId */
  function scheduleReadingPosition(segmentId) {
    if (segmentId) state.pendingReadingSegmentId = segmentId;
    if (state.readingPositionTimer !== null) {
      window.clearTimeout(state.readingPositionTimer);
    }
    state.readingPositionTimer = window.setTimeout(flushReadingPosition, 250);
  }

  function flushReadingPosition() {
    if (state.readingPositionTimer !== null) {
      window.clearTimeout(state.readingPositionTimer);
      state.readingPositionTimer = null;
    }
    if (!data || !state.currentChapterId) return;

    const chapter = state.chaptersById.get(state.currentChapterId);
    if (!chapter) return;
    let segmentId = state.pendingReadingSegmentId;
    if (!segmentId || state.segmentChapters.get(segmentId) !== state.currentChapterId) {
      const visibleLanguage = state.view === "target" ? "target" : "source";
      segmentId = firstVisibleSegment(visibleLanguage)?.dataset.seg || chapter.segmentIds[0];
    }
    state.pendingReadingSegmentId = null;
    window.BookViewerPreferences.savePosition(data.slug, {
      chapterId: state.currentChapterId,
      segmentId,
      progressPercent: readingProgressPercent(segmentId),
      sourceScrollTop: sourceScroll.scrollTop,
      targetScrollTop: hasOfflineTranslation() ? targetScroll.scrollTop : null,
    });
  }

  /** @param {string} segmentId */
  function readingProgressPercent(segmentId) {
    const segmentIndex = state.segmentIndexes.get(segmentId);
    if (segmentIndex === undefined || data.segmentCount <= 1) return 0;
    return Math.round((segmentIndex / (data.segmentCount - 1)) * 100);
  }

  /**
   * @param {ReaderLanguage} language
   * @param {HTMLElement} anchor
   */
  function syncFrom(language, anchor) {
    const originScroller = language === "source" ? sourceScroll : targetScroll;
    const counterpartLanguage = language === "source" ? "target" : "source";
    const destinationScroller = counterpartLanguage === "source" ? sourceScroll : targetScroll;
    const originTop = originScroller.getBoundingClientRect().top + 8;
    const segmentId = anchor.dataset.seg;
    if (!segmentId) return;
    const target = state.segmentMaps[counterpartLanguage].get(segmentId);
    if (!target) return;

    const relativeTop = anchor.getBoundingClientRect().top - originTop;
    const targetTop = destinationScroller.getBoundingClientRect().top + 8;
    state.syncLock = true;
    destinationScroller.scrollTop += target.getBoundingClientRect().top - targetTop - relativeTop;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        state.syncLock = false;
      });
    });
  }

  /**
   * @param {ReaderLanguage} language
   * @param {string} id
   * @param {HTMLElement} sourceElement
   * @param {boolean} smooth
   */
  function alignCounterpart(language, id, sourceElement, smooth) {
    const targetLanguage = language === "source" ? "target" : "source";
    const originScroller = language === "source" ? sourceScroll : targetScroll;
    const destinationScroller = targetLanguage === "source" ? sourceScroll : targetScroll;
    const target = state.segmentMaps[targetLanguage].get(id);
    if (!target) return;

    const sourceOffset =
      sourceElement.getBoundingClientRect().top - originScroller.getBoundingClientRect().top;
    const targetOffset =
      target.getBoundingClientRect().top - destinationScroller.getBoundingClientRect().top;
    state.syncLock = true;
    destinationScroller.scrollTo({
      top: destinationScroller.scrollTop + targetOffset - sourceOffset,
      behavior: smooth ? "smooth" : "auto",
    });
    window.setTimeout(
      () => {
        state.syncLock = false;
      },
      smooth ? 450 : 40,
    );
  }

  /**
   * @param {string} id
   * @param {boolean} smooth
   */
  async function navigateToSegment(id, smooth) {
    const chapterId = state.segmentChapters.get(id);
    if (!chapterId) return;
    if (chapterId !== state.currentChapterId) {
      await loadChapter(chapterId, id);
      return;
    }
    navigateWithinChapter(id, smooth, true);
  }

  /**
   * @param {string} id
   * @param {boolean} smooth
   * @param {boolean} highlight
   */
  function navigateWithinChapter(id, smooth, highlight) {
    const sourceSegment = state.segmentMaps.source.get(id);
    const targetSegment = state.segmentMaps.target.get(id);
    if (!sourceSegment && !targetSegment) return;

    if (highlight) setActiveSegment(id);
    state.syncLock = true;

    if (state.view !== "target" && sourceSegment) {
      scrollElementIntoPane(sourceScroll, sourceSegment, smooth);
    }
    if (state.mode === "offline" && state.view !== "source" && targetSegment) {
      scrollElementIntoPane(targetScroll, targetSegment, smooth);
    }

    window.setTimeout(
      () => {
        state.syncLock = false;
      },
      smooth ? 500 : 50,
    );
  }

  /**
   * @param {HTMLElement} scroller
   * @param {HTMLElement} element
   * @param {boolean} smooth
   */
  function scrollElementIntoPane(scroller, element, smooth) {
    const top = element.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    scroller.scrollTo({
      top: scroller.scrollTop + top - 24,
      behavior: smooth ? "smooth" : "auto",
    });
  }

  /** @param {ReaderLanguage} language */
  function updateProgress(language) {
    const scroller = language === "source" ? sourceScroll : targetScroll;
    const denominator = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
    const percent = Math.round((scroller.scrollTop / denominator) * 100);
    progressLabels[language].textContent = `${Math.max(0, Math.min(100, percent))}%`;
  }

  function updateVisibleProgress() {
    if (state.view !== "target") updateProgress("source");
    if (hasOfflineTranslation() && state.mode === "offline" && state.view !== "source") {
      updateProgress("target");
    }
  }

  /** @param {string | null | undefined} segmentId */
  function updateCurrentTocForSegment(segmentId) {
    if (!segmentId) return;
    const segmentIndex = state.segmentIndexes.get(segmentId);
    if (segmentIndex === undefined) return;
    let low = 0;
    let high = data.toc.length - 1;
    let currentId = data.toc[0]?.segmentId || null;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      const entry = data.toc[middle];
      const entryIndex = state.segmentIndexes.get(entry.segmentId);
      if (entryIndex === undefined) return;
      if (entryIndex <= segmentIndex) {
        currentId = entry.segmentId;
        low = middle + 1;
      } else {
        high = middle - 1;
      }
    }
    if (currentId === state.currentTocId) return;
    if (state.currentTocId) state.tocLinks.get(state.currentTocId)?.classList.remove("is-current");
    if (currentId) state.tocLinks.get(currentId)?.classList.add("is-current");
    state.currentTocId = currentId;
  }

  /** @param {HTMLElement} segment */
  async function requestLiveTranslation(segment) {
    cancelLiveTranslation();
    const requestId = ++state.liveRequestId;

    if (location.protocol === "file:") {
      showPopover(
        segment,
        "Live translation unavailable",
        "<p>Run <code>uv run book-viewer-serve</code> and open the local HTTP address shown in the terminal to use live translation.</p>",
        false,
      );
      return;
    }

    const list = state.segmentLists.source;
    const index = list.indexOf(segment);
    const sentence = segment.dataset.plainText || normalizeText(segment.textContent);
    const before = list.slice(Math.max(0, index - 2), index).map(segmentText);
    const after = list.slice(index + 1, index + 3).map(segmentText);
    const targetLanguage = state.liveTargetLanguage;
    const cacheKey = `book-viewer-live:${data.slug}:${targetLanguage}:${segment.dataset.seg}:${simpleHash(JSON.stringify([sentence, before, after]))}`;
    const cached = storageGet(cacheKey);

    if (cached) {
      if (requestId === state.liveRequestId) showLiveTranslation(segment, targetLanguage, cached);
      return;
    }

    showPopover(
      segment,
      "Translating",
      '<p class="loading-copy">Requesting a context-aware translation...</p>',
      false,
    );
    const controller = new AbortController();
    state.liveController = controller;

    try {
      const response = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          sentence,
          before,
          after,
          source_language: data.sourceLanguage,
          target_language: targetLanguage,
        }),
      });
      const payload = /** @type {{ error?: string; translation?: string }} */ (
        await response.json().catch(() => ({}))
      );
      if (!response.ok)
        throw new Error(payload.error || `Translation request failed (${response.status})`);
      if (!payload.translation)
        throw new Error("The translation service returned an empty response.");
      storageSet(cacheKey, payload.translation);
      if (
        requestId === state.liveRequestId &&
        state.mode === "online" &&
        state.liveTargetLanguage === targetLanguage &&
        state.activeId === segment.dataset.seg
      ) {
        showLiveTranslation(segment, targetLanguage, payload.translation);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (requestId !== state.liveRequestId) return;
      const message = escapeHtml(
        error instanceof Error ? error.message : "Translation request failed.",
      );
      showPopover(segment, "Translation error", `<p>${message}</p>`, false);
    } finally {
      if (requestId === state.liveRequestId) state.liveController = null;
    }
  }

  function cancelLiveTranslation() {
    state.liveController?.abort();
    state.liveController = null;
    state.liveRequestId += 1;
  }

  /**
   * @param {HTMLElement} segment
   * @param {string} targetLanguage
   * @param {string} translation
   */
  function showLiveTranslation(segment, targetLanguage, translation) {
    const paragraph = document.createElement("p");
    paragraph.textContent = translation;
    showPopover(segment, `Live ${targetLanguage} translation`, paragraph.outerHTML, false);
  }

  /**
   * @param {HTMLElement} anchor
   * @param {string} label
   * @param {string} html
   * @param {boolean} alreadyTypeset
   */
  function showPopover(anchor, label, html, alreadyTypeset) {
    state.popoverAnchor = anchor;
    state.popoverReturnFocus = anchor;
    popoverLabel.textContent = label;
    popoverContent.innerHTML = html;
    popover.hidden = false;
    popover.style.visibility = "hidden";
    requestAnimationFrame(() => {
      positionPopover(anchor);
      popover.style.visibility = "visible";
      if (!alreadyTypeset) typesetElement(popoverContent);
      popoverClose.focus({ preventScroll: true });
    });
  }

  /** @param {HTMLElement} anchor */
  function positionPopover(anchor) {
    const anchorRect = anchor.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const margin = 12;
    let top = anchorRect.top - popoverRect.height - 10;
    if (top < margin)
      top = Math.min(window.innerHeight - popoverRect.height - margin, anchorRect.bottom + 10);
    let left = anchorRect.left + anchorRect.width / 2 - popoverRect.width / 2;
    left = Math.max(margin, Math.min(window.innerWidth - popoverRect.width - margin, left));
    popover.style.top = `${Math.max(margin, top)}px`;
    popover.style.left = `${left}px`;
  }

  function hidePopover(restoreFocus = false) {
    if (popover.hidden) return;
    popover.hidden = true;
    state.popoverAnchor = null;
    const returnFocus = state.popoverReturnFocus;
    state.popoverReturnFocus = null;
    if (restoreFocus && returnFocus?.isConnected) {
      returnFocus.focus({ preventScroll: true });
    }
  }

  function openToc() {
    if (window.innerWidth > 1050) return;
    state.tocOpen = true;
    tocPanel.classList.add("is-open");
    tocToggle.setAttribute("aria-expanded", "true");
    tocScrim.hidden = false;
    updateTocAccessibility();
    requestAnimationFrame(() => {
      const firstLink = tocList.querySelector(".toc-link");
      (firstLink instanceof HTMLElement ? firstLink : tocClose).focus({ preventScroll: true });
    });
  }

  function closeToc(restoreFocus = false) {
    const wasOpen = state.tocOpen;
    state.tocOpen = false;
    tocPanel.classList.remove("is-open");
    tocToggle.setAttribute("aria-expanded", "false");
    tocScrim.hidden = true;
    updateTocAccessibility();
    if (restoreFocus && wasOpen) tocToggle.focus({ preventScroll: true });
  }

  function updateTocAccessibility() {
    const closedMobileDrawer = window.innerWidth <= 1050 && !state.tocOpen;
    tocPanel.inert = closedMobileDrawer;
    tocPanel.setAttribute("aria-hidden", String(closedMobileDrawer));
  }

  /**
   * @param {string} message
   * @param {number} [duration]
   */
  function showToast(message, duration = 4200) {
    if (state.toastTimer !== null) window.clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, duration);
  }

  /** @param {HTMLElement} element */
  function typesetElement(element) {
    const mathJax = window.MathJax;
    const typesetPromise = mathJax?.typesetPromise;
    if (!state.mathReady || !typesetPromise) return;
    state.mathQueue = state.mathQueue
      .catch(() => {})
      .then(async () => {
        mathJax.typesetClear?.([element]);
        await typesetPromise([element]);
      })
      .catch(() => {
        showToast("Some mathematical notation could not be rendered.");
      });
  }

  /** @param {HTMLElement} element */
  function segmentText(element) {
    return element.dataset.plainText || normalizeText(element.textContent);
  }

  /** @param {unknown} value */
  function normalizeText(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  /** @param {string} value */
  function simpleHash(value) {
    let hash = 5381;
    for (let index = 0; index < value.length; index += 1) {
      hash = ((hash << 5) + hash) ^ value.charCodeAt(index);
    }
    return (hash >>> 0).toString(36);
  }

  /** @param {string} key */
  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  /**
   * @param {string} key
   * @param {string} value
   */
  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // The viewer remains usable when browser storage is unavailable or full.
    }
  }

  /** @param {string} value */
  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value;
    return element.innerHTML;
  }

  /** @param {string} message */
  function showLoadError(message) {
    matchingElements(document, ".language-pane", HTMLElement).forEach((pane) => {
      pane.hidden = true;
    });
    emptyStateMessage.textContent = message;
    emptyState.hidden = false;
    countLabel.textContent = "No reader data";
  }

  /**
   * @param {unknown} value
   * @returns {value is number}
   */
  function isFiniteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  /**
   * @template {Element} ElementType
   * @param {string} selector
   * @param {new () => ElementType} elementType
   * @returns {ElementType}
   */
  function requiredElement(selector, elementType) {
    const element = document.querySelector(selector);
    if (!(element instanceof elementType)) {
      throw new Error(`Required element '${selector}' is missing or has the wrong type.`);
    }
    return element;
  }

  /**
   * @template {Element} ElementType
   * @param {ParentNode} root
   * @param {string} selector
   * @param {new () => ElementType} elementType
   * @returns {ElementType[]}
   */
  function matchingElements(root, selector, elementType) {
    return [...root.querySelectorAll(selector)].map((element) => {
      if (!(element instanceof elementType)) {
        throw new Error(`Element matching '${selector}' has the wrong type.`);
      }
      return element;
    });
  }

  window.BookViewer = Object.freeze({ initialize, showLoadError });
})();
