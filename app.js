(() => {
  "use strict";

  let data = null;
  const shell = document.querySelector(".app-shell");
  const sourceContent = document.querySelector("#source-content");
  const targetContent = document.querySelector("#target-content");
  const sourceScroll = document.querySelector("#source-scroll");
  const targetScroll = document.querySelector("#target-scroll");
  const emptyState = document.querySelector("#empty-state");
  const emptyStateMessage = document.querySelector("#empty-state-message");
  const brandTitle = document.querySelector("#brand-title");
  const sourceHeading = document.querySelector("#source-heading");
  const targetHeading = document.querySelector("#target-heading");
  const sourceViewButton = document.querySelector('[data-view-choice="source"]');
  const targetViewButton = document.querySelector('[data-view-choice="target"]');
  const countLabel = document.querySelector("#segment-count");
  const statusLabel = document.querySelector("#reader-status");
  const modeNote = document.querySelector("#mode-note");
  const tocList = document.querySelector("#toc-list");
  const tocPanel = document.querySelector("#toc-panel");
  const tocToggle = document.querySelector("#toc-toggle");
  const tocClose = document.querySelector("#toc-close");
  const tocScrim = document.querySelector("#toc-scrim");
  const popover = document.querySelector("#translation-popover");
  const popoverContent = document.querySelector("#popover-content");
  const popoverLabel = document.querySelector("#popover-label");
  const popoverClose = document.querySelector("#popover-close");
  const toast = document.querySelector("#toast");
  const progressLabels = {
    source: document.querySelector("#source-progress"),
    target: document.querySelector("#target-progress")
  };

  const state = {
    mode: "offline",
    view: "both",
    offlineView: "both",
    activeId: null,
    syncLock: false,
    syncFrame: null,
    toastTimer: null,
    popoverAnchor: null,
    popoverReturnFocus: null,
    tocOpen: false,
    liveRequestId: 0,
    liveController: null,
    segmentLists: { source: [], target: [] },
    segmentMaps: { source: new Map(), target: new Map() }
  };

  function initialize(documentData) {
    data = documentData;
    if (!data.sourceHtml || !data.targetHtml) {
      showLoadError("The selected book data is incomplete.");
      return;
    }

    document.title = data.readerTitle;
    document.querySelector('meta[name="description"]').content = data.description;
    brandTitle.textContent = data.readerTitle;
    sourceHeading.textContent = data.sourceLabel;
    targetHeading.textContent = data.targetLabel;
    sourceViewButton.textContent = data.sourceLabel;
    targetViewButton.textContent = data.targetLabel;
    sourceContent.lang = data.sourceHtmlLang;
    targetContent.lang = data.targetHtmlLang;
    sourceContent.innerHTML = data.sourceHtml;
    targetContent.innerHTML = data.targetHtml;
    prepareSegments("source", sourceContent);
    prepareSegments("target", targetContent);
    validateAlignment();
    buildToc();
    installEvents();
    updateTocAccessibility();
    updateControls();
    updateProgress("source");
    updateProgress("target");

    const count = state.segmentLists.source.length;
    countLabel.textContent = `${count.toLocaleString()} aligned segments`;
    statusLabel.textContent = "Offline edition";

    const hashMatch = location.hash.match(/^#seg=(.+)$/);
    if (hashMatch) {
      const segmentId = decodeURIComponent(hashMatch[1]);
      requestAnimationFrame(() => navigateToSegment(segmentId, false));
    }

    typesetDocument();
  }

  function prepareSegments(language, container) {
    const segments = [...container.querySelectorAll(".segment[data-seg]")];
    const map = new Map();

    segments.forEach((segment) => {
      const id = segment.dataset.seg;
      if (!id || map.has(id)) {
        throw new Error(`Invalid or duplicate segment ID in ${language}: ${id || "(missing)"}`);
      }
      map.set(id, segment);
      segment.dataset.plainText = normalizeText(segment.textContent);
      segment.tabIndex = 0;
      const hasInteractiveChild = Boolean(segment.querySelector("a, button, input, select, textarea, [tabindex]"));
      segment.setAttribute("role", hasInteractiveChild ? "group" : "button");
      const counterpartLabel = language === "source" ? data.targetLabel : data.sourceLabel;
      segment.setAttribute("aria-label", `Show ${counterpartLabel} counterpart`);
    });

    state.segmentLists[language] = segments;
    state.segmentMaps[language] = map;
  }

  function validateAlignment() {
    const sourceIds = state.segmentLists.source.map((segment) => segment.dataset.seg);
    const targetIds = state.segmentLists.target.map((segment) => segment.dataset.seg);
    const mismatch = sourceIds.length !== targetIds.length || sourceIds.some((id, index) => id !== targetIds[index]);
    if (mismatch) {
      showToast("The bilingual files have mismatched sentence IDs. Some alignment features may be unavailable.", 7000);
    }
  }

  function buildToc() {
    const headings = [...sourceContent.querySelectorAll("h1, h2, h3")];
    const fragment = document.createDocumentFragment();

    headings.forEach((heading) => {
      const segment = heading.querySelector(".segment[data-seg]");
      if (!segment) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `toc-link level-${heading.tagName.slice(1)}`;
      button.dataset.seg = segment.dataset.seg;
      button.textContent = normalizeText(segment.dataset.plainText || segment.textContent);
      button.addEventListener("click", () => {
        navigateToSegment(button.dataset.seg, true);
        closeToc();
      });
      fragment.append(button);
    });

    tocList.replaceChildren(fragment);
  }

  function installEvents() {
    document.querySelectorAll("[data-mode-choice]").forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.modeChoice));
    });

    document.querySelectorAll("[data-view-choice]").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.viewChoice));
    });

    [sourceContent, targetContent].forEach((container) => {
      container.addEventListener("click", onSegmentActivation);
      container.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const segment = event.target.closest(".segment[data-seg]");
        if (!segment || event.target !== segment) return;
        event.preventDefault();
        activateSegment(segment, container === sourceContent ? "source" : "target");
      });
    });

    sourceScroll.addEventListener("scroll", () => onPaneScroll("source"), { passive: true });
    targetScroll.addEventListener("scroll", () => onPaneScroll("target"), { passive: true });

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

    window.addEventListener("mathjax-ready", typesetDocument);
  }

  function onSegmentActivation(event) {
    const segment = event.target.closest(".segment[data-seg]");
    if (!segment) return;
    if (event.target !== segment && event.target.closest("a, button, input, select, textarea")) return;
    const language = event.currentTarget === sourceContent ? "source" : "target";
    activateSegment(segment, language);
  }

  function activateSegment(segment, language) {
    const id = segment.dataset.seg;
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
      const label = otherLanguage === "target" ? `${data.targetLabel} translation` : `${data.sourceLabel} source`;
      showPopover(segment, label, counterpart.innerHTML, true);
    }
  }

  function setActiveSegment(id) {
    if (state.activeId) {
      document.querySelectorAll(`.segment[data-seg="${cssEscape(state.activeId)}"]`).forEach((element) => {
        element.classList.remove("is-active");
      });
    }
    state.activeId = id;
    document.querySelectorAll(`.segment[data-seg="${cssEscape(id)}"]`).forEach((element) => {
      element.classList.add("is-active");
    });
    history.replaceState(null, "", `#seg=${encodeURIComponent(id)}`);
  }

  function setMode(mode) {
    if (mode !== "offline" && mode !== "online") return;
    if (state.mode === mode) return;

    hidePopover(false);
    cancelLiveTranslation();
    state.mode = mode;
    shell.dataset.mode = mode;

    if (mode === "online") {
      state.offlineView = state.view;
      setView("source", true);
      statusLabel.textContent = "Live translation";
      modeNote.textContent = `Click a ${data.sourceLanguage} sentence to translate it with nearby context. Live mode requires the reader server and a configured Chat Completions service.`;
    } else {
      setView(state.offlineView || "both", true);
      statusLabel.textContent = "Offline edition";
      modeNote.textContent = "Scroll either column. Click a sentence to align and highlight its counterpart.";
    }

    updateControls();
  }

  function setView(view, forced = false) {
    if (!forced && state.mode === "online") return;
    if (!["both", "source", "target"].includes(view)) return;

    state.view = view;
    if (state.mode === "offline") state.offlineView = view;
    shell.dataset.view = view;
    hidePopover(false);
    updateControls();

    requestAnimationFrame(() => {
      updateProgress("source");
      updateProgress("target");
      if (state.activeId) navigateToSegment(state.activeId, false);
    });
  }

  function updateControls() {
    document.querySelectorAll("[data-mode-choice]").forEach((button) => {
      const selected = button.dataset.modeChoice === state.mode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });

    document.querySelectorAll("[data-view-choice]").forEach((button) => {
      const selected = button.dataset.viewChoice === state.view;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.disabled = state.mode === "online";
    });
  }

  function onPaneScroll(language) {
    updateProgress(language);
    hidePopover(false);
    updateCurrentToc(language);

    if (state.mode !== "offline" || state.view !== "both" || window.innerWidth <= 780 || state.syncLock) return;
    if (state.syncFrame) cancelAnimationFrame(state.syncFrame);
    state.syncFrame = requestAnimationFrame(() => syncFrom(language));
  }

  function syncFrom(language) {
    const originScroller = language === "source" ? sourceScroll : targetScroll;
    const counterpartLanguage = language === "source" ? "target" : "source";
    const destinationScroller = counterpartLanguage === "source" ? sourceScroll : targetScroll;
    const originSegments = state.segmentLists[language];
    const originTop = originScroller.getBoundingClientRect().top + 8;
    const anchor = originSegments.find((element) => element.getBoundingClientRect().bottom > originTop);

    if (!anchor) return;
    const target = state.segmentMaps[counterpartLanguage].get(anchor.dataset.seg);
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

  function alignCounterpart(language, id, sourceElement, smooth) {
    const targetLanguage = language === "source" ? "target" : "source";
    const originScroller = language === "source" ? sourceScroll : targetScroll;
    const destinationScroller = targetLanguage === "source" ? sourceScroll : targetScroll;
    const target = state.segmentMaps[targetLanguage].get(id);
    if (!target) return;

    const sourceOffset = sourceElement.getBoundingClientRect().top - originScroller.getBoundingClientRect().top;
    const targetOffset = target.getBoundingClientRect().top - destinationScroller.getBoundingClientRect().top;
    state.syncLock = true;
    destinationScroller.scrollTo({
      top: destinationScroller.scrollTop + targetOffset - sourceOffset,
      behavior: smooth ? "smooth" : "auto"
    });
    window.setTimeout(() => {
      state.syncLock = false;
    }, smooth ? 450 : 40);
  }

  function navigateToSegment(id, smooth) {
    const sourceSegment = state.segmentMaps.source.get(id);
    const targetSegment = state.segmentMaps.target.get(id);
    if (!sourceSegment && !targetSegment) return;

    setActiveSegment(id);
    state.syncLock = true;

    if (state.view !== "target" && sourceSegment) {
      scrollElementIntoPane(sourceScroll, sourceSegment, smooth);
    }
    if (state.mode === "offline" && state.view !== "source" && targetSegment) {
      scrollElementIntoPane(targetScroll, targetSegment, smooth);
    }

    window.setTimeout(() => {
      state.syncLock = false;
    }, smooth ? 500 : 50);
  }

  function scrollElementIntoPane(scroller, element, smooth) {
    const top = element.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    scroller.scrollTo({
      top: scroller.scrollTop + top - 24,
      behavior: smooth ? "smooth" : "auto"
    });
  }

  function updateProgress(language) {
    const scroller = language === "source" ? sourceScroll : targetScroll;
    const denominator = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
    const percent = Math.round((scroller.scrollTop / denominator) * 100);
    progressLabels[language].textContent = `${Math.max(0, Math.min(100, percent))}%`;
  }

  function updateCurrentToc(language) {
    if (language !== "source") return;
    const top = sourceScroll.getBoundingClientRect().top + 12;
    let currentId = null;
    [...sourceContent.querySelectorAll("h1, h2, h3")].forEach((heading) => {
      if (heading.getBoundingClientRect().top <= top) {
        currentId = heading.querySelector(".segment[data-seg]")?.dataset.seg || currentId;
      }
    });
    document.querySelectorAll(".toc-link").forEach((link) => {
      link.classList.toggle("is-current", Boolean(currentId && link.dataset.seg === currentId));
    });
  }

  async function requestLiveTranslation(segment) {
    cancelLiveTranslation();
    const requestId = ++state.liveRequestId;

    if (location.protocol === "file:") {
      showPopover(
        segment,
        "Live translation unavailable",
        "<p>Run <code>uv run book-viewer-serve</code> and open the local HTTP address shown in the terminal to use live translation.</p>",
        false
      );
      return;
    }

    const list = state.segmentLists.source;
    const index = list.indexOf(segment);
    const sentence = segment.dataset.plainText || normalizeText(segment.textContent);
    const before = list.slice(Math.max(0, index - 2), index).map(segmentText);
    const after = list.slice(index + 1, index + 3).map(segmentText);
    const cacheKey = `book-viewer-live:${data.slug}:${segment.dataset.seg}:${simpleHash(JSON.stringify([sentence, before, after]))}`;
    const cached = storageGet(cacheKey);

    if (cached) {
      if (requestId === state.liveRequestId) showLiveTranslation(segment, cached);
      return;
    }

    showPopover(segment, "Translating", "<p class=\"loading-copy\">Requesting a context-aware translation...</p>", false);
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
          target_language: data.targetLanguage
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Translation request failed (${response.status})`);
      if (!payload.translation) throw new Error("The translation service returned an empty response.");
      storageSet(cacheKey, payload.translation);
      if (requestId === state.liveRequestId && state.mode === "online" && state.activeId === segment.dataset.seg) {
        showLiveTranslation(segment, payload.translation);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (requestId !== state.liveRequestId) return;
      const message = escapeHtml(error instanceof Error ? error.message : "Translation request failed.");
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

  function showLiveTranslation(segment, translation) {
    const paragraph = document.createElement("p");
    paragraph.textContent = translation;
    showPopover(segment, `Live ${data.targetLabel} translation`, paragraph.outerHTML, false);
  }

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

  function positionPopover(anchor) {
    const anchorRect = anchor.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const margin = 12;
    let top = anchorRect.top - popoverRect.height - 10;
    if (top < margin) top = Math.min(window.innerHeight - popoverRect.height - margin, anchorRect.bottom + 10);
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
      (tocList.querySelector(".toc-link") || tocClose).focus({ preventScroll: true });
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

  function showToast(message, duration = 4200) {
    window.clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, duration);
  }

  function typesetDocument() {
    typesetElement(sourceContent);
    typesetElement(targetContent);
  }

  function typesetElement(element) {
    if (!window.MathJax?.typesetPromise) return;
    window.MathJax.typesetClear?.([element]);
    window.MathJax.typesetPromise([element]).catch(() => {
      showToast("Some mathematical notation could not be rendered.");
    });
  }

  function segmentText(element) {
    return element.dataset.plainText || normalizeText(element.textContent);
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function simpleHash(value) {
    let hash = 5381;
    for (let index = 0; index < value.length; index += 1) {
      hash = ((hash << 5) + hash) ^ value.charCodeAt(index);
    }
    return (hash >>> 0).toString(36);
  }

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Translation still works when browser storage is unavailable or full.
    }
  }

  function cssEscape(value) {
    if (window.CSS?.escape) return window.CSS.escape(value);
    return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value;
    return element.innerHTML;
  }

  function showLoadError(message) {
    document.querySelectorAll(".language-pane").forEach((pane) => {
      pane.hidden = true;
    });
    emptyStateMessage.textContent = message;
    emptyState.hidden = false;
    countLabel.textContent = "No reader data";
  }

  window.BookViewer = Object.freeze({ initialize, showLoadError });
})();
