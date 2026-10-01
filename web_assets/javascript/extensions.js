(function () {
  const LABEL_CLASS = "extension-tabs-section-label";

  function appRoot() {
    return window.ChuanhuApp?.root?.() || document;
  }

  function buttonText(button) {
    return (button?.textContent || "").trim();
  }

  function findSettingTabs() {
    return appRoot().querySelector("#chuanhu-setting-tabs");
  }

  function extensionSettingsLabelText() {
    return appRoot().querySelector("#extension-settings-label-source")?.textContent?.trim() || "插件设置";
  }

  function extensionSettingsTabLabels() {
    const source = appRoot().querySelector("#extension-settings-tab-labels");
    if (!source?.dataset?.labels) return [];
    try {
      return JSON.parse(source.dataset.labels);
    } catch {
      return [];
    }
  }

  function findTabNav(tabsRoot, settingLabels) {
    if (!tabsRoot) return null;
    const navs = Array.from(tabsRoot.querySelectorAll(".tab-nav"));
    return navs.find((nav) => {
      const buttons = Array.from(nav.querySelectorAll("button"));
      return buttons.some((button) => settingLabels.includes(buttonText(button)));
    }) || null;
  }

  function installExtensionSettingsLabel() {
    const tabsRoot = findSettingTabs();
    const settingLabels = extensionSettingsTabLabels();
    if (!settingLabels.length) return;

    const nav = findTabNav(tabsRoot, settingLabels);
    if (!nav || nav.querySelector(`.${LABEL_CLASS}`)) return;

    const buttons = Array.from(nav.querySelectorAll("button"));
    const firstSettingsButton = buttons.find((button) => settingLabels.includes(buttonText(button)));
    if (!firstSettingsButton) return;

    const label = document.createElement("div");
    label.className = LABEL_CLASS;
    label.textContent = extensionSettingsLabelText();
    firstSettingsButton.insertAdjacentElement("beforebegin", label);
  }

  function gradioTextInput(root) {
    return root?.querySelector("textarea, input");
  }

  function setGradioValue(root, value) {
    const input = gradioTextInput(root);
    if (!input) return false;
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function submitExtensionAction(action) {
    const root = appRoot();
    const payloadRoot = root.querySelector("#extension-action-payload");
    const actionButton = root.querySelector("#extension-action-btn button, #extension-action-btn");
    if (!setGradioValue(payloadRoot, JSON.stringify(action)) || !actionButton) return;
    actionButton.click();
  }

  function bindExtensionManager() {
    appRoot().querySelectorAll("[data-extension-action]").forEach((element) => {
      if (element.dataset.extensionBound) return;
      element.dataset.extensionBound = "true";
      const action = element.dataset.extensionAction;
      if (action === "toggle") {
        element.addEventListener("change", () => {
          submitExtensionAction({
            action: "toggle",
            id: element.dataset.extensionId,
            enabled: element.checked,
          });
        });
      } else if (action === "update") {
        element.addEventListener("click", () => {
          submitExtensionAction({
            action: "update",
            id: element.dataset.extensionId,
          });
        });
      }
    });
  }

  function syncExtensionsUi() {
    installExtensionSettingsLabel();
    bindExtensionManager();
  }

  if (window.ChuanhuApp?.onReady) {
    window.ChuanhuApp.onReady(syncExtensionsUi);
    window.ChuanhuApp.onMutation(syncExtensionsUi);
  } else {
    const observer = new MutationObserver(syncExtensionsUi);
    window.addEventListener("DOMContentLoaded", () => {
      syncExtensionsUi();
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();
