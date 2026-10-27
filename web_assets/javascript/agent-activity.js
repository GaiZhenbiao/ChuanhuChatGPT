/* Display elapsed observation time without polling or mutating task state. */
(() => {
    if (globalThis.__chuanhuActivityVersion === 10) return;
    globalThis.__chuanhuActivityCleanup?.();
    globalThis.__chuanhuActivityVersion = 10;
    const clocks = new WeakMap();
    const expanded = new Map();
    function owned(detail, conversation) {
        return detail && !detail.closest('.history-message') && conversation !== undefined
            && detail.dataset.conversationId === conversation;
    }
    function detailKey(detail) {
        return JSON.stringify([detail.dataset.conversationId, detail.dataset.scopeId || '', detail.dataset.turnId || '', detail.dataset.layer || 'tool', detail.dataset.activityKey]);
    }
    const nodeStates = new WeakMap();
    const currentNodes = new Map();
    let restoreFrame;
    let scroller;
    let restoringScroll = false;
    function sampleScroll(binding = scroller) {
        if (!binding || restoringScroll) return;
        binding.top = binding.node.scrollTop;
        binding.following = binding.node.offsetHeight + binding.top > binding.node.scrollHeight - 100;
    }
    function scrollPosition(binding, measuredHeight) {
        // Read live position before measuring a replacement. Native scrolling
        // can move before its queued scroll event updates our saved baseline.
        const observed = binding.node.scrollTop;
        if (binding.pendingIntent) return {top: observed, following: false, clamped: false, intent: true};
        const height = measuredHeight ?? binding.node.scrollHeight;
        const maximum = Math.max(0, height - binding.node.offsetHeight);
        const atClamp = binding.top > maximum && Math.abs(observed - maximum) <= 1;
        const moved = !atClamp && Math.abs(observed - binding.top) > 1;
        const top = moved ? observed : binding.top;
        return {top, following: binding.following && !moved,
            clamped: top > maximum && Math.abs(binding.node.scrollTop - maximum) <= 1};
    }
    function releaseScroller() {
        if (!scroller) return;
        const {node, hook, descriptor, onScroll, onIntent, intentFrame} = scroller;
        node.removeEventListener('scroll', onScroll);
        for (const name of ['wheel', 'keydown', 'touchmove', 'pointerdown']) node.removeEventListener(name, onIntent, true);
        if (intentFrame !== undefined) globalThis.cancelAnimationFrame?.(intentFrame);
        if (node.scrollTo === hook) {
            if (descriptor) Object.defineProperty(node, 'scrollTo', descriptor);
            else delete node.scrollTo;
        }
        scroller = undefined;
    }
    function bindScroller(app, conversation, details) {
        const node = details.some(detail => owned(detail, conversation))
            ? app.querySelector?.('#chuanhu-chatbot .bubble-wrap, #chuanhu-chatbot .panel-wrap') : null;
        if (scroller && (scroller.node !== node || scroller.conversation !== conversation)) releaseScroller();
        if (!node || scroller || typeof node.scrollTo !== 'function') return;
        const original = node.scrollTo;
        const descriptor = Object.getOwnPropertyDescriptor(node, 'scrollTo');
        const binding = {node, original, descriptor, conversation};
        binding.onScroll = () => { sampleScroll(binding); binding.pendingIntent = false; };
        binding.onIntent = event => {
            if (!event?.isTrusted || event.defaultPrevented) return;
            if (event.type === 'wheel' && (!event.deltaY || event.ctrlKey || binding.following && event.deltaY > 0)) return;
            if (event.type === 'keydown' && (!['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)
                || event.target?.closest?.('input, textarea, select, [contenteditable="true"]')
                || event.key === ' ' && event.target?.closest?.('summary')
                || binding.following && (['ArrowDown', 'PageDown', 'End'].includes(event.key) || event.key === ' ' && !event.shiftKey)
                || event.ctrlKey || event.metaKey || event.altKey)) return;
            if (event.type === 'pointerdown' && !(event.target === node && event.button === 0
                && node.offsetWidth > node.clientWidth && event.offsetX >= node.clientWidth)) return;
            // A trusted scroll gesture can precede both the scroll event and
            // a transient clamp. In that ambiguous frame, never scroll on the
            // user's behalf or resurrect the old bottom-follow position.
            binding.pendingIntent = true;
            if (binding.intentFrame === undefined && typeof requestAnimationFrame === 'function') {
                binding.intentFrame = requestAnimationFrame(() => {
                    binding.intentFrame = undefined;
                    binding.pendingIntent = false;
                    if (scroller === binding) sampleScroll(binding);
                });
            }
        };
        binding.hook = function (...args) {
            // Gradio 4.29's afterUpdate is a two-number bottom scroll. Leave
            // arbitrary coordinates, options overloads and borrowed calls alone.
            if (this !== node || restoringScroll || args.length !== 2 || args[0] !== 0
                || typeof args[1] !== 'number' || args[1] !== node.scrollHeight
                || globalThis.chuanhuInputConversation?.() !== conversation) {
                return original.apply(this, args);
            }
            const current = Array.from(app.querySelectorAll('#chuanhu-chatbot .agent-history-detail'));
            const replacing = current.some(detail => owned(detail, conversation) && persistent(detail)
                && (!nodeStates.has(detail) || nodeStates.get(detail).key !== detailKey(detail))
                && (expanded.has(detailKey(detail)) || currentNodes.has(detailKey(detail))));
            if (!replacing) return original.apply(this, args);
            // The argument's scrollHeight was already measured by Gradio.
            // Restore within this same call, before native scroll/next paint.
            // Never derive reader intent from that transient collapsed layout.
            const {top, following, clamped, intent} = scrollPosition(binding, args[1]);
            restoringScroll = true;
            try {
                const restored = tick();
                if (restored && intent) return;
                return original.apply(this, restored
                    ? [0, following ? node.scrollHeight : clamped ? top : node.scrollTop] : args);
            } finally {
                restoringScroll = false;
                sampleScroll(binding);
            }
        };
        try { Object.defineProperty(node, 'scrollTo', {configurable: true, writable: true, value: binding.hook}); }
        catch (_) { return; } // A non-configurable host wrapper is left untouched.
        scroller = binding;
        node.addEventListener('scroll', binding.onScroll, {passive: true});
        for (const name of ['wheel', 'keydown', 'touchmove', 'pointerdown']) node.addEventListener(name, binding.onIntent, {capture: true, passive: true});
        sampleScroll(binding);
    }
    function clearRestoreMarkers() {
        for (const detail of currentNodes.values()) delete detail.dataset.restoringOpen;
    }
    function finishRestoration() {
        // One pending frame, consulting only the latest bindings. Streaming
        // replacements cannot queue callbacks retaining detached predecessors.
        if (restoreFrame === undefined) restoreFrame = requestAnimationFrame(() => {
            restoreFrame = undefined;
            clearRestoreMarkers();
        });
    }
    const explicitIntent = new WeakSet();
    function persistent(detail) {
        return detail.dataset.activityKey && detail.dataset.persistOpen !== 'false';
    }
    function save(key, open) {
        expanded.set(key, open);
        if (expanded.size > 1000) expanded.delete(expanded.keys().next().value);
    }
    function rememberToggle(event) {
        const detail = event.target;
        const app = typeof gradioApp === 'function' ? gradioApp() : document;
        if (!detail?.matches?.('#chuanhu-chatbot .agent-history-detail')
            || !owned(detail, globalThis.chuanhuInputConversation?.()) || !persistent(detail)
            || detail.isConnected === false
            || !Array.from(app.querySelectorAll('#chuanhu-chatbot .agent-history-detail')).includes(detail)) return;
        // A late event from a removed predecessor cannot overwrite the new
        // node. Native open is sampled synchronously, before queued toggle.
        explicitIntent.add(detail);
        tick();
    }
    document.addEventListener('toggle', rememberToggle, true);
    let timer;
    function tick(records = []) {
        const app = typeof gradioApp === 'function' ? gradioApp() : document;
        const conversation = globalThis.chuanhuInputConversation?.();
        let running = false;
        const details = Array.from(app.querySelectorAll('#chuanhu-chatbot .agent-history-detail'));
        bindScroller(app, conversation, details);
        const scrollBefore = scroller && scrollPosition(scroller);
        const restored = [];
        // Drain attributes even when a timer runs before the observer callback.
        // This captures a new node's user choice before first cache restoration.
        for (const record of [...(records || []), ...(observer.takeRecords?.() || [])]) {
            if (record.type === 'attributes' && record.attributeName === 'open'
                && !nodeStates.has(record.target)) explicitIntent.add(record.target);
        }
        // Sample predecessors before replacing them, including detached nodes:
        // their last DOM open may contain a click whose toggle is still queued.
        for (const [key, node] of currentNodes) {
            const state = nodeStates.get(node);
            if (state && detailKey(node) === key && node.open !== state.open) {
                save(key, node.open); state.open = node.open;
            }
        }
        const nextNodes = new Map();
        for (const detail of details) {
            if (!owned(detail, conversation) || !persistent(detail)) continue;
            const key = detailKey(detail);
            let state = nodeStates.get(detail);
            if (!state || state.key !== key) {
                // Restore only a newly encountered DOM binding. Any open
                // attribute change or current toggle on that node wins.
                if (explicitIntent.has(detail)) save(key, detail.open);
                else if (expanded.has(key) && detail.open !== expanded.get(key)) {
                    // Restoring a replacement is not a user disclosure action.
                    // Resolve its final layout with transitions disabled before
                    // the next paint, without a separate animation state.
                    detail.dataset.restoringOpen = 'true';
                    detail.open = expanded.get(key);
                    restored.push(detail);
                    if (typeof requestAnimationFrame === 'function') {
                        finishRestoration();
                    } else delete detail.dataset.restoringOpen;
                }
                else save(key, detail.open);
                state = {key, open: detail.open}; nodeStates.set(detail, state);
            } else if (detail.open !== state.open || explicitIntent.has(detail)) {
                save(key, detail.open); state.open = detail.open;
            }
            explicitIntent.delete(detail);
            nextNodes.set(key, detail);
        }
        // Resolve nested outer/inner state together, never measure midway.
        if (restored.length) globalThis.getComputedStyle?.(restored[0], '::details-content').height;
        for (const [key, detail] of currentNodes) {
            if (nextNodes.get(key) !== detail) delete detail.dataset.restoringOpen;
        }
        currentNodes.clear();
        for (const [key, detail] of nextNodes) currentNodes.set(key, detail);
        for (const node of app.querySelectorAll('#chuanhu-chatbot .agent-activity-elapsed')) {
            const detail = node.closest('.agent-history-detail');
            if (!owned(detail, conversation) || detail.dataset.layer !== 'group') continue;
            if (node.dataset.running !== 'true') continue;
            const base = Number(node.dataset.elapsedMs);
            if (!Number.isFinite(base) || base < 0 || base > 31536000000) continue;
            let clock = clocks.get(node);
            if (!clock || clock.base !== base) {
                clock = {base, started: performance.now()}; clocks.set(node, clock);
            }
            const elapsed = base + Math.max(0, performance.now() - clock.started);
            const seconds = Math.floor(elapsed / 1000);
            const displayed = elapsed < 1000 ? (elapsed === 0 ? '0.0' : elapsed < 100 ? '0.1' : (Math.floor(elapsed / 100) / 10).toFixed(1)) : String(seconds < 60 ? seconds : seconds % 60);
            const format = seconds < 60 ? (node.dataset.secondsFormat || '{seconds}s') : (node.dataset.minutesFormat || '{minutes}m {seconds}s');
            const text = format.replaceAll('{minutes}', String(Math.floor(seconds / 60))).replaceAll('{seconds}', displayed);
            if (node.textContent !== text) node.textContent = text;
            running = true;
        }
        // When Gradio did not autoscroll (the user is reading), an earlier
        // collapsed measurement may still have clamped scrollTop. Recover the
        // saved position only after all disclosure states are restored.
        if (restored.length && scroller && scrollBefore && !restoringScroll
            && (scrollBefore.following || scrollBefore.clamped)) {
            restoringScroll = true;
            try { scroller.original.call(scroller.node, 0, scrollBefore.following ? scroller.node.scrollHeight : scrollBefore.top); }
            finally { restoringScroll = false; }
        }
        sampleScroll();
        if (running && timer === undefined) timer = setInterval(tick, 250);
        if (!running && timer !== undefined) { clearInterval(timer); timer = undefined; }
        return restored.length > 0;
    }
    const observer = new MutationObserver(tick);
    function start() { observer.observe(document.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['open'], attributeOldValue: true}); tick(); }
    globalThis.__chuanhuActivityCleanup = () => {
        observer.disconnect();
        releaseScroller();
        document.removeEventListener?.('toggle', rememberToggle, true);
        expanded.clear();
        if (restoreFrame !== undefined) globalThis.cancelAnimationFrame?.(restoreFrame);
        restoreFrame = undefined;
        clearRestoreMarkers();
        currentNodes.clear();
        if (timer !== undefined) clearInterval(timer);
        timer = undefined;
        document.removeEventListener?.('DOMContentLoaded', start);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
    else start();
})();
