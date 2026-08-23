(() => {
  "use strict";

  const data = window.PCP_DOCUMENT || {};
  const shell = document.querySelector(".app-shell");
  const jpContent = document.querySelector("#jp-content");
  const enContent = document.querySelector("#en-content");
  const jpScroll = document.querySelector("#jp-scroll");
  const enScroll = document.querySelector("#en-scroll");
  const emptyState = document.querySelector("#empty-state");
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
    jp: document.querySelector("#jp-progress"),
    en: document.querySelector("#en-progress")
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
    segmentLists: { jp: [], en: [] },
    segmentMaps: { jp: new Map(), en: new Map() }
  };

  function initialize() {
    if (!data.sourceHtml || !data.targetHtml) {
      document.querySelectorAll(".language-pane").forEach((pane) => {
        pane.hidden = true;
      });
      emptyState.hidden = false;
      countLabel.textContent = "No reader data";
      return;
    }

    jpContent.innerHTML = data.sourceHtml;
    enContent.innerHTML = data.targetHtml;
    prepareSegments("jp", jpContent);
    prepareSegments("en", enContent);
    validateAlignment();
    buildToc();
    installEvents();
    updateTocAccessibility();
    updateControls();
    updateProgress("jp");
    updateProgress("en");

    const count = state.segmentLists.jp.length;
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
      segment.setAttribute("aria-label", language === "jp" ? "Show English counterpart" : "Show Japanese counterpart");
    });

    state.segmentLists[language] = segments;
    state.segmentMaps[language] = map;
  }

  function validateAlignment() {
    const jpIds = state.segmentLists.jp.map((segment) => segment.dataset.seg);
    const enIds = state.segmentLists.en.map((segment) => segment.dataset.seg);
    const mismatch = jpIds.length !== enIds.length || jpIds.some((id, index) => id !== enIds[index]);
    if (mismatch) {
      showToast("The bilingual files have mismatched sentence IDs. Some alignment features may be unavailable.", 7000);
    }
  }

  function buildToc() {
    const headings = [...jpContent.querySelectorAll("h1, h2, h3")];
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

    [jpContent, enContent].forEach((container) => {
      container.addEventListener("click", onSegmentActivation);
      container.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const segment = event.target.closest(".segment[data-seg]");
        if (!segment || event.target !== segment) return;
        event.preventDefault();
        activateSegment(segment, container === jpContent ? "jp" : "en");
      });
    });

    jpScroll.addEventListener("scroll", () => onPaneScroll("jp"), { passive: true });
    enScroll.addEventListener("scroll", () => onPaneScroll("en"), { passive: true });

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
    const language = event.currentTarget === jpContent ? "jp" : "en";
    activateSegment(segment, language);
  }

  function activateSegment(segment, language) {
    const id = segment.dataset.seg;
    setActiveSegment(id);

    if (state.mode === "online") {
      if (language !== "jp") return;
      requestLiveTranslation(segment);
      return;
    }

    if (state.view === "both" && window.innerWidth > 780) {
      alignCounterpart(language, id, segment, true);
      hidePopover(false);
    } else {
      const otherLanguage = language === "jp" ? "en" : "jp";
      const counterpart = state.segmentMaps[otherLanguage].get(id);
      if (!counterpart) {
        showToast("No mapped counterpart was found for this segment.");
        return;
      }
      const label = otherLanguage === "en" ? "English translation" : "Japanese source";
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
      setView("jp", true);
      statusLabel.textContent = "Live translation";
      modeNote.textContent = "Click a Japanese sentence to translate it with nearby context. Live mode requires the reader server and llama.cpp SSH tunnel.";
    } else {
      setView(state.offlineView || "both", true);
      statusLabel.textContent = "Offline edition";
      modeNote.textContent = "Scroll either column. Click a sentence to align and highlight its counterpart.";
    }

    updateControls();
  }

  function setView(view, forced = false) {
    if (!forced && state.mode === "online") return;
    if (!["both", "jp", "en"].includes(view)) return;

    state.view = view;
    if (state.mode === "offline") state.offlineView = view;
    shell.dataset.view = view;
    hidePopover(false);
    updateControls();

    requestAnimationFrame(() => {
      updateProgress("jp");
      updateProgress("en");
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
    const sourceScroll = language === "jp" ? jpScroll : enScroll;
    const targetLanguage = language === "jp" ? "en" : "jp";
    const targetScroll = targetLanguage === "jp" ? jpScroll : enScroll;
    const sourceSegments = state.segmentLists[language];
    const sourceTop = sourceScroll.getBoundingClientRect().top + 8;
    const anchor = sourceSegments.find((element) => element.getBoundingClientRect().bottom > sourceTop);

    if (!anchor) return;
    const target = state.segmentMaps[targetLanguage].get(anchor.dataset.seg);
    if (!target) return;

    const relativeTop = anchor.getBoundingClientRect().top - sourceTop;
    const targetTop = targetScroll.getBoundingClientRect().top + 8;
    state.syncLock = true;
    targetScroll.scrollTop += target.getBoundingClientRect().top - targetTop - relativeTop;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        state.syncLock = false;
      });
    });
  }

  function alignCounterpart(language, id, sourceElement, smooth) {
    const targetLanguage = language === "jp" ? "en" : "jp";
    const sourceScroll = language === "jp" ? jpScroll : enScroll;
    const targetScroll = targetLanguage === "jp" ? jpScroll : enScroll;
    const target = state.segmentMaps[targetLanguage].get(id);
    if (!target) return;

    const sourceOffset = sourceElement.getBoundingClientRect().top - sourceScroll.getBoundingClientRect().top;
    const targetOffset = target.getBoundingClientRect().top - targetScroll.getBoundingClientRect().top;
    state.syncLock = true;
    targetScroll.scrollTo({
      top: targetScroll.scrollTop + targetOffset - sourceOffset,
      behavior: smooth ? "smooth" : "auto"
    });
    window.setTimeout(() => {
      state.syncLock = false;
    }, smooth ? 450 : 40);
  }

  function navigateToSegment(id, smooth) {
    const jpSegment = state.segmentMaps.jp.get(id);
    const enSegment = state.segmentMaps.en.get(id);
    if (!jpSegment && !enSegment) return;

    setActiveSegment(id);
    state.syncLock = true;

    if (state.view !== "en" && jpSegment) {
      scrollElementIntoPane(jpScroll, jpSegment, smooth);
    }
    if (state.mode === "offline" && state.view !== "jp" && enSegment) {
      scrollElementIntoPane(enScroll, enSegment, smooth);
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
    const scroller = language === "jp" ? jpScroll : enScroll;
    const denominator = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
    const percent = Math.round((scroller.scrollTop / denominator) * 100);
    progressLabels[language].textContent = `${Math.max(0, Math.min(100, percent))}%`;
  }

  function updateCurrentToc(language) {
    if (language !== "jp") return;
    const top = jpScroll.getBoundingClientRect().top + 12;
    let currentId = null;
    [...jpContent.querySelectorAll("h1, h2, h3")].forEach((heading) => {
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
        "<p>Start <code>server.py</code> and open the local HTTP address shown in the terminal to use live translation.</p>",
        false
      );
      return;
    }

    const list = state.segmentLists.jp;
    const index = list.indexOf(segment);
    const sentence = segment.dataset.plainText || normalizeText(segment.textContent);
    const before = list.slice(Math.max(0, index - 2), index).map(segmentText);
    const after = list.slice(index + 1, index + 3).map(segmentText);
    const cacheKey = `pcp-live:${segment.dataset.seg}:${simpleHash(JSON.stringify([sentence, before, after]))}`;
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
          source_language: "Japanese",
          target_language: "English"
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
    showPopover(segment, "Live English translation", paragraph.outerHTML, false);
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
    typesetElement(jpContent);
    typesetElement(enContent);
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

  initialize();
})();
