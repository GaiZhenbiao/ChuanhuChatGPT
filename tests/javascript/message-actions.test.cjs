// Offline DOM integration: production chat refresh, message controls, capability
// observer and artifact delegation execute together against real Python markup.
// This intentionally makes no browser geometry, system clipboard or API claim.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const read = name => fs.readFileSync(path.join(__dirname, '../../web_assets/javascript', name), 'utf8');
const scripts = Object.fromEntries(['chat-list.js', 'message-button.js', 'model-capabilities.js', 'artifact-cards.js']
    .map(name => [name, read(name)]));
const chatSource = read('ChuanhuChat.js');
const refreshStart = chatSource.indexOf('function chatbotContentChanged(');
const refreshEnd = chatSource.indexOf('\nvar chatbotObserver', refreshStart);
assert(refreshStart >= 0 && refreshEnd > refreshStart, 'The real chat refresh function must be present');
const refreshSource = chatSource.slice(refreshStart, refreshEnd);

const escape = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const unescape = value => value.replace(/&(#x[\da-f]+|#\d+|quot|apos|lt|gt|amp|nbsp);/gi, (full, key) => {
    if (key[0] === '#') return String.fromCodePoint(parseInt(key.slice(key[1].toLowerCase() === 'x' ? 2 : 1), key[1].toLowerCase() === 'x' ? 16 : 10));
    return {quot: '"', apos: "'", lt: '<', gt: '>', amp: '&', nbsp: '\u00a0'}[key.toLowerCase()];
});
const dataAttribute = key => 'data-' + key.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase());
const voidTags = new Set(['br', 'hr', 'input', 'img', 'meta', 'link']);

function createDOM() {
    const microtasks = [], frames = [], timers = [], observers = [];
    function notify(target, type, attributeName) {
        for (const observer of observers) {
            if (!observer.target || !observer.options[type]) continue;
            if (type === 'attributes' && observer.options.attributeFilter && !observer.options.attributeFilter.includes(attributeName)) continue;
            if (observer.target !== target && (!observer.options.subtree || !observer.target.contains(target))) continue;
            observer.records.push({target, type, attributeName});
            if (observer.pending) continue;
            observer.pending = true;
            microtasks.push(() => {
                observer.pending = false;
                const records = observer.records.splice(0);
                if (records.length) observer.callback(records, observer);
            });
        }
    }
    class Element {
        constructor(tagName) {
            this.tagName = tagName.toLowerCase(); this.attributes = new Map();
            this.childNodes = []; this.parentElement = null; this._text = '';
            this.listeners = new Map(); this.style = {}; this.value = '';
            this.dataset = new Proxy({}, {
                get: (_, key) => this.attributes.get(dataAttribute(key)),
                set: (_, key, value) => { this.setAttribute(dataAttribute(key), value); return true; },
            });
            this.classList = {
                contains: name => this.className.split(/\s+/).includes(name),
                add: (...names) => names.forEach(name => this.classList.toggle(name, true)),
                remove: (...names) => names.forEach(name => this.classList.toggle(name, false)),
                toggle: (name, force) => {
                    const names = new Set(this.className.split(/\s+/).filter(Boolean));
                    const include = force === undefined ? !names.has(name) : !!force;
                    if (include) names.add(name); else names.delete(name);
                    this.className = [...names].join(' '); return include;
                },
            };
        }
        get children() { return this.childNodes.filter(node => node.tagName !== '#text'); }
        get parentNode() { return this.parentElement; }
        setAttribute(name, value) { this.attributes.set(name, String(value)); notify(this, 'attributes', name); }
        getAttribute(name) { return this.attributes.get(name) ?? null; }
        get className() { return this.getAttribute('class') || ''; }
        set className(value) { this.setAttribute('class', value); }
        get hidden() { return this.attributes.has('hidden'); }
        set hidden(value) { if (value) this.setAttribute('hidden', ''); else this.attributes.delete('hidden'); }
        get disabled() { return this.attributes.has('disabled'); }
        set disabled(value) { if (value) this.setAttribute('disabled', ''); else this.attributes.delete('disabled'); }
        get nextElementSibling() { return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] || null; }
        contains(node) { return node === this || this.childNodes.some(child => child.contains(node)); }
        append(...nodes) { for (const node of nodes) this.appendChild(node); }
        appendChild(node) { node.remove(); node.parentElement = this; this.childNodes.push(node); notify(this, 'childList'); return node; }
        removeChild(node) { assert.equal(node.parentElement, this); node.remove(); return node; }
        remove() {
            if (!this.parentElement) return;
            const parent = this.parentElement;
            parent.childNodes.splice(parent.childNodes.indexOf(this), 1); this.parentElement = null; notify(parent, 'childList');
        }
        after(node) {
            const parent = this.parentElement; assert(parent);
            node.remove(); node.parentElement = parent;
            parent.childNodes.splice(parent.childNodes.indexOf(this) + 1, 0, node); notify(parent, 'childList');
        }
        replaceChildren(...nodes) {
            for (const child of this.childNodes) child.parentElement = null;
            this.childNodes = []; this._text = ''; notify(this, 'childList'); this.append(...nodes);
        }
        matches(selector) {
            assert(!/[ ,>]/.test(selector), 'Unsupported simple selector: ' + selector);
            const attrs = [...selector.matchAll(/\[([^=\]]+)(?:="?([^"\]]*)"?)?\]/g)];
            const plain = selector.replace(/\[[^\]]+\]/g, '');
            const tag = plain.match(/^[a-z][\w-]*/i)?.[0];
            const id = plain.match(/#([\w-]+)/)?.[1];
            const classes = [...plain.matchAll(/\.([\w-]+)/g)].map(match => match[1]);
            return this.tagName !== '#text' && (!tag || this.tagName === tag.toLowerCase())
                && (!id || this.getAttribute('id') === id) && classes.every(name => this.classList.contains(name))
                && attrs.every(([, name, value]) => this.attributes.has(name) && (value === undefined || this.getAttribute(name) === value));
        }
        closest(selector) { for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node; return null; }
        querySelectorAll(selector) {
            const alternatives = selector.split(',').map(value => value.trim().split(/\s+/));
            const matches = node => alternatives.some(parts => {
                if (!node.matches(parts.at(-1))) return false;
                let ancestor = node.parentElement;
                for (let index = parts.length - 2; index >= 0; index--) {
                    while (ancestor && !ancestor.matches(parts[index])) ancestor = ancestor.parentElement;
                    if (!ancestor) return false;
                    ancestor = ancestor.parentElement;
                }
                return true;
            });
            const found = [];
            const walk = node => { for (const child of node.children) { if (matches(child)) found.push(child); walk(child); } };
            walk(this); return found;
        }
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
        get textContent() { return this._text + this.childNodes.map(child => child.textContent).join(''); }
        set textContent(value) { this.replaceChildren(); this._text = String(value); }
        get innerText() { return this.hidden || this.classList.contains('hideM') ? '' : this._text + this.childNodes.map(child => child.innerText).join(''); }
        get innerHTML() { return escape(this._text) + this.childNodes.map(child => child.outerHTML).join(''); }
        get outerHTML() {
            if (this.tagName === '#text') return escape(this._text);
            const attrs = [...this.attributes].map(([key, value]) => ` ${key}="${escape(value)}"`).join('');
            return `<${this.tagName}${attrs}>` + (voidTags.has(this.tagName) ? '' : this.innerHTML + `</${this.tagName}>`);
        }
        set innerHTML(markup) {
            this.replaceChildren(); const stack = [this];
            for (const match of markup.matchAll(/<!--[\s\S]*?-->|<\/(\w[\w-]*)\s*>|<(\w[\w-]*)([^>]*)>|([^<]+)/g)) {
                if (match[0].startsWith('<!--')) continue;
                if (match[1]) { assert.equal(stack.at(-1).tagName, match[1]); stack.pop(); }
                else if (match[2]) {
                    const node = new Element(match[2]);
                    for (const attr of match[3].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) node.setAttribute(attr[1], unescape(attr[2] || ''));
                    stack.at(-1).append(node);
                    if (!voidTags.has(node.tagName) && !match[3].trim().endsWith('/')) stack.push(node);
                } else { const node = new Element('#text'); node._text = unescape(match[4]); stack.at(-1).append(node); }
            }
            assert.equal(stack.length, 1, 'Production fixture markup must be balanced');
        }
        addEventListener(type, handler) {
            if (!this.listeners.has(type)) this.listeners.set(type, []);
            this.listeners.get(type).push(handler);
        }
        dispatchEvent(event) {
            event.target = this;
            const chain = []; for (let node = this; node; node = node.parentElement) chain.push(node);
            event.composedPath = () => chain;
            for (const node of chain) {
                for (const handler of node.listeners.get(event.type) || []) handler(event);
                if (!event.bubbles) break;
            }
            return true;
        }
        click() { if (!this.disabled) this.dispatchEvent({type: 'click', bubbles: true}); }
    }
    const document = new Element('document'); document.readyState = 'complete';
    document.createElement = tag => new Element(tag);
    document.documentElement = new Element('html'); document.body = new Element('body');
    document.append(document.documentElement); document.documentElement.append(document.body);
    class MutationObserver {
        constructor(callback) { this.callback = callback; this.records = []; observers.push(this); }
        observe(target, options) { this.target = target; this.options = options; }
        disconnect() { this.target = null; this.records = []; }
    }
    function flush() {
        let ticks = 0;
        while (microtasks.length || frames.length || timers.length) {
            assert(++ticks < 300, 'Production observers/timers must settle without a mutation loop');
            (microtasks.shift() || frames.shift() || timers.shift())();
        }
    }
    return {document, MutationObserver, microtasks, frames, timers, flush};
}

function fixture({history = 'empty', normal = false, snapshot = payload.initial, initialCaps = null} = {}) {
    const dom = createDOM(), {document} = dom, hits = [], copied = [], saved = [];
    const element = (tag, attrs = {}, text = '') => {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text) node.textContent = text;
        return node;
    };
    const chat = element('div', {id: 'chuanhu-chatbot'}), wrap = element('div', {class: 'message-wrap'});
    chat.append(wrap);
    const source = element('div', {id: 'model-output-cards'}), native = element('div', {id: 'model-output-native-files'});
    const retryBox = element('div', {id: 'model-output-retry-id'}), input = element('textarea'); retryBox.append(input);
    input.addEventListener('input', () => hits.push('input:' + input.value));
    const markerBox = element('div', {id: 'model-capability-state'}), marker = element('span'); markerBox.append(marker);
    const indicator = element('div', {class: 'hide translucent'});
    document.body.append(chat, source, native, retryBox, markerBox, indicator);
    for (const id of ['model-output-retry', 'gr-retry-btn', 'gr-dellast-btn', 'gr-like-btn', 'gr-dislike-btn',
        'gr-history-download-json-btn', 'export-chat-btn', 'gr-history-save-btn', 'gr-history-delete-btn']) {
        const button = element('button', {id});
        button.addEventListener('click', () => hits.push(id === 'model-output-retry' ? 'retry:' + input.value : id));
        document.body.append(button);
    }
    const historyList = element('fieldset', {id: 'history-select-dropdown'});
    if (history !== 'missing') document.body.append(historyList);
    if (history === 'populated') {
        const label = element('label', {class: 'selected'}); label.append(element('span', {}, 'Saved conversation')); historyList.append(label);
    }
    function setCaps(caps, conversation = snapshot.conversation) {
        marker.dataset.modelCapabilities = JSON.stringify({...caps, input_target: conversation, busy: false});
    }
    function replace(snapshotValue, ordinary = false) {
        snapshot = snapshotValue; wrap.replaceChildren();
        for (const [, markup] of ordinary ? [[null, payload.ordinary]] : snapshot.rows) {
            if (markup === null) continue;
            const row = element('div', {class: 'message-row bot-row'});
            const bubble = element('div', {class: 'message bot message-bubble-border'});
            bubble.innerHTML = markup; row.append(bubble); wrap.append(row);
        }
        source.innerHTML = ordinary ? '' : snapshot.cards;
        native.replaceChildren(element('span', {'data-testid': 'block-label'}, JSON.stringify(snapshot.nativeIds)));
        for (const id of snapshot.nativeIds) {
            const td = element('td', {class: 'download'}), link = element('a', {href: '/file/' + id}, 'same.txt');
            link.addEventListener('click', () => hits.push('file:' + id)); td.append(link); native.append(td);
        }
        setCaps(ordinary ? payload.normalCaps : payload.agentCaps);
    }
    replace(snapshot, normal);
    if (initialCaps !== null) setCaps(initialCaps);
    const context = vm.createContext({
        document, gradioApp: () => document, chatbotIndicator: indicator,
        MutationObserver: dom.MutationObserver,
        queueMicrotask: callback => dom.microtasks.push(callback), requestAnimationFrame: callback => dom.frames.push(callback),
        setTimeout: callback => { dom.timers.push(callback); return dom.timers.length; },
        setInterval: () => { throw new Error('Unexpected interval outside the completed-chat fixture'); }, clearInterval() {},
        navigator: {clipboard: {writeText: async text => { copied.push(text); }}},
        Event: class { constructor(type, options) { this.type = type; Object.assign(this, options); } },
        TextDecoder,
        atob: value => Buffer.from(value, 'base64').toString('binary'),
        saveHistoryHtml: () => saved.push(wrap.innerHTML),
        disableSendBtn() {}, updateCheckboxes() {}, bindFancyBox() {}, bindChatbotPlaceholderButtons() {},
        i18n: value => value, regenerate_i18n: 'Regenerate', deleteRound_i18n: 'Delete',
        console: {error: (...args) => { throw new Error(args.join(' ')); }},
    });
    context.window = context;
    for (const [name, text] of Object.entries(scripts)) vm.runInContext(text, context, {filename: name});
    vm.runInContext(refreshSource, context, {filename: 'ChuanhuChat.js'});
    dom.flush();
    function refresh() { context.chatbotContentChanged(1); dom.flush(); }
    const rows = () => wrap.querySelectorAll('.message-row.bot-row');
    const bubble = row => row.querySelector('.message.bot');
    const owned = row => row.nextElementSibling?.querySelectorAll('.model-file-card') || [];
    return {dom, document, chat, wrap, source, native, historyList, marker, context, hits, copied, saved,
        replace, setCaps, refresh, rows, bubble, owned};
}

const ids = cards => cards.map(card => card.dataset.artifactId);
const button = (f, row, className) => f.bubble(row).querySelector('.' + className);
async function copy(f, row, expected = payload.raw) {
    button(f, row, 'copy-bot-btn').click(); await Promise.resolve(); f.dom.flush();
    assert.equal(f.copied.at(-1), expected, 'Copy must retain exact assistant Markdown, Unicode and newlines');
    for (const forbidden of ['data-agent-message', 'same.txt', '/tmp/private-', '下载失败', 'Regenerate', 'Delete']) {
        assert(!f.copied.at(-1).includes(forbidden), 'Copy must exclude metadata, cards, paths and actions: ' + forbidden);
    }
}
const tests = [];
function test(name, run) { tests.push({name, run}); }

for (const history of ['empty', 'populated', 'missing']) {
    test(`real chat refresh mounts read-only actions with ${history} history`, async () => {
        const f = fixture({history}); f.refresh();
        for (const row of f.rows().slice(0, 2)) {
            assert.equal(f.bubble(row).querySelectorAll('.copy-bot-btn').length, 1);
            assert.equal(f.bubble(row).querySelectorAll('.toggle-md-btn').length, 1);
            assert.equal(button(f, row, 'copy-bot-btn').hidden, false);
            assert.equal(button(f, row, 'toggle-md-btn').hidden, false);
            await copy(f, row);
        }
        if (history === 'populated') {
            assert.equal(f.historyList.querySelector('label').style.pointerEvents, 'auto');
            assert(f.historyList.querySelector('#history-rename-btn'), 'The real selected-history controls still mount');
        }
        assert(f.saved.length > 0, 'The same real refresh continues through history persistence');
    });
}

test('Markdown toggles preserve stable ownership for identical replies and download/retry delegation', async () => {
    const f = fixture(); f.refresh();
    const [first, second] = f.rows();
    const firstKey = first.querySelector('.agent-message-anchor').dataset.messageKey;
    const secondKey = second.querySelector('.agent-message-anchor').dataset.messageKey;
    assert.notEqual(firstKey, secondKey, 'Same answer text in different turns must have distinct identities');
    for (let round = 0; round < 3; round++) {
        for (const row of [first, second]) {
            button(f, row, 'toggle-md-btn').click(); f.dom.flush();
            assert(f.bubble(row).querySelector('.md-message').classList.contains('hideM'));
            assert(!f.bubble(row).querySelector('.raw-message').classList.contains('hideM'));
            await copy(f, row);
            button(f, row, 'toggle-md-btn').click(); f.dom.flush();
            assert(!f.bubble(row).querySelector('.md-message').classList.contains('hideM'));
            assert(f.bubble(row).querySelector('.raw-message').classList.contains('hideM'));
        }
        assert.deepEqual(ids(f.owned(first)), ['ready-first', 'failed-first']);
        assert.deepEqual(ids(f.owned(second)), ['ready-second']);
        assert.equal(first.nextElementSibling.dataset.fileOwner, 'conversation:' + firstKey);
        assert.equal(second.nextElementSibling.dataset.fileOwner, 'conversation:' + secondKey);
        assert.equal(f.chat.querySelectorAll('.agent-message-files').length, 3);
        f.owned(first)[0].click(); f.owned(second)[0].click(); f.owned(first)[1].click(); f.dom.flush();
    }
    assert.equal(f.hits.filter(hit => hit === 'file:ready-first').length, 3);
    assert.equal(f.hits.filter(hit => hit === 'file:ready-second').length, 3);
    assert.equal(f.hits.filter(hit => hit === 'input:failed-first').length, 3);
    assert.equal(f.hits.filter(hit => hit === 'retry:failed-first').length, 3);
    assert(f.saved.some(markup => markup.includes('class="md-message hideM"')), 'Raw mode reaches the history snapshot callback');
});

test('restored and shortened rerenders rebind fresh controls and cards by message identity', async () => {
    const f = fixture({history: 'populated'}); f.refresh();
    const oldRows = f.rows(), oldKeys = oldRows.map(row => row.querySelector('.agent-message-anchor').dataset.messageKey);
    f.replace(payload.restored); f.refresh();
    assert(oldRows.every(row => row.parentElement === null));
    assert.deepEqual(f.rows().map(row => row.querySelector('.agent-message-anchor').dataset.messageKey), oldKeys);
    assert.deepEqual(ids(f.owned(f.rows()[0])), ['ready-first', 'failed-first']);
    assert.deepEqual(ids(f.owned(f.rows()[1])), ['ready-second']);
    await copy(f, f.rows()[1]);
    button(f, f.rows()[1], 'toggle-md-btn').click(); f.dom.flush();
    f.owned(f.rows()[0])[1].click(); f.owned(f.rows()[1])[0].click(); f.dom.flush();
    assert(f.hits.includes('retry:failed-first') && f.hits.includes('file:ready-second'));
    assert(f.chat.querySelectorAll('.agent-message-files').every(holder => holder.dataset.fileOwner.startsWith('restored:')));
    f.replace(payload.shortened); f.refresh();
    assert.equal(f.rows()[0].querySelector('.agent-message-anchor').dataset.messageKey, oldKeys[1]);
    assert.deepEqual(ids(f.owned(f.rows()[0])), ['ready-second'], 'Shortening history must not move first-turn files to surviving row 0');
    await copy(f, f.rows()[0]);
});

test('file-only bubble gets the hide marker while its separate card remains actionable', () => {
    const f = fixture(); f.refresh();
    const row = f.rows()[2];
    assert(row.classList.contains('agent-file-only-message'));
    assert(row.classList.contains('agent-message-has-files'));
    assert.equal(f.bubble(row).querySelector('.raw-message').textContent, '');
    assert.deepEqual(ids(f.owned(row)), ['file-only']);
    assert.equal(f.owned(row)[0].closest('.message.bot'), null, 'File-only cards must be outside the hidden text bubble');
    f.owned(row)[0].click(); f.dom.flush(); assert(f.hits.includes('file:file-only'));
    f.source.innerHTML = ''; f.dom.flush();
    assert(!row.classList.contains('agent-file-only-message'), 'Removing cards clears stale file-only hiding');
    assert(!row.classList.contains('agent-message-has-files'));
});

test('message actions stay closed until capabilities arrive, then ordinary actions restore', async () => {
    const f = fixture({initialCaps: {}}); f.refresh();
    const row = f.rows().at(-1);
    for (const className of ['regenerate-btn', 'delete-latest-btn']) {
        const control = button(f, row, className);
        assert(control.hidden, 'Unknown capability must not briefly expose ' + className);
        control.dispatchEvent({type: 'click', bubbles: true});
    }
    assert(!f.hits.includes('gr-retry-btn') && !f.hits.includes('gr-dellast-btn'));
    f.setCaps(payload.agentCaps); f.dom.flush();
    for (const className of ['regenerate-btn', 'delete-latest-btn']) assert(button(f, row, className).hidden);
    f.setCaps(payload.normalCaps); f.dom.flush();
    for (const className of ['regenerate-btn', 'delete-latest-btn']) {
        assert(!button(f, row, className).hidden); button(f, row, className).click();
    }
    assert(f.hits.includes('gr-retry-btn') && f.hits.includes('gr-dellast-btn'));
});

test('Agent read-only capabilities stay enabled while regeneration and deletion do nothing', async () => {
    assert.equal(payload.agentCaps.message_copy, true);
    assert.equal(payload.agentCaps.message_markdown, true);
    const f = fixture(); f.refresh();
    const latest = f.rows().at(-1);
    for (const className of ['regenerate-btn', 'delete-latest-btn']) {
        const control = button(f, latest, className); assert(control.hidden);
        // dispatchEvent bypasses disabled .click() to exercise the real handler guard.
        control.dispatchEvent({type: 'click', bubbles: true});
    }
    assert(!f.hits.includes('gr-retry-btn') && !f.hits.includes('gr-dellast-btn'));
    await copy(f, f.rows()[0]);
});

test('ordinary models retain copy, Markdown, regeneration and deletion after Agent mode', async () => {
    assert.equal(payload.normalCaps.message_copy, true);
    assert.equal(payload.normalCaps.message_markdown, true);
    const f = fixture(); f.refresh(); f.replace(payload.initial, true); f.refresh();
    const row = f.rows()[0];
    const literal=f.document.createElement('div'); literal.classList.add('raw-message'); literal.textContent='LITERAL_BODY_MUST_NOT_DUPLICATE';
    f.bubble(row).querySelector('.md-message').append(literal);
    await copy(f, row, payload.ordinaryRaw);
    button(f, row, 'toggle-md-btn').click(); f.dom.flush();
    assert(f.bubble(row).querySelector('.md-message').classList.contains('hideM'));
    for (const className of ['regenerate-btn', 'delete-latest-btn']) {
        assert(!button(f, row, className).hidden); button(f, row, className).click();
    }
    assert(f.hits.includes('gr-retry-btn') && f.hits.includes('gr-dellast-btn'));
    assert.equal(f.chat.querySelectorAll('.agent-message-files').length, 0);
});

test('each read-only capability gates only its own control and guards already mounted handlers', async () => {
    const f = fixture(); f.refresh(); const row = f.rows()[0];
    const staleCopy = button(f, row, 'copy-bot-btn');
    f.setCaps({...payload.agentCaps, message_copy: false}); f.dom.flush();
    assert(staleCopy.hidden); assert(!button(f, row, 'toggle-md-btn').hidden);
    staleCopy.dispatchEvent({type: 'click', bubbles: true}); await Promise.resolve();
    assert.equal(f.copied.length, 0);
    button(f, row, 'toggle-md-btn').click(); f.dom.flush();
    assert(f.bubble(row).querySelector('.md-message').classList.contains('hideM'));
    const staleToggle = button(f, row, 'toggle-md-btn');
    f.setCaps({...payload.agentCaps, message_markdown: false}); f.dom.flush();
    assert(staleToggle.hidden); assert(!button(f, row, 'copy-bot-btn').hidden);
    staleToggle.dispatchEvent({type: 'click', bubbles: true}); f.dom.flush();
    assert(f.bubble(row).querySelector('.md-message').classList.contains('hideM'), 'Disallowed stale toggle must not change display mode');
    await copy(f, row);
});

test('copy rejects malformed or mismatched Agent markers and uses the ordinary raw fallback', async () => {
    const corruptions = [
        data => { data.v = 2; },
        data => { data.role = 'user'; },
        data => { data.raw = null; },
        data => { data.key = 'different-message'; },
        data => { data.conversation = 'different-conversation'; },
    ];
    for (const corrupt of corruptions) {
        const f = fixture(); f.refresh(); const row = f.rows()[0];
        const anchor = row.querySelector('.agent-message-anchor');
        const data = JSON.parse(Buffer.from(anchor.dataset.agentMessageRaw, 'base64').toString('utf8'));
        corrupt(data); anchor.dataset.agentMessageRaw = Buffer.from(JSON.stringify(data)).toString('base64');
        await copy(f, row, payload.raw);
    }
    for (const [attribute, value] of [['agentMessageCell', 'user'], ['agentMessageRaw', 'invalid-base64']]) {
        const f = fixture(); f.refresh(); const row = f.rows()[0];
        row.querySelector('.agent-message-anchor').dataset[attribute] = value;
        await copy(f, row, payload.raw);
    }
});

(async () => {
    let failed = 0;
    for (const {name, run} of tests) {
        try { await run(); console.log('PASS ' + name); }
        catch (error) { failed++; console.error('FAIL ' + name + '\n' + error.stack); }
    }
    if (failed) process.exitCode = 1;
    else console.log(tests.length + ' message action regressions passed');
})();
