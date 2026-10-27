// Dedicated login fields are transient and never inserted into the chat.
window.chuanhuAgentLoginOption = function () {
    const root = (typeof gradioApp === 'function' ? gradioApp() : document).querySelector('#agent-browser-form');
    const option = root?.querySelector('#agent-login-option');
    if (!option) return;
    const allowed = JSON.parse(option.selectedOptions[0].dataset.fields);
    root.querySelectorAll('[data-agent-field]').forEach(label => {
        label.hidden = !allowed.includes(label.dataset.agentField);
        if (label.hidden) label.querySelectorAll('input').forEach(input => input.value = '');
    });
};
