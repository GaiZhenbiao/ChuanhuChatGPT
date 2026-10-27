// One capability payload drives custom controls as well as native Gradio updates.
(function () {
    let snapshot = {};
    let queued = false;
    let historyIntent = null;
    let latestHistoryIntent = null;
    window.chuanhuClearHistoryIntent = () => { historyIntent = latestHistoryIntent = null; };
    window.chuanhuHistorySelection = filename => {
        const selected = historyIntent;
        historyIntent = null;
        return selected && (filename === undefined || selected.filename === filename) ? selected : null;
    };
    function captureHistoryIntent(event, keyboardTarget = null) {
        if (event.type === 'pointerdown' && event.button !== 0) return;
        const target = keyboardTarget || event.composedPath?.()[0] || event.target;
        if (target?.closest?.('button, a, .chat-selected-btns')) return;
        const input = target?.matches?.('#history-select-dropdown input[type=radio]') ? target
            : target?.closest?.('#history-select-dropdown label')?.querySelector('input[type=radio]');
        if (input?.disabled) return;
        if (event.isTrusted && input?.matches?.('#history-select-dropdown input[type=radio]')) {
            // Read the current response synchronously. The capability observer
            // may not have copied the new visit into snapshot yet.
            const marker = root().querySelector('#model-capability-state [data-model-capabilities]');
            let visit = snapshot.history_visit;
            try { visit = JSON.parse(marker?.dataset.modelCapabilities || '{}').history_visit || visit; } catch (_) {}
            const labelKey = input.closest?.('label')?.dataset?.testid;
            const filename = labelKey?.endsWith('-radio-label') ? labelKey.slice(0, -12)
                : typeof input.__value === 'string' ? input.__value : input.value;
            historyIntent = {filename, visit};
            latestHistoryIntent = {...historyIntent, sentVisit: visit};
            root().querySelector('button#history-intent-submit, #history-intent-submit button')?.click();
        }
    }
    document.addEventListener('pointerdown', captureHistoryIntent, true);
    document.addEventListener('keydown', event => {
        if ([' ', 'Enter'].includes(event.key) && event.target?.matches?.('#history-select-dropdown input[type=radio]')) {
            event.preventDefault(); captureHistoryIntent(event);
        }
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
            const radios = Array.from(root().querySelectorAll('#history-select-dropdown input[type=radio]:not(:disabled)'));
            const index = radios.indexOf(event.composedPath?.()[0] || event.target);
            if (index >= 0) {
                event.preventDefault();
                const next = radios[(index + (['ArrowUp', 'ArrowLeft'].includes(event.key) ? -1 : 1) + radios.length) % radios.length];
                next.focus(); next.click(); captureHistoryIntent(event, next);
            }
        }
    }, true);
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    // Mutation actions require an explicit capability, including during initial load.
    const explicitActions = new Set(['regenerate', 'history_delete']);
    window.chuanhuSupports = capability => explicitActions.has(capability)
        ? snapshot[capability] === true : snapshot[capability] !== false;
    window.chuanhuInputTarget = () => snapshot.sandbox_attachments === true ? '#agent-upload-files' : '#upload-index-file';
    window.chuanhuInputBusy = () => snapshot.busy === true;
    window.chuanhuTurnTerminal = () => snapshot.turn_terminal === true;
    window.chuanhuInputConversation = () => snapshot.input_target || '';
    window.chuanhuRefreshAgentLoader = bot => {
        const state = bot.querySelector('.agent-reply-state');
        const waiting = snapshot.agent_tools && snapshot.busy && !snapshot.turn_terminal && state &&
            state.dataset.conversationId === snapshot.input_target && state.dataset.turnId === snapshot.agent_turn_id &&
            state.dataset.waiting === 'true';
        const empty = !!(waiting && state.dataset.empty === 'true');
        if (bot.classList.contains('agent-loading-only') !== empty) bot.classList.toggle('agent-loading-only', empty);
        let loader = bot.querySelector('.generating-loader');
        if (waiting && !loader) {
            loader = document.createElement('div');
            loader.className = 'generating-loader';
            loader.setAttribute('aria-label', '等待回答');
            bot.appendChild(loader);
        }
        if (!waiting) loader?.remove();
    };
    function apply() {
        queued = false;
        const app = root();
        const marker = app.querySelector('#model-capability-state [data-model-capabilities]');
        if (!marker) return;
        const wasTerminal = snapshot.turn_terminal === true;
        try { snapshot = JSON.parse(marker.dataset.modelCapabilities); } catch (_) { return; }
        if (latestHistoryIntent && snapshot.history_filename === latestHistoryIntent.filename
                && snapshot.history_visit !== latestHistoryIntent.sentVisit) {
            latestHistoryIntent = historyIntent = null;
        } else if (latestHistoryIntent && snapshot.history_visit && latestHistoryIntent.sentVisit !== snapshot.history_visit) {
            // Keep the last explicit user choice through an earlier selection's
            // atomic response; programmatic Radio updates never create intent.
            latestHistoryIntent.sentVisit = snapshot.history_visit;
            historyIntent = {filename: latestHistoryIntent.filename, visit: snapshot.history_visit};
            app.querySelector('button#history-intent-submit, #history-intent-submit button')?.click();
        }
        const chatArea = app.querySelector("#chatbot-area");
        if (chatArea && chatArea.classList.contains("agent-mode") !== (snapshot.agent_tools === true)) {
            chatArea.classList.toggle("agent-mode", snapshot.agent_tools === true);
        }
        const mapping = {
            regenerate: '.regenerate-btn', history_delete: '.delete-latest-btn',
            history_edit: '.edit-message-btn', history_rollback: '.rollback-btn',
            message_copy: '.copy-bot-btn', message_markdown: '.toggle-md-btn',
            input_attachments: '#upload-files-btn', knowledge: '#uploaded-files-btn',
            single_turn: 'input[name="single-session-cb"]',
            external_websearch: 'input[name="online-search-cb"]'
        };
        Object.entries(mapping).forEach(([capability, selector]) => {
            app.querySelectorAll(selector).forEach(element => {
                const visible = window.chuanhuSupports(capability);
                const target = element.matches('input[type="checkbox"]') ? element.closest('.switch-checkbox') : element;
                if (target && target.hidden === visible) target.hidden = !visible;
                if ('disabled' in element && element.disabled === visible) element.disabled = !visible;
            });
        });
        const more = app.querySelector('#chatbot-input-more-btn-div');
        const hasMore = ['input_attachments','knowledge','single_turn','external_websearch'].some(window.chuanhuSupports);
        if (more && more.hidden === hasMore) more.hidden = !hasMore;
        if (!wasTerminal && snapshot.turn_terminal === true && typeof setLatestMessage === 'function') setLatestMessage();
        if (snapshot.agent_tools) app.querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot')
            .forEach(window.chuanhuRefreshAgentLoader);
        window.chuanhuRefreshSendButton?.();
        window.chuanhuRefreshArtifactCards?.();
        window.chuanhuClearSubmittedDraft?.(snapshot.submitted_draft);
        window.chuanhuApplyToolPatch?.(snapshot.tool_patch);
    }
    function schedule() {
        if (!queued) { queued = true; queueMicrotask(apply); }
    }
    const observer = new MutationObserver(schedule);
    function start() { observer.observe(document.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-model-capabilities']}); apply(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
