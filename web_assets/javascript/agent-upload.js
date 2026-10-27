// Attachment-only transport. Progress comes exclusively from XMLHttpRequest.upload.
(function () {
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    let batch = null, revision = 0;
    const pendingTransports = [];
    const refresh = () => { window.chuanhuRefreshInputCards?.(); window.chuanhuRefreshSendButton?.(); };
    function retireChangedTarget() {
        const target = window.chuanhuInputConversation?.();
        if (!batch || batch.target === target) return;
        const previous = batch;
        batch = null; previous.retired = true;
        for (const item of previous.items) { item.removed = true; item.xhr?.abort(); }
        window.chuanhuAgentUploading = false; window.chuanhuAgentUploadStaging = false;
    }
    window.chuanhuUploadCards = () => { retireChangedTarget(); return batch?.items.filter(item => !item.removed) || []; };
    window.chuanhuUploadHasPending = () => { retireChangedTarget(); return !!batch?.items.some(item => !item.removed); };
    window.chuanhuUploadRemove = id => {
        retireChangedTarget();
        const item = batch?.items.find(item => item.id === id);
        if (!item || batch.committing) return;
        item.removed = true; item.xhr?.abort();
        if (!batch.running) {
            const retained = batch.items.filter(item => !item.removed);
            if (!retained.length) { batch.retired = true; batch = null; }
            // A failed native batch cannot emit its earlier successful siblings.
            // Always expose batch retry after removing its last failed member.
            else if (!retained.some(item => item.status === 'failed'))
                retained.forEach(item => { item.status = 'failed'; item.error = '请重试暂存附件'; });
        }
        refresh();
    };
    function upload(item) {
        return new Promise((resolve, reject) => {
            const xhr = item.xhr = new XMLHttpRequest();
            const base = window.gradio_config?.root || location.origin;
            xhr.open('POST', base.replace(/\/$/, '') + '/upload');
            xhr.withCredentials = true;
            xhr.upload.onprogress = event => {
                if (!item.removed && event.lengthComputable) {
                    item.progress = event.loaded / event.total;
                    refresh();
                }
            };
            xhr.onload = () => {
                item.xhr = null;
                if (item.removed) return resolve();
                try {
                    const paths = JSON.parse(xhr.responseText);
                    if (xhr.status < 200 || xhr.status >= 300 || !Array.isArray(paths) || paths.length !== 1 || typeof paths[0] !== 'string') throw Error();
                    item.path = paths[0]; item.status = 'uploaded'; resolve();
                } catch (_) { reject(Error('上传失败，请重试')); }
            };
            xhr.onerror = () => { item.xhr = null; reject(Error('上传失败，请重试')); };
            xhr.onabort = () => { item.xhr = null; item.removed ? resolve() : reject(Error('上传已取消')); };
            const data = new FormData(); data.append('files', item.file, item.name);
            item.status = 'uploading'; item.progress = null;
            xhr.send(data);
        });
    }
    const originalFetch = window.fetch;
    window.fetch = async function (resource, options) {
        let url;
        try { url = new URL(typeof resource === 'string' ? resource : resource.url, location.href); } catch (_) {}
        const uploadRoot = new URL(window.gradio_config?.root || location.origin, location.href);
        const uploadPath = uploadRoot.pathname.replace(/\/$/, '') + '/upload';
        const files = options?.body instanceof FormData ? options.body.getAll('files') : [];
        // Match a captured picker selection, including a canceled selection whose
        // native async prepare_files has not issued its POST yet. Never revive it.
        if (!url || url.origin !== uploadRoot.origin || url.pathname !== uploadPath || !url.searchParams.has('upload_id') || options?.method !== 'POST')
            return originalFetch.apply(this, arguments);
        const index = pendingTransports.findIndex(selection => files.length === selection.items.length &&
            files.every((file, i) => file.name === selection.items[i].name && file.size === selection.items[i].size));
        if (index < 0) return originalFetch.apply(this, arguments);
        const current = pendingTransports.splice(index, 1)[0];
        if (current.retired) return new Response('Attachment upload cancelled', {status: 409});
        current.running = true;
        for (const item of current.items) {
            if (item.removed) continue;
            try { await upload(item); }
            catch (error) { item.status = 'failed'; item.error = error.message; }
            refresh();
        }
        current.running = false;
        if (current.retired) return new Response('Attachment upload cancelled', {status: 409});
        if (current.items.some(item => !item.removed && item.status === 'failed')) {
            window.chuanhuAgentUploading = false; refresh();
            return new Response('Attachment upload failed', {status: 503});
        }
        current.committing = true;
        // Gradio FileData preprocessing and its upload-folder checks remain in place.
        // Path basenames are authoritative in InputFileStager, never positional orig_name.
        const retained = current.items.filter(item => !item.removed);
        // Keep native FileData.map's original indices intact. Canceled slots use
        // a survivor path only as a transport placeholder and are removed by
        // chuanhuUploadStaging before Gradio preprocessing/server callbacks.
        const paths = retained.length ? current.items.map(item => item.removed ? retained[0].path : item.path) : [];
        return new Response(JSON.stringify(paths), {
            status: 200, headers: {'Content-Type': 'application/json'}
        });
    };
    window.chuanhuUploadStaging = files => {
        retireChangedTarget();
        if (!batch || batch.running) return [];
        const retained = batch.items.filter(item => !item.removed);
        if ((files || []).some((file, index) => file.path !== (batch.items[index]?.removed ? retained[0]?.path : batch.items[index]?.path))) return [];
        batch.committing = true; window.chuanhuAgentUploadStaging = true;
        return (files || []).filter((file, index) => !batch.items[index]?.removed);
    };
    window.chuanhuUploadRetry = () => {
        retireChangedTarget();
        if (!batch || batch.running || batch.committing) return;
        const files = batch.items.filter(item => !item.removed).map(item => item.file);
        const input = root().querySelector('#agent-upload-files input[type=file]');
        if (!input || !files.length) return;
        batch = null;
        const transfer = new DataTransfer(); files.forEach(file => transfer.items.add(file));
        input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    };
    window.chuanhuUploadCommitted = files => {
        retireChangedTarget();
        if (!batch || !batch.committing) return;
        let metadata;
        try { metadata = JSON.parse(root().querySelector('#agent-pending-files [data-testid="block-label"]').textContent); } catch (_) {}
        if (metadata && metadata.target !== batch.target) return;
        const paths = new Set((files || []).map(file => typeof file === 'string' ? file : file.path));
        const retained = batch.items.filter(item => !item.removed);
        if (!retained.every(item => paths.has(item.path))) {
            batch.committing = false;
            retained.forEach(item => { item.status = 'failed'; item.error = '附件暂存失败，请重试'; });
        } else batch = null;
        window.chuanhuAgentUploading = false; window.chuanhuAgentUploadStaging = false; refresh();
    };
    window.chuanhuBeginUpload = files => {
        retireChangedTarget();
        if (!files?.length || batch?.running || batch?.committing || window.chuanhuInputBusy?.()) return false;
        if (batch?.items.some(item => !item.removed)) return false;
        const target = window.chuanhuInputConversation?.() || '';
        if (!target) return false;
        batch = {target, token: String(++revision), items: Array.from(files).map((file, index) => ({
            id: 'upload-' + revision + '-' + index, name: file.name, size: file.size, file,
            status: 'queued', progress: null, removed: false
        }))};
        pendingTransports.push(batch);
        window.chuanhuAgentUploadTarget = target; window.chuanhuAgentUploading = true;
        window.chuanhuRefreshInputCards?.(); refresh(); return true;
    };
})();
