(function () {
  function appRoot() {
    return window.ChuanhuApp?.root?.() || document;
  }

  function currentInput() {
    return window.ChuanhuApp?.userInput?.() || appRoot().querySelector("#user-input-tb textarea, #user-input-tb input");
  }

  function selectedLanguage(button) {
    const panel = button.closest(".prompt-tools-panel");
    return panel?.querySelector("[data-prompt-tools-language]")?.value || "中文";
  }

  function emitInput(input) {
    if (!window.ChuanhuApp?.setInputValue?.(input, input.value)) {
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    input.focus();
  }

  function applyTemplate(input, template, language) {
    const prompt = template.replaceAll("{language}", language);
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    const selected = input.value.slice(start, end);
    if (selected.trim()) {
      input.setRangeText(`${prompt}\n\n${selected}`, start, end, "end");
      return;
    }
    if (input.value.trim()) {
      input.value = `${prompt}\n\n${input.value}`;
      input.selectionStart = input.selectionEnd = prompt.length + 2;
      return;
    }
    input.value = `${prompt}\n\n`;
    input.selectionStart = input.selectionEnd = input.value.length;
  }

  function bindPromptButtons() {
    appRoot().querySelectorAll("[data-prompt-tools-template]").forEach((button) => {
      if (button.dataset.promptToolsBound) return;
      button.dataset.promptToolsBound = "true";
      button.addEventListener("click", () => {
        const input = currentInput();
        if (!input) return;
        applyTemplate(input, button.dataset.promptToolsTemplate || "", selectedLanguage(button));
        emitInput(input);
      });
    });
  }

  if (window.ChuanhuApp?.onReady) {
    window.ChuanhuApp.onReady(bindPromptButtons);
    window.ChuanhuApp.onMutation(bindPromptButtons);
  } else {
    const observer = new MutationObserver(bindPromptButtons);
    window.addEventListener("DOMContentLoaded", () => {
      bindPromptButtons();
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();
