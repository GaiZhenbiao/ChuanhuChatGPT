// Delegate from rerendered cards to the mounted native Gradio controls.
(function () {
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    let scheduled = false;
    // 只匹配同一消息的服务端文件身份和完整远端路径，不按文件名猜测。
    function fileReference(value) {
        if (typeof value !== 'string' || /^(?:https?:|\/\/|#)/i.test(value)) return null;
        try { value = decodeURIComponent(value); } catch (_) { return null; }
        if (/[\\\x00-\x1f]/.test(value) || value.split('/').includes('..')) return null;
        if (/^artifact:(?:\/\/)?/.test(value)) return {id: value.replace(/^artifact:(?:\/\/)?/, '')};
        value = value.replace(/^sandbox:/, '');
        if (/^\/(?:workspace|mnt\/data)\//.test(value)) return {path: value};
        if (/^(?:workspace|mnt\/data)\//.test(value)) return {path: '/' + value};
        if (/^(?:outputs|artifacts)\//.test(value)) return {path: '/workspace/' + value};
        return null;
    }
    function mountLinks(chat, groups) {
        for (const row of chat.querySelectorAll('.message-row.bot-row')) {
            const anchor = row.querySelector('.agent-message-anchor');
            if (!anchor) continue;
            const cards = groups.get(anchor.dataset.conversationId + ':' + anchor.dataset.messageKey)?.cards || [];
            for (const link of row.querySelectorAll('.md-message a[href]')) {
                const original = link._agentFileHref || link.getAttribute('href');
                const reference = fileReference(original);
                if (!reference) continue;
                link._agentFileHref = original;
                const matches = cards.filter(card => reference.id ? card.dataset.artifactId === reference.id
                    : fileReference(card.dataset.remotePath)?.path === reference.path);
                link.dataset.agentFileLink = 'true';
                link.dataset.artifactId = matches.length === 1 ? matches[0].dataset.artifactId : '';
                link.dataset.messageKey = anchor.dataset.messageKey;
                link.dataset.conversationId = anchor.dataset.conversationId;
                link.setAttribute('href', '#');
                link.removeAttribute('target');
                link.title = matches.length === 1 ? '获取此回复生成的文件' : '文件未发布或已过期，请重新连接后重试';
                if (matches.length === 1 && !matches[0].disabled && link.nextElementSibling?.classList.contains('agent-link-feedback'))
                    link.nextElementSibling.remove();
            }
        }
    }
    function mountCards() {
        scheduled = false;
        const app = root();
        const chat = app.querySelector('#chuanhu-chatbot');
        const source = app.querySelector('#model-output-cards');
        if (!chat) return;
        const groups = new Map();
        const activeConversation = globalThis.chuanhuInputConversation?.();
        for (const card of source?.querySelectorAll('.model-file-card') || []) {
            const key = card.dataset.messageKey, conversation = card.dataset.conversationId;
            if (!key || !conversation || (activeConversation !== undefined && conversation !== activeConversation)) continue;
            const identity = conversation + ':' + key;
            if (!groups.has(identity)) groups.set(identity, {key, conversation, cards: [], afterKeys: new Set(), orphan: false});
            groups.get(identity).cards.push(card);
            if (card.dataset.fileAfterKey) groups.get(identity).afterKeys.add(card.dataset.fileAfterKey);
            if (card.dataset.fileOrphan === 'true') groups.get(identity).orphan = true;
        }
        const used = new Set();
        for (const [identity, group] of groups) {
            const candidates = Array.from(chat.querySelectorAll('.agent-message-anchor')).filter(anchor =>
                anchor.dataset.conversationId === group.conversation && !anchor.closest('.history-message'));
            let anchors = candidates.filter(anchor => anchor.dataset.messageKey === group.key);
            if (!anchors.length && group.afterKeys.size === 1) {
                const afterKey = [...group.afterKeys][0];
                anchors = candidates.filter(anchor => anchor.dataset.messageKey === afterKey);
            }
            if (anchors.length > 1) continue;
            const row = anchors[0]?.closest('.message-row.bot-row');
            if (!row && !group.orphan) continue;
            let holder = Array.from(chat.querySelectorAll('.agent-message-files')).find(node => node.dataset.fileOwner === identity);
            if (!holder) {
                holder = document.createElement('div');
                holder.className = 'agent-message-files model-file-cards';
                holder.dataset.fileOwner = identity;
                holder.setAttribute('role', 'group');
                holder.setAttribute('aria-label', '此回复生成的文件');
            }
            const markup = (!row ? '<small>未关联消息的文件</small>' : '') + group.cards.map(card => card.outerHTML).join('');
            if (holder._sourceMarkup !== markup) { holder.innerHTML = markup; holder._sourceMarkup = markup; }
            holder.classList.toggle('agent-unassociated-files', !row);
            if (!row) {
                const parent = chat.querySelector('.bubble-wrap') || chat;
                if (holder.parentElement !== parent) parent.append(holder);
                used.add(holder);
                continue;
            }
            if (row.nextElementSibling !== holder) row.after(holder);
            row.classList.add('agent-message-has-files');
            holder.classList.toggle('agent-files-with-avatar', !!row.querySelector('.avatar-container'));
            let fileOnly = false;
            try { const raw = JSON.parse(atob(anchors[0].dataset.agentMessageRaw)).raw; fileOnly = raw === null || raw === ''; } catch (_) {}
            row.classList.toggle('agent-file-only-message', fileOnly);
            holder.classList.toggle('agent-turn-files-after-answer', fileOnly && !!row.querySelector('.agent-turn-files-after-answer'));
            used.add(holder);
        }
        for (const holder of chat.querySelectorAll('.agent-message-files')) if (!used.has(holder)) holder.remove();
        for (const row of chat.querySelectorAll('.agent-message-has-files')) {
            if (!row.nextElementSibling?.classList.contains('agent-message-files')) {
                row.classList.remove('agent-file-only-message');
                row.classList.remove('agent-message-has-files');
            }
        }
        const linkGroups = new Map(groups);
        for (const group of groups.values()) {
            if (group.afterKeys.size !== 1) continue;
            const alias = group.conversation + ':' + [...group.afterKeys][0];
            const existing = linkGroups.get(alias);
            if (existing !== group) linkGroups.set(alias, {cards: [...(existing?.cards || []), ...group.cards]});
        }
        mountLinks(chat, linkGroups);
        let notice = chat.querySelector('.agent-file-notice');
        const incomingNotice = source?.querySelector('[data-file-notice]');
        if (incomingNotice && incomingNotice.dataset.conversationId === activeConversation) {
            if (!notice) { notice = document.createElement('div'); notice.className = 'agent-file-notice'; }
            if (notice.innerHTML !== incomingNotice.outerHTML) notice.innerHTML = incomingNotice.outerHTML;
            if (!notice.parentElement) (chat.querySelector('.bubble-wrap') || chat).append(notice);
        } else notice?.remove();
    }
    function scheduleMount() {
        if (!scheduled) { scheduled = true; queueMicrotask(mountCards); }
    }
    globalThis.chuanhuRefreshArtifactCards = scheduleMount;
    const observer = new MutationObserver(scheduleMount);
    function start() { observer.observe(document.documentElement, {childList:true, subtree:true, characterData:true}); mountCards(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
    document.addEventListener('click', event => {
        const link = (event.composedPath ? event.composedPath() : [event.target])
            .find(node => node?.matches?.('a[data-agent-file-link]'));
        if (link) {
            event.preventDefault();
            const cards = Array.from(root().querySelectorAll('#model-output-cards .model-file-card'));
            const card = cards.find(node => node.dataset.artifactId === link.dataset.artifactId
                && (node.dataset.messageKey === link.dataset.messageKey || node.dataset.fileAfterKey === link.dataset.messageKey) && node.dataset.conversationId === link.dataset.conversationId
                && node.dataset.conversationId === globalThis.chuanhuInputConversation?.());
            if (card && !card.disabled) card.click();
            else {
                let feedback = link.nextElementSibling;
                if (!feedback?.classList.contains('agent-link-feedback')) {
                    feedback = document.createElement('span'); feedback.className = 'agent-link-feedback';
                    feedback.setAttribute('aria-live', 'polite'); link.after(feedback);
                }
                feedback.textContent = card ? '（文件正在准备，请稍后重试）' : '（文件未发布或已过期，请重新连接后重试）';
            }
            return;
        }
        const card = (event.composedPath ? event.composedPath() : [event.target])
            .find(node => node?.matches?.('.model-file-card'));
        if (!card || card.disabled) return;
        const app = root();
        const identifier = card.dataset.artifactId;
        const feedback = text => { card.querySelector('.model-file-feedback').textContent = text; };
        if (card.dataset.fileAction === 'download') {
            const native = app.querySelector('#model-output-native-files');
            let ids;
            try { ids = JSON.parse(native.querySelector('[data-testid="block-label"]').textContent.trim()); }
            catch (_) { feedback('文件链接正在准备，请稍后重试'); return; }
            const links = native.querySelectorAll('td.download a[href]');
            const index = ids.indexOf(identifier);
            if (index < 0 || links.length !== ids.length || !links[index]) {
                feedback('文件链接正在准备，请稍后重试'); return;
            }
            // The native URL keeps its isolated cache identity. The same-origin
            // download hint supplies the original filename for both card/link.
            links[index].setAttribute('download', card.dataset.downloadName || 'artifact');
            links[index].click();
        } else if (card.dataset.fileAction === 'retry') {
            const input = app.querySelector('#model-output-retry-id textarea, #model-output-retry-id input');
            const trigger = app.querySelector('#model-output-retry');
            if (!input || !trigger) { feedback('暂时无法重试，请重新连接'); return; }
            input.value = identifier;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            requestAnimationFrame(() => trigger.click());
        }
    });
})();
