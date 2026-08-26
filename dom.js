(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: This file runs as a classic browser script.
  "use strict";

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

  window.BookViewerDom = Object.freeze({ requiredElement, matchingElements });
})();
