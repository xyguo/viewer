(() => {
  // biome-ignore lint/suspicious/noRedundantUseStrict: This file runs as a classic browser script.
  "use strict";

  const { matchingElements, requiredElement } = window.BookViewerDom;
  const SETTINGS_URL = "/api/settings";
  const dialog = requiredElement("#settings-dialog", HTMLDialogElement);
  const restartDialog = requiredElement("#settings-restart-dialog", HTMLDialogElement);
  const form = requiredElement("#settings-form", HTMLFormElement);
  const closeButton = requiredElement("#settings-close", HTMLButtonElement);
  const cancelButton = requiredElement("#settings-cancel", HTMLButtonElement);
  const saveButton = requiredElement("#settings-save", HTMLButtonElement);
  const restartButton = requiredElement("#settings-restart-dismiss", HTMLButtonElement);
  const alert = requiredElement("#settings-alert", HTMLElement);
  const loading = requiredElement("#settings-loading", HTMLElement);
  const groupsContainer = requiredElement("#settings-groups", HTMLElement);
  const changeSummary = requiredElement("#settings-change-summary", HTMLElement);
  const sourcePath = requiredElement("#settings-source-path", HTMLElement);
  const openButtons = matchingElements(document, "[data-settings-open]", HTMLButtonElement);

  /** @type {SettingsField[]} */
  let fields = [];
  /** @type {Map<string, HTMLInputElement>} */
  const inputs = new Map();
  /** @type {Set<string>} */
  const removals = new Set();

  if (location.protocol === "http:" || location.protocol === "https:") {
    openButtons.forEach((button) => {
      button.hidden = false;
      button.addEventListener("click", () => void openSettings());
    });
  }

  closeButton.addEventListener("click", () => dialog.close());
  cancelButton.addEventListener("click", () => dialog.close());
  restartButton.addEventListener("click", () => restartDialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  restartDialog.addEventListener("click", (event) => {
    if (event.target === restartDialog) restartDialog.close();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveSettings();
  });

  async function openSettings() {
    setAlert("", "neutral");
    loading.hidden = false;
    groupsContainer.hidden = true;
    saveButton.disabled = true;
    changeSummary.textContent = "No unsaved changes";
    if (!dialog.open) dialog.showModal();

    try {
      const response = await fetch(SETTINGS_URL, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload, "Settings could not be loaded."));
      if (!isSettingsDocument(payload)) throw new Error("The server returned invalid settings.");
      renderSettings(payload);
    } catch (error) {
      loading.hidden = true;
      setAlert(error instanceof Error ? error.message : "Settings could not be loaded.", "error");
    }
  }

  /** @param {SettingsDocument} documentData */
  function renderSettings(documentData) {
    fields = documentData.fields;
    sourcePath.textContent = documentData.source;
    inputs.clear();
    removals.clear();
    groupsContainer.replaceChildren();

    /** @type {Map<string, SettingsField[]>} */
    const groupedFields = new Map();
    fields.forEach((field) => {
      const groupFields = groupedFields.get(field.group) || [];
      groupFields.push(field);
      groupedFields.set(field.group, groupFields);
    });

    groupedFields.forEach((groupFields, groupName) => {
      const section = document.createElement("section");
      section.className = "settings-group";

      const heading = document.createElement("h3");
      heading.textContent = groupName;
      section.append(heading);

      groupFields.forEach((field, index) => {
        section.append(createSettingField(field, `${groupedFields.size}-${index}`));
      });
      groupsContainer.append(section);
    });

    loading.hidden = true;
    groupsContainer.hidden = false;
    updateChangeState();
  }

  /**
   * @param {SettingsField} field
   * @param {string} suffix
   */
  function createSettingField(field, suffix) {
    const container = document.createElement("div");
    container.className = "settings-field";

    const labelRow = document.createElement("div");
    labelRow.className = "settings-label-row";

    const label = document.createElement("label");
    const safeName = field.name.replaceAll(".", "-").replaceAll("_", "-");
    const inputId = `setting-${suffix}-${safeName}`;
    label.htmlFor = inputId;
    label.textContent = field.label;

    const state = document.createElement("span");
    state.className = "settings-field-state";
    state.textContent = settingState(field);
    labelRow.append(label, state);

    const control = document.createElement("div");
    control.className = "settings-control";

    const input = document.createElement("input");
    input.id = inputId;
    input.name = field.name;
    input.type = inputType(field);
    input.value = field.sensitive ? "" : field.value || "";
    input.autocomplete = field.sensitive ? "new-password" : "off";
    input.spellcheck = false;
    if (input.type === "number") input.step = "any";
    input.placeholder = inputPlaceholder(field);
    input.addEventListener("input", () => {
      removals.delete(field.name);
      input.disabled = false;
      container.classList.remove("is-reset");
      updateChangeState();
    });
    inputs.set(field.name, input);
    control.append(input);

    if (field.isSet) {
      const resetButton = document.createElement("button");
      resetButton.type = "button";
      resetButton.className = "settings-reset-action";
      resetButton.textContent = field.sensitive ? "Remove key" : "Reset value";
      resetButton.addEventListener("click", () => {
        const markedForRemoval = removals.has(field.name);
        if (markedForRemoval) {
          removals.delete(field.name);
          input.disabled = false;
          input.value = field.sensitive ? "" : field.value || "";
          resetButton.textContent = field.sensitive ? "Remove key" : "Reset value";
          container.classList.remove("is-reset");
        } else {
          removals.add(field.name);
          input.value = "";
          input.disabled = true;
          resetButton.textContent = "Undo";
          container.classList.add("is-reset");
        }
        updateChangeState();
      });
      control.append(resetButton);
    }

    const variable = document.createElement("code");
    variable.className = "settings-variable";
    variable.textContent = field.name;

    const description = document.createElement("p");
    description.className = "settings-description";
    description.textContent = field.description;

    const note = field.note ? document.createElement("p") : null;
    if (note) {
      note.className = "settings-note";
      note.textContent = field.note;
    }

    const defaultNote = document.createElement("p");
    defaultNote.className = "settings-default";
    defaultNote.textContent = field.sensitive
      ? field.isSet
        ? "A key is stored in your OS keyring. Enter a new key only to replace it."
        : "No API key is stored in your OS keyring."
      : field.defaultValue === null
        ? "Optional; no default value."
        : `Default: ${field.defaultValue}`;

    container.append(labelRow, control, variable, description);
    if (note) container.append(note);
    container.append(defaultNote);
    return container;
  }

  async function saveSettings() {
    if (!form.reportValidity()) return;
    const values = changedValues();
    if (Object.keys(values).length === 0) return;

    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
    setAlert("", "neutral");
    try {
      const response = await fetch(SETTINGS_URL, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ values }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload, "Settings could not be saved."));
      if (!isSettingsDocument(payload)) throw new Error("The server returned invalid settings.");
      renderSettings(payload);
      if (payload.restartRequired) {
        dialog.close();
        restartDialog.showModal();
      }
    } catch (error) {
      setAlert(error instanceof Error ? error.message : "Settings could not be saved.", "error");
      updateChangeState();
    } finally {
      saveButton.textContent = "Save changes";
    }
  }

  /** @returns {Record<string, string | null>} */
  function changedValues() {
    /** @type {Record<string, string | null>} */
    const values = {};
    fields.forEach((field) => {
      const input = inputs.get(field.name);
      if (!input) return;
      if (removals.has(field.name)) {
        values[field.name] = null;
        return;
      }
      if (field.sensitive) {
        if (input.value) values[field.name] = input.value;
        return;
      }
      const originalValue = field.value || "";
      if (input.value !== originalValue) values[field.name] = input.value;
    });
    return values;
  }

  function updateChangeState() {
    const count = Object.keys(changedValues()).length;
    saveButton.disabled = count === 0;
    changeSummary.textContent =
      count === 0 ? "No unsaved changes" : `${count} unsaved ${count === 1 ? "change" : "changes"}`;
  }

  /** @param {SettingsField} field */
  function settingState(field) {
    if (field.sensitive) return field.isSet ? "Stored in keyring" : "Not configured";
    return field.isSet ? "Saved in config.toml" : "Using default";
  }

  /** @param {SettingsField} field */
  function inputType(field) {
    if (field.sensitive || field.inputType === "password") return "password";
    if (field.inputType === "number") return "number";
    if (field.inputType === "url") return "url";
    return "text";
  }

  /** @param {SettingsField} field */
  function inputPlaceholder(field) {
    if (field.sensitive) {
      return field.isSet ? "Stored value hidden; enter to replace" : "Enter API key";
    }
    return field.defaultValue === null ? "Optional" : `Default: ${field.defaultValue}`;
  }

  /**
   * @param {string} message
   * @param {"neutral" | "success" | "error"} tone
   */
  function setAlert(message, tone) {
    alert.hidden = !message;
    alert.textContent = message;
    alert.dataset.tone = tone;
  }

  /** @param {unknown} value */
  function isSettingsDocument(value) {
    if (!value || typeof value !== "object") return false;
    const candidate = /** @type {Partial<SettingsDocument>} */ (value);
    return (
      typeof candidate.source === "string" &&
      Array.isArray(candidate.fields) &&
      typeof candidate.restartRequired === "boolean"
    );
  }

  /**
   * @param {unknown} value
   * @param {string} fallback
   */
  function errorMessage(value, fallback) {
    if (!value || typeof value !== "object") return fallback;
    const candidate = /** @type {{ error?: unknown }} */ (value);
    return typeof candidate.error === "string" && candidate.error ? candidate.error : fallback;
  }
})();
