// Independent metadata polling never extends a completed chat queue event.
(() => {
    if (globalThis.__chuanhuFileRefreshVersion === 1) return;
    globalThis.chuanhuFileRefreshCleanup?.();
    globalThis.__chuanhuFileRefreshVersion = 1;
    const root = () => typeof gradioApp === 'function' ? gradioApp() : document;
    const noops = () => Array.from({length:4}, () => ({__type__:'update'}));
    let inFlight = false, dispatched = '', revision = '';
    const current = () => {
        try { return JSON.parse(root().querySelector('#model-capability-state [data-model-capabilities]')?.dataset.modelCapabilities || '{}'); }
        catch (_) { return {}; }
    };
    globalThis.chuanhuAcceptFileUpdate = (wire, target) => {
        let result; try { result = JSON.parse(wire); } catch (_) { return noops(); }
        const state = current();
        if (JSON.stringify([result.target, result.generation]) === dispatched) inFlight = false;
        if (result.target !== target || result.target !== state.history_visit
            || result.generation !== state.task_generation || !state.agent_tools) return noops();
        for (const file of result.updates?.[2]?.value || []) {
            if (file.url?.startsWith('/file=') && globalThis.gradio_config?.root)
                file.url = globalThis.gradio_config.root.replace(/\/$/, '') + file.url;
        }
        return result.updates;
    };
    const timer = setInterval(() => {
        const state = current(), cards = root().querySelector('#model-output-cards [data-file-pending]');
        const visit = JSON.stringify([state.history_visit, state.task_generation]);
        if (visit !== dispatched) { inFlight = false; dispatched = visit; revision = ''; }
        if (!state.agent_tools || !state.input_target || inFlight) return;
        // A final read after pending becomes false catches the last receipt.
        if (cards?.dataset.filePending !== 'true' && cards?.dataset.fileRevision === revision) return;
        revision = cards?.dataset.fileRevision || '';
        const button = root().querySelector('button#agent-file-refresh, #agent-file-refresh button');
        if (button) { inFlight = true; button.click(); }
    }, 750);
    globalThis.chuanhuFileRefreshCleanup = () => clearInterval(timer);
})();
