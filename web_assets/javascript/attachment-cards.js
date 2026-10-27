// 原生 File 保留上传状态；卡片只投影名称、大小和稳定附件 ID。
(function () {
    let scheduled = false;
    const observedBubbles = new Set();
    const alignmentObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null;
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    function mount() {
        scheduled = false;
        const app = root(), composer = app.querySelector('#chatbot-input-tb-row');
        const native = app.querySelector('#agent-pending-files');
        if (!composer || !native) return;
        let metadata;
        try { metadata = JSON.parse(native.querySelector('[data-testid="block-label"]').textContent); }
        catch (_) { metadata = {}; }
        const ready = metadata.target === window.chuanhuInputConversation?.() ? metadata.files || [] : [];
        const uploads = window.chuanhuUploadCards?.() || [];
        const sizeLabel = size => { const unit = size >= 1024 ** 3 ? 'GB' : size >= 1024 ** 2 ? 'MB' : 'KB';
            return (size / (unit === 'GB' ? 1024 ** 3 : unit === 'MB' ? 1024 ** 2 : 1024)).toFixed(2) + ' ' + unit; };
        const files = ready.concat(uploads.map(item => ({...item, upload: true,
            basename: item.name.replace(/(?:\.tar\.(?:gz|bz2|xz|zst|lzma|lz)|\.d\.ts|\.[^.]+)$/i, ''),
            extension: (item.name.includes('.') ? item.name.split('.').pop().toUpperCase() : 'FILE').slice(0, 5),
            size_label: sizeLabel(item.size)})));
        let holder = composer.querySelector('.agent-pending-cards');
        if (!holder && files.length) {
            holder = document.createElement('div'); holder.className = 'agent-pending-cards';
            holder.setAttribute('role', 'group'); holder.setAttribute('aria-label', '待发送附件');
            composer.prepend(holder);
        }
        if (holder) {
            const signature = JSON.stringify([metadata.target, files.map(({file, xhr, ...visible}) => visible)]);
            if (holder._signature !== signature) {
                holder.replaceChildren(); holder._signature = signature;
                for (const file of files) {
                    const card = document.createElement('div'); card.className = 'agent-input-card agent-file-card--mini';
                    const extension = file.extension || 'FILE';
                    // Same escaped server renderer as sent user and bot cards.
                    const icon = document.createElement('template');
                    if (file.upload) {
                        const progress = file.progress == null ? 0 : Math.max(0, Math.min(1, file.progress));
                        icon.innerHTML = '<span class="agent-input-icon agent-upload-progress" role="progressbar" aria-label="上传 ' +
                            '" aria-valuemin="0" aria-valuemax="100"' + (file.progress == null ? '' : ' aria-valuenow="' + Math.round(progress * 100) + '"') +
                            '><svg viewBox="0 0 32 32"><circle class="agent-upload-track" cx="16" cy="16" r="12"/><circle class="agent-upload-value" cx="16" cy="16" r="12" pathLength="100" stroke-dasharray="' + progress * 100 + ' 100"/></svg></span>';
                    } else icon.innerHTML = file.icon;
                    const text = document.createElement('span'); text.className = 'agent-input-card-text';
                    const name = document.createElement('span'); name.className = 'agent-input-name';
                    name.textContent = file.basename; name.title = file.name;
                    const meta = document.createElement('span'); meta.className = 'agent-input-meta';
                    meta.textContent = extension + ' · ' + file.size_label + (file.status === 'failed' ? ' · 上传失败' : '');
                    text.append(name, meta);
                    const remove = document.createElement('button'); remove.type = 'button';
                    remove.className = 'agent-input-remove-card'; remove.textContent = '×';
                    remove.setAttribute('aria-label', '移除 ' + file.name);
                    if (file.upload) remove.dataset.uploadId = file.id;
                    else { remove.dataset.inputId = file.id; remove.dataset.inputTarget = metadata.target; }
                    card.append(icon.content, text, remove);
                    if (file.status === 'failed') {
                        const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'agent-upload-retry';
                        retry.dataset.uploadRetry = 'true'; retry.textContent = '重试'; card.append(retry);
                    }
                    holder.append(card);
                }
            }
            const busy = window.chuanhuInputBusy?.() || window.chuanhuAgentUploading;
            for (const button of holder.querySelectorAll('button')) button.disabled = button.dataset.uploadId || button.dataset.uploadRetry ? !!window.chuanhuAgentUploadStaging : !!busy;
            holder.hidden = files.length === 0;
            composer.classList.toggle('agent-composer-has-files', files.length > 0);
        }
        const chat = app.querySelector('#chuanhu-chatbot');
        if (!chat) return;
        const used = new Set(), bubbles = new Set();
        for (const source of chat.querySelectorAll('.agent-user-file-source')) {
            const row = source.closest('.message-row.user-row');
            if (!row) continue;
            let cards = row.previousElementSibling;
            if (!cards?.classList.contains('agent-user-files')) {
                cards = document.createElement('div'); cards.className = 'agent-user-files';
                cards.setAttribute('role', 'group'); cards.setAttribute('aria-label', '此消息上传的附件');
                row.before(cards);
            }
            if (cards._markup !== source.innerHTML) { cards.innerHTML = source.innerHTML; cards._markup = source.innerHTML; }
            const bubble = row.querySelector('.message.user');
            if (bubble) {
                // Align to the actual user bubble, excluding its avatar/gap.
                const inset = Math.max(0, row.getBoundingClientRect().right - bubble.getBoundingClientRect().right).toFixed(2) + 'px';
                if (cards.style.getPropertyValue('--agent-user-bubble-inset') !== inset) cards.style.setProperty('--agent-user-bubble-inset', inset);
                for (const target of [bubble, row]) {
                    bubbles.add(target);
                    if (alignmentObserver && !observedBubbles.has(target)) { alignmentObserver.observe(target); observedBubbles.add(target); }
                }
            }
            used.add(cards);
        }
        for (const cards of chat.querySelectorAll('.agent-user-files')) if (!used.has(cards)) cards.remove();
        for (const bubble of observedBubbles) if (!bubbles.has(bubble)) { alignmentObserver?.unobserve(bubble); observedBubbles.delete(bubble); }
    }
    function schedule() { if (!scheduled) { scheduled = true; queueMicrotask(mount); } }
    window.chuanhuRefreshInputCards = schedule;
    const observer = new MutationObserver(schedule);
    function start() { observer.observe(document.documentElement, {childList: true, subtree: true, characterData: true}); mount(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
