// Capture the intended conversation before the browser's upload starts. A late
// upload completion must not attach files to a different model or new chat.
(function () {
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    const handledDrafts = new Set();
    const handledToolPatches = new Set();
    window.chuanhuApplyToolPatch = patch => {
        if (!patch || handledToolPatches.has(patch.token) || patch.conversation !== window.chuanhuInputConversation?.()) return;
        const revision = window.chuanhuAgentToolRevision || 0;
        if (patch.revision < revision) { handledToolPatches.add(patch.token); return; }
        if (patch.revision !== revision) return;
        const input = root().querySelector('#agent-network-access input[type=checkbox]');
        if (!input) return;
        handledToolPatches.add(patch.token);
        if (input.checked !== patch.network) {
            input.checked = patch.network;
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }
    };
    document.addEventListener('input', event => {
        if (event.target?.matches?.('#user-input-tb textarea'))
            window.chuanhuDraftEditRevision = (window.chuanhuDraftEditRevision || 0) + 1;
    }, true);
    window.chuanhuClearSubmittedDraft = draft => {
        if (!draft || handledDrafts.has(draft.token)) return;
        const pending = window.chuanhuAgentPendingDraft;
        if (!pending || pending.conversation !== draft.conversation || pending.text !== draft.text
            || window.chuanhuInputConversation?.() !== draft.conversation) return;
        handledDrafts.add(draft.token);
        window.chuanhuAgentPendingDraft = null;
        const input = root().querySelector('#user-input-tb textarea');
        if (input && input.value === draft.text && (window.chuanhuDraftEditRevision || 0) === pending.revision) {
            input.value = '';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    };
    let previousError = null, sawProgress = false;
    document.addEventListener('change', event => {
        const input = (event.composedPath ? event.composedPath() : [event.target])
            .find(node => node?.matches?.('#agent-upload-files input[type=file]'));
        if (!input || !input.files?.length) return;
        if (window.chuanhuBeginUpload) {
            if (!window.chuanhuBeginUpload(Array.from(input.files))) { event.preventDefault(); event.stopImmediatePropagation(); input.value = ''; }
            return;
        }
        // Gradio can recreate this input when a model changes while a previous
        // upload is still in flight. Keep that batch's conversation immutable
        // until its upload callback has captured it.
        if (window.chuanhuAgentUploading) {
            event.preventDefault();
            event.stopImmediatePropagation();
            input.value = '';
            return;
        }
        window.chuanhuAgentUploadTarget = window.chuanhuInputConversation?.() || '';
        window.chuanhuAgentUploading = true;
        previousError = root().querySelector('#agent-upload-files .error');
        sawProgress = false;
        window.chuanhuRefreshSendButton?.();
    }, true);
    function removeSelected(event) {
        if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
        const button = (event.composedPath ? event.composedPath() : [event.target])
            .find(node => node?.matches?.('button'));
        if (button?.matches?.('.agent-input-remove-card, .agent-upload-retry')) {
            event.preventDefault(); event.stopImmediatePropagation();
            if (button.dataset.uploadId) { window.chuanhuUploadRemove?.(button.dataset.uploadId); return; }
            if (button.dataset.uploadRetry) { window.chuanhuUploadRetry?.(); return; }
            if (window.chuanhuInputBusy?.() || window.chuanhuAgentUploading) return;
            const app = root(), input = app.querySelector('#agent-input-remove-payload textarea, #agent-input-remove-payload input');
            const trigger = app.querySelector('#agent-input-remove');
            if (!input || !trigger) return;
            input.value = JSON.stringify({target:button.dataset.inputTarget, ids:[button.dataset.inputId]});
            input.dispatchEvent(new Event('input', {bubbles:true}));
            requestAnimationFrame(() => trigger.click());
            return;
        }
        const preview = button?.closest?.('#agent-pending-files');
        if (!preview) return;
        const row = button.closest('tr.file');
        if (row && !button.matches('.label-clear-button')) return;
        // These are the native per-file remove and clear-all buttons. Prevent
        // File.change from removing by a stale positional subset; submit only
        // the stable IDs that the user actually saw and selected.
        event.preventDefault();
        event.stopImmediatePropagation();
        if (window.chuanhuInputBusy?.() || window.chuanhuAgentUploading) return;
        let metadata;
        try { metadata = JSON.parse(preview.querySelector('[data-testid="block-label"]').textContent.trim()); }
        catch (_) { return; }
        const rows = Array.from(preview.querySelectorAll('tr.file'));
        if (!Array.isArray(metadata.ids) || metadata.ids.length !== rows.length) return;
        const ids = row ? [metadata.ids[rows.indexOf(row)]] : metadata.ids;
        if (!ids.length || ids.some(id => !id)) return;
        const app = root();
        const input = app.querySelector('#agent-input-remove-payload textarea, #agent-input-remove-payload input');
        const trigger = app.querySelector('#agent-input-remove');
        if (!input || !trigger) return;
        input.value = JSON.stringify({target: metadata.target, ids});
        input.dispatchEvent(new Event('input', {bubbles: true}));
        requestAnimationFrame(() => trigger.click());
    }
    document.addEventListener('click', removeSelected, true);
    document.addEventListener('keydown', removeSelected, true);
    const observer = new MutationObserver(() => {
        const app = root(), progress = app.querySelector('#agent-upload-files .uploading');
        if (progress) sawProgress = true;
        const error = app.querySelector('#agent-upload-files .error');
        if (!window.chuanhuAgentUploadStaging && !progress && error && (sawProgress || error !== previousError)) {
            window.chuanhuAgentUploading = false;
            window.chuanhuRefreshSendButton?.();
        }
    });
    function start() { observer.observe(document.documentElement, {childList:true, subtree:true}); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
