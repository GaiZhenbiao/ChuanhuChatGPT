// Offline regression of the production mount observer and delegated card clicks.
// The small DOM implements only standard operations exercised by this script;
// mounting, identity matching, scheduling and download/retry logic stay in the
// real artifact-cards.js. No browser, package install or network is required.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../../web_assets/javascript/artifact-cards.js'), 'utf8');

const escape = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const unescape = value => value.replace(/&quot;/g, '"').replace(/&#(?:x27|39);/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const dataAttribute = key => 'data-' + key.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase());

function createDOM(readyState = 'complete') {
    const microtasks = [], frames = [], observers = [];
    let mutations = 0;
    function notify(target, type) {
        mutations++;
        for (const observer of observers) {
            if (!observer.target || !observer.options[type]) continue;
            if (observer.target !== target && (!observer.options.subtree || !observer.target.contains(target))) continue;
            observer.records.push({target, type});
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
            this.tagName = tagName.toLowerCase();
            this.attributes = new Map();
            this.children = [];
            this.parentElement = null;
            this._text = '';
            this.listeners = new Map();
            this.value = '';
            this.innerHTMLWrites = 0;
            this.dataset = new Proxy({}, {
                get: (_, key) => this.attributes.get(dataAttribute(key)),
                set: (_, key, value) => {this.setAttribute(dataAttribute(key), value); return true;},
            });
            this.classList = {
                contains: name => this.className.split(/\s+/).includes(name),
                add: name => this.classList.toggle(name, true),
                remove: name => this.classList.toggle(name, false),
                toggle: (name, force) => {
                    const names = new Set(this.className.split(/\s+/).filter(Boolean));
                    const include = force === undefined ? !names.has(name) : !!force;
                    if (include) names.add(name); else names.delete(name);
                    this.className = [...names].join(' ');
                    return include;
                },
            };
        }
        setAttribute(name, value) {this.attributes.set(name, String(value)); notify(this, 'attributes');}
        getAttribute(name) {return this.attributes.get(name) ?? null;}
        removeAttribute(name) {this.attributes.delete(name);}
        get className() {return this.attributes.get('class') || '';}
        set className(value) {this.setAttribute('class', value);}
        get disabled() {return this.attributes.has('disabled');}
        set disabled(value) {if (value) this.setAttribute('disabled', ''); else this.attributes.delete('disabled');}
        get nextElementSibling() {
            return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] || null;
        }
        contains(node) {return node === this || this.children.some(child => child.contains(node));}
        append(...nodes) {
            for (const node of nodes) {
                node.remove(); node.parentElement = this; this.children.push(node); notify(this, 'childList');
            }
        }
        remove() {
            if (!this.parentElement) return;
            const parent = this.parentElement;
            parent.children.splice(parent.children.indexOf(this), 1); this.parentElement = null;
            notify(parent, 'childList');
        }
        after(node) {
            const parent = this.parentElement;
            assert(parent, 'after requires a parent');
            node.remove(); node.parentElement = parent;
            parent.children.splice(parent.children.indexOf(this) + 1, 0, node); notify(parent, 'childList');
        }
        replaceChildren(...nodes) {
            for (const child of this.children) child.parentElement = null;
            this.children = []; this._text = ''; notify(this, 'childList'); this.append(...nodes);
        }
        matches(selector) {
            assert(!/[ ,>]/.test(selector), 'Unsupported simple selector: ' + selector);
            const attrs = [...selector.matchAll(/\[([^=\]]+)(?:="?([^"\]]*)"?)?\]/g)];
            const plain = selector.replace(/\[[^\]]+\]/g, '');
            const tag = plain.match(/^[a-z][\w-]*/i)?.[0];
            const id = plain.match(/#([\w-]+)/)?.[1];
            const classes = [...plain.matchAll(/\.([\w-]+)/g)].map(match => match[1]);
            return (!tag || this.tagName === tag.toLowerCase()) && (!id || this.getAttribute('id') === id)
                && classes.every(name => this.classList.contains(name))
                && attrs.every(([, name, value]) => this.attributes.has(name) && (value === undefined || this.getAttribute(name) === value));
        }
        closest(selector) {for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node; return null;}
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
            const walk = node => {for (const child of node.children) {if (matches(child)) found.push(child); walk(child);}};
            walk(this); return found;
        }
        querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
        get textContent() {return this._text + this.children.map(child => child.textContent).join('');}
        set textContent(value) {this.replaceChildren(); this._text = String(value);}
        get outerHTML() {
            const attrs = [...this.attributes].map(([key, value]) => ` ${key}="${escape(value)}"`).join('');
            return `<${this.tagName}${attrs}>${escape(this._text)}${this.children.map(child => child.outerHTML).join('')}</${this.tagName}>`;
        }
        set innerHTML(markup) {
            this.innerHTMLWrites++;
            this.replaceChildren();
            const stack = [this];
            for (const match of markup.matchAll(/<\/(\w[\w-]*)\s*>|<(\w[\w-]*)([^>]*)>|([^<]+)/g)) {
                if (match[1]) {assert.equal(stack.at(-1).tagName, match[1]); stack.pop();}
                else if (match[2]) {
                    const node = new Element(match[2]);
                    for (const attr of match[3].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) node.setAttribute(attr[1], unescape(attr[2] || ''));
                    stack.at(-1).append(node); stack.push(node);
                } else stack.at(-1)._text += unescape(match[4]);
            }
            assert.equal(stack.length, 1, 'Fixture HTML must be balanced');
        }
        addEventListener(type, handler) {
            if (!this.listeners.has(type)) this.listeners.set(type, []);
            this.listeners.get(type).push(handler);
        }
        dispatchEvent(event) {
            event.target = this;
            const chain = []; for (let node = this; node; node = node.parentElement) chain.push(node);
            event.composedPath = () => chain;
            for (const node of chain) {for (const handler of node.listeners.get(event.type) || []) handler(event); if (!event.bubbles) break;}
            return true;
        }
        click() {if (!this.disabled) this.dispatchEvent({type: 'click', bubbles: true, preventDefault() {this.defaultPrevented = true;}});}
    }
    const document = new Element('document');
    document.readyState = readyState;
    document.createElement = tag => new Element(tag);
    document.documentElement = new Element('html');
    document.body = new Element('body');
    document.append(document.documentElement); document.documentElement.append(document.body);
    class MutationObserver {
        constructor(callback) {this.callback = callback; this.records = []; this.pending = false; observers.push(this);}
        observe(target, options) {this.target = target; this.options = options;}
    }
    function flush() {
        let count = 0;
        while (microtasks.length || frames.length) {
            assert(++count < 100, 'Mount observer never settles (self-triggered DOM mutation loop)');
            if (microtasks.length) microtasks.shift()(); else frames.shift()();
        }
    }
    return {document, flush, MutationObserver, microtasks, frames, observers, get mutations() {return mutations;}};
}

function fixture(options = {}) {
    const {loading = false, shadowRoot = false} = options;
    let activeConversation = options.activeConversation, context;
    const dom = createDOM(loading ? 'loading' : 'complete');
    const {document} = dom;
    const app = shadowRoot ? document.createElement('gradio-app') : document.body;
    if (shadowRoot) document.body.append(app);
    const element = (tag, attrs = {}, text = '') => {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text) node.textContent = text;
        return node;
    };
    const chat = element('div', {id: 'chuanhu-chatbot'});
    const cards = element('div', {id: 'model-output-cards'});
    const native = element('div', {id: 'model-output-native-files'});
    const retryBox = element('div', {id: 'model-output-retry-id'});
    const input = element('textarea'); retryBox.append(input);
    const retry = element('button', {id: 'model-output-retry', type: 'button'});
    const hits = [];
    input.addEventListener('input', () => hits.push('input:' + input.value));
    retry.addEventListener('click', () => hits.push('retry:' + input.value));
    app.append(chat, cards, native, retryBox, retry);
    function row(key, conversation = 'conversation', raw = 'same answer', history = false) {
        const node = element('div', {class: 'message-row bot-row' + (history ? ' history-message' : '')});
        const bubble = element('div', {class: 'message bot message-bubble-border'}, raw ?? '');
        const anchor = element('span', {class: 'agent-message-anchor', 'data-message-key': key,
            'data-conversation-id': conversation, 'data-agent-message-raw': Buffer.from(JSON.stringify({raw})).toString('base64')});
        bubble.append(anchor); node.append(bubble); return node;
    }
    function card(id, key, conversation = 'conversation', state = 'ready', name = 'same.txt') {
        const action = state === 'failed' ? 'retry' : state === 'ready' ? 'download' : '';
        const node = element('button', {type: 'button', class: 'model-file-card', 'data-artifact-id': id,
            'data-message-key': key, 'data-conversation-id': conversation, 'data-file-action': action,
            'aria-label': name});
        if (!action) node.disabled = true;
        node.append(element('span', {class: 'model-file-name'}, name), element('span', {class: 'model-file-state'}, state),
            element('span', {class: 'model-file-feedback', 'aria-live': 'polite'}));
        return node;
    }
    function nativeFiles(ids, linkIds = ids) {
        const label = element('span', {'data-testid': 'block-label'}, JSON.stringify(ids));
        native.replaceChildren(label);
        for (const id of linkIds) {
            const td = element('td', {class: 'download'});
            const link = element('a', {href: '/file/' + id}, 'same.txt');
            link.addEventListener('click', () => hits.push('file:' + id)); td.append(link); native.append(td);
        }
    }
    function start() {
        context = {document, MutationObserver: dom.MutationObserver,
            queueMicrotask: callback => dom.microtasks.push(callback),
            requestAnimationFrame: callback => dom.frames.push(callback),
            Event: class {constructor(type, options) {this.type = type; Object.assign(this, options);}},
            atob: value => Buffer.from(value, 'base64').toString('binary'),
            ...(shadowRoot ? {gradioApp: () => app} : {}),
            ...('activeConversation' in options ? {chuanhuInputConversation: () => activeConversation} : {})};
        vm.runInNewContext(source, context);
        dom.flush();
    }
    function setActiveConversation(value) {activeConversation = value; context.chuanhuRefreshArtifactCards(); dom.flush();}
    const holders = () => chat.querySelectorAll('.agent-message-files');
    const owned = node => node.nextElementSibling?.querySelectorAll('.model-file-card') || [];
    return {dom, document, app, chat, cards, native, retry, input, row, card, nativeFiles, start, hits, holders, owned, setActiveConversation};
}

let passed = 0, failed = 0;
function test(name, run) {
    try {run(); passed++; console.log('PASS ' + name);}
    catch (error) {failed++; console.error('FAIL ' + name + '\n' + error.stack);}
}
const ids = nodes => nodes.map(node => node.dataset.artifactId);

test('two turns mount cloned cards beside the correct row and settle after observer delivery', () => {
    const f = fixture();
    const first = f.row('first'), second = f.row('second');
    const sourceFirst = f.card('file-1', 'first'), sourceSecond = f.card('file-2', 'second');
    f.chat.append(first, second); f.cards.append(sourceSecond, sourceFirst); f.start();
    assert.deepEqual(ids(f.owned(first)), ['file-1']); assert.deepEqual(ids(f.owned(second)), ['file-2']);
    assert.equal(f.holders().length, 2);
    assert.notEqual(f.owned(first)[0], sourceFirst); assert.equal(sourceFirst.parentElement, f.cards);
    assert.equal(first.nextElementSibling.getAttribute('role'), 'group');
    assert.equal(first.nextElementSibling.getAttribute('aria-label'), '此回复生成的文件');
    assert(first.classList.contains('agent-message-has-files'));
    assert(second.classList.contains('agent-message-has-files'));
    assert.equal(f.dom.microtasks.length, 0);
    assert.equal(f.dom.observers.length, 1);
    assert.equal(f.dom.observers[0].target, f.document.documentElement);
});

test('adding a file in the last turn preserves earlier holder and card DOM identity', () => {
    const f = fixture(); const first = f.row('first'), last = f.row('last');
    f.chat.append(first, last); f.cards.append(f.card('old', 'first'), f.card('new', 'last')); f.start();
    const oldHolder = first.nextElementSibling, oldCard = f.owned(first)[0];
    f.cards.append(f.card('newer', 'last')); f.dom.flush();
    assert.deepEqual(ids(f.owned(last)), ['new', 'newer']);
    assert.equal(first.nextElementSibling, oldHolder); assert.equal(f.owned(first)[0], oldCard);
    assert.equal(oldHolder.innerHTMLWrites, 1);
    // An unrelated render still must not destroy a focused/clicked old card.
    f.app.append(f.document.createElement('div')); f.dom.flush();
    assert.equal(f.owned(first)[0], oldCard); assert.equal(f.holders().length, 2);
});

test('row reorder and row replacement move existing holders and remove detached owners', () => {
    const f = fixture(); const first = f.row('first'), second = f.row('second');
    f.chat.append(first, second); f.cards.append(f.card('one', 'first'), f.card('two', 'second')); f.start();
    const firstHolder = first.nextElementSibling, secondHolder = second.nextElementSibling;
    f.chat.append(first); f.dom.flush();
    assert.equal(first.nextElementSibling, firstHolder); assert.equal(second.nextElementSibling, secondHolder);
    const replacement = f.row('first'); first.after(replacement); first.remove(); f.dom.flush();
    assert.equal(replacement.nextElementSibling, firstHolder); assert.equal(f.holders().length, 2);
    second.remove(); f.dom.flush();
    assert.equal(secondHolder.parentElement, null); assert.equal(f.holders().length, 1);
    const restored = f.row('second'); f.chat.replaceChildren(restored); f.dom.flush();
    assert.deepEqual(ids(f.owned(restored)), ['two']); assert.equal(f.holders().length, 1);
    assert.equal(firstHolder.parentElement, null);
});

test('restored repeated text uses message keys, ignores history clones, and rejects ambiguity', () => {
    const f = fixture(); const first = f.row('first'), second = f.row('second');
    const historical = f.row('first', 'conversation', 'same answer', true);
    f.chat.append(first, historical, second); f.cards.append(f.card('one', 'first'), f.card('two', 'second')); f.start();
    assert.deepEqual(ids(f.owned(first)), ['one']); assert.deepEqual(ids(f.owned(second)), ['two']);
    assert.equal(historical.nextElementSibling, second);
    const ambiguous = f.row('first'); f.chat.append(ambiguous); f.dom.flush();
    assert.equal(f.holders().length, 1); assert.deepEqual(ids(f.owned(second)), ['two']);
    assert.equal(f.owned(first).length, 0); assert.equal(f.owned(ambiguous).length, 0);
    assert(!first.classList.contains('agent-message-has-files'));
    assert(!ambiguous.classList.contains('agent-message-has-files'));
    ambiguous.remove(); f.dom.flush(); assert.deepEqual(ids(f.owned(first)), ['one']);
});

test('conversation switch never attaches stale cards even when message keys repeat', () => {
    const f = fixture(); const old = f.row('same');
    f.chat.append(old); f.cards.append(f.card('old-file', 'same')); f.start();
    const current = f.row('same', 'new-conversation');
    f.chat.replaceChildren(current); f.dom.flush(); assert.equal(f.holders().length, 0);
    f.cards.append(f.card('new-file', 'same', 'new-conversation')); f.dom.flush();
    assert.deepEqual(ids(f.owned(current)), ['new-file']);
    f.cards.replaceChildren(f.card('old-file', 'same')); f.dom.flush(); assert.equal(f.holders().length, 0);
});

test('unknown, missing, orphaned and non-assistant anchors never borrow a nearby row', () => {
    const f = fixture(); const row = f.row('known'); const user = f.row('user'); user.className = 'message-row user-row';
    const orphan = f.row('orphan').querySelector('.agent-message-anchor');
    f.chat.append(row, user, orphan);
    f.cards.append(f.card('unknown', 'unknown'), f.card('missing-key', ''), f.card('missing-conversation', 'known', ''),
        f.card('user-file', 'user'), f.card('orphan-file', 'orphan'));
    f.start(); assert.equal(f.holders().length, 0);
    assert.equal(f.chat.querySelectorAll('.agent-message-has-files').length, 0);
});

test('active conversation refresh clears even matching stale chat and source without a DOM mutation', () => {
    const f = fixture({activeConversation: 'conversation'}); const stale = f.row('same', 'conversation', '');
    f.chat.append(stale); f.cards.append(f.card('old-file', 'same')); f.start();
    assert.deepEqual(ids(f.owned(stale)), ['old-file']);
    f.setActiveConversation('new-conversation');
    assert.equal(f.holders().length, 0); assert(!stale.classList.contains('agent-file-only-message'));
    assert(!stale.classList.contains('agent-message-has-files'));
    // A late render contains mutually matching old cards and rows. They still
    // must not appear in the newly selected model/conversation.
    f.cards.replaceChildren(f.card('old-file', 'same')); f.chat.replaceChildren(f.row('same')); f.dom.flush();
    assert.equal(f.holders().length, 0);
    const current = f.row('same', 'new-conversation');
    f.chat.replaceChildren(current); f.cards.replaceChildren(f.card('new-file', 'same', 'new-conversation')); f.dom.flush();
    assert.deepEqual(ids(f.owned(current)), ['new-file']);
    f.setActiveConversation(null); assert.equal(f.holders().length, 0);
});

test('file-only rows hide the empty bubble and recover when files or ownership disappear', () => {
    const f = fixture(); const empty = f.row('empty', 'conversation', ''), none = f.row('none', 'conversation', null);
    const text = f.row('text'), malformed = f.row('malformed', 'conversation', '');
    const avatar = f.document.createElement('div'); avatar.className = 'avatar-container'; text.append(avatar);
    malformed.querySelector('.agent-message-anchor').dataset.agentMessageRaw = 'not-json';
    f.chat.append(empty, none, text, malformed);
    f.cards.append(f.card('empty-file', 'empty'), f.card('none-file', 'none'), f.card('text-file', 'text'), f.card('bad-file', 'malformed'));
    f.start();
    assert(empty.classList.contains('agent-file-only-message')); assert(none.classList.contains('agent-file-only-message'));
    assert(!text.classList.contains('agent-file-only-message')); assert(!malformed.classList.contains('agent-file-only-message'));
    assert(text.nextElementSibling.classList.contains('agent-files-with-avatar'));
    assert(!empty.nextElementSibling.classList.contains('agent-files-with-avatar'));
    const duplicate = f.row('empty', 'conversation', ''); f.chat.append(duplicate); f.dom.flush();
    assert(!empty.classList.contains('agent-file-only-message')); assert(!duplicate.classList.contains('agent-file-only-message'));
    f.cards.replaceChildren(); f.dom.flush();
    assert.equal(f.holders().length, 0); assert.equal(f.chat.querySelectorAll('.agent-file-only-message').length, 0);
    assert.equal(f.chat.querySelectorAll('.agent-message-has-files').length, 0);
});

test('duplicate filenames download the real native link by ID across native reordering', () => {
    const f = fixture(); const first = f.row('first'), second = f.row('second');
    f.chat.append(first, second); f.cards.append(f.card('file-1', 'first'), f.card('file-2', 'second'));
    f.nativeFiles(['file-1', 'file-2']); f.start();
    f.owned(second)[0].querySelector('.model-file-name').click();
    f.nativeFiles(['file-2', 'file-1']); f.dom.flush(); f.owned(second)[0].click(); f.owned(first)[0].click();
    assert.deepEqual(f.hits, ['file:file-2', 'file:file-2', 'file:file-1']);
    assert.equal(f.owned(second)[0].tagName, 'button'); assert.equal(f.owned(second)[0].getAttribute('type'), 'button');
});

test('missing, malformed and out-of-sync native links show feedback without a wrong download', () => {
    const f = fixture(); const row = f.row('row'); f.chat.append(row); f.cards.append(f.card('file', 'row')); f.start();
    const click = () => {f.owned(row)[0].click(); f.dom.flush(); assert.equal(f.hits.length, 0);
        assert.match(f.owned(row)[0].querySelector('.model-file-feedback').textContent, /正在准备/);};
    click();
    f.nativeFiles(['unrelated']); f.dom.flush(); click();
    f.nativeFiles(['file', 'other'], ['file']); f.dom.flush(); click();
    f.nativeFiles(['file'], ['file', 'other']); f.dom.flush(); click();
    f.native.querySelector('[data-testid="block-label"]').textContent = 'invalid-json'; f.dom.flush(); click();
    f.nativeFiles(['file']); f.dom.flush(); f.owned(row)[0].click(); assert.deepEqual(f.hits, ['file:file']);
});

test('preparing to ready to failed rerenders remain bound to the same message and native retry', () => {
    const f = fixture({shadowRoot: true}); const row = f.row('turn');
    f.chat.append(row); f.cards.append(f.card('file', 'turn', 'conversation', 'preparing')); f.start();
    const holder = row.nextElementSibling;
    assert(f.owned(row)[0].disabled); f.owned(row)[0].click(); assert.deepEqual(f.hits, []);
    f.nativeFiles(['file']); f.cards.replaceChildren(f.card('file', 'turn')); f.dom.flush();
    assert.equal(row.nextElementSibling, holder); assert(!f.owned(row)[0].disabled);
    f.owned(row)[0].click(); assert.deepEqual(f.hits, ['file:file']);
    f.cards.replaceChildren(f.card('file', 'turn', 'conversation', 'failed')); f.dom.flush();
    const failedCard = f.owned(row)[0]; failedCard.querySelector('.model-file-name').click();
    assert.equal(f.input.value, 'file'); assert.deepEqual(f.hits, ['file:file', 'input:file']);
    f.dom.flush(); assert.deepEqual(f.hits, ['file:file', 'input:file', 'retry:file']);
    // Once the native callback renders preparing, the cloned button is disabled.
    f.cards.replaceChildren(f.card('file', 'turn', 'conversation', 'preparing')); f.dom.flush();
    f.owned(row)[0].click(); assert.deepEqual(f.hits, ['file:file', 'input:file', 'retry:file']);
    assert.equal(row.nextElementSibling, holder);
});

test('retry without native controls produces reconnect feedback', () => {
    const f = fixture(); const row = f.row('turn');
    f.chat.append(row); f.cards.append(f.card('file', 'turn', 'conversation', 'failed')); f.start();
    f.retry.remove(); f.dom.flush(); f.owned(row)[0].click(); f.dom.flush();
    assert.match(f.owned(row)[0].querySelector('.model-file-feedback').textContent, /重新连接/);
    assert.deepEqual(f.hits, []);
});

test('DOMContentLoaded defers mounting, then later source and chat renders are observed', () => {
    const f = fixture({loading: true}); const row = f.row('turn');
    f.chat.append(row); f.cards.append(f.card('file', 'turn')); f.start(); assert.equal(f.holders().length, 0);
    f.document.dispatchEvent({type: 'DOMContentLoaded'}); f.dom.flush(); assert.deepEqual(ids(f.owned(row)), ['file']);
    f.cards.remove(); f.dom.flush(); assert.equal(f.holders().length, 0);
    f.app.append(f.cards); f.dom.flush(); assert.deepEqual(ids(f.owned(row)), ['file']);
});

function bodyLink(f,row,href) {
    const md=f.document.createElement('div');md.className='md-message';
    const link=f.document.createElement('a');link.setAttribute('href',href);link.setAttribute('target','_blank');link.textContent='download';
    md.append(link);row.append(md);return link;
}

test('body file links match full path and current reply without guessing same basename',()=>{
    const f=fixture({activeConversation:'conversation'});const a=f.row('a'),b=f.row('b');
    const ca=f.card('file-a','a'),cb=f.card('file-b','b');
    ca.dataset.remotePath='/workspace/outputs/a/same.txt';cb.dataset.remotePath='/workspace/outputs/b/same.txt';
    const good=bodyLink(f,b,'sandbox:/workspace/outputs/b/same.txt');
    const wrong=bodyLink(f,b,'/workspace/outputs/a/same.txt');
    const outside=bodyLink(f,b,'https://example.com/workspace/outputs/b/same.txt');
    f.chat.append(a,b);f.cards.append(ca,cb);f.nativeFiles(['file-a','file-b']);f.start();
    good.click();assert.deepEqual(f.hits,['file:file-b']);
    assert.equal(good.dataset.artifactId,'file-b');assert.equal(good.getAttribute('target'),null);
    wrong.click();assert.deepEqual(f.hits,['file:file-b']);
    assert.match(wrong.nextElementSibling.textContent,/未发布或已过期/);
    assert.equal(outside.getAttribute('href'),'https://example.com/workspace/outputs/b/same.txt');
    assert.equal(outside.dataset.agentFileLink,undefined);
});

test('encoded, relative and artifact identities resolve but traversal and ambiguous paths do not',()=>{
    const f=fixture({activeConversation:'conversation'});const row=f.row('r');
    const card=f.card('owned','r');card.dataset.remotePath='/workspace/outputs/中文.txt';
    const encoded=bodyLink(f,row,'sandbox:/workspace/outputs/%E4%B8%AD%E6%96%87.txt');
    const relative=bodyLink(f,row,'outputs/中文.txt');const identity=bodyLink(f,row,'artifact://owned');
    const unsafe=bodyLink(f,row,'/workspace/outputs/../中文.txt');
    f.chat.append(row);f.cards.append(card);f.nativeFiles(['owned']);f.start();
    for(const link of [encoded,relative,identity]){link.click();assert.equal(link.dataset.artifactId,'owned');}
    assert.deepEqual(f.hits,['file:owned','file:owned','file:owned']);assert.equal(unsafe.dataset.agentFileLink,undefined);
    const duplicate=f.card('second','r');duplicate.dataset.remotePath=card.dataset.remotePath;
    f.cards.append(duplicate);f.dom.flush();encoded.click();assert.equal(encoded.dataset.artifactId,'');
    assert.equal(f.hits.length,3);
});

test('body link dispatches retry and rejects a stale conversation after navigation',()=>{
    const f=fixture({activeConversation:'conversation'});const row=f.row('r');const card=f.card('failed','r','conversation','failed');
    card.dataset.remotePath='/mnt/data/result.txt';const link=bodyLink(f,row,'/mnt/data/result.txt');
    f.chat.append(row);f.cards.append(card);f.start();link.click();f.dom.flush();
    assert.deepEqual(f.hits,['input:failed','retry:failed']);
    f.setActiveConversation('next');link.click();assert.equal(f.hits.length,2);
    assert.match(link.nextElementSibling.textContent,/未发布或已过期/);
});

test('body pending feedback disappears when its owned file becomes ready',()=>{
    const f=fixture({activeConversation:'conversation'});const row=f.row('r');
    const pending=f.card('owned','r','conversation','preparing');pending.dataset.remotePath='/workspace/outputs/result.txt';
    const link=bodyLink(f,row,'/workspace/outputs/result.txt');f.chat.append(row);f.cards.append(pending);f.start();
    link.click();f.dom.flush();assert.match(link.nextElementSibling.textContent,/正在准备/);
    const ready=f.card('owned','r');ready.dataset.remotePath=pending.dataset.remotePath;
    f.cards.replaceChildren(ready);f.nativeFiles(['owned']);f.dom.flush();
    assert(!link.nextElementSibling?.classList.contains('agent-link-feedback'));
    link.click();assert.deepEqual(f.hits,['file:owned']);
});

test('card and body downloads keep full Unicode filename and isolated native URL', () => {
    const f=fixture({activeConversation:'conversation'});const row=f.row('turn');const card=f.card('owned','turn');
    card.dataset.remotePath='/workspace/outputs/报告 空格.txt';card.dataset.downloadName='报告 空格.txt';
    const body=bodyLink(f,row,'artifact:owned');f.chat.append(row);f.cards.append(card);f.nativeFiles(['owned']);f.start();
    const native=f.native.querySelector('td.download a[href]');const original=native.getAttribute('href');
    f.owned(row)[0].click();assert.equal(native.getAttribute('download'),'报告 空格.txt');assert.equal(native.getAttribute('href'),original);
    body.click();assert.equal(native.getAttribute('download'),'报告 空格.txt');assert.equal(native.getAttribute('href'),original);
    assert.deepEqual(f.hits,['file:owned','file:owned']);
});


test('turn file section following text restores answer spacing without hiding text', () => {
    const f = fixture(), answer = f.row('answer'), files = f.row('files', 'conversation', '');
    const marker = f.document.createElement('small'); marker.className = 'agent-turn-files-after-answer'; files.append(marker);
    f.chat.append(answer, files); f.cards.append(f.card('file', 'files')); f.start();
    assert(!answer.classList.contains('agent-file-only-message'));
    assert(files.classList.contains('agent-file-only-message'));
    assert(files.nextElementSibling.classList.contains('agent-turn-files-after-answer'));
    files.replaceChildren(files.querySelector('.agent-message-anchor')); f.dom.flush();
    assert(!files.nextElementSibling.classList.contains('agent-turn-files-after-answer'));
});


test('late turn-only files mount below their exact reply before the canonical file row arrives', () => {
    const f=fixture({activeConversation:'conversation'}), answer=f.row('answer');
    const card=f.card('late','files');card.dataset.fileAfterKey='answer';
    const link=bodyLink(f,answer,'artifact:late');f.chat.append(answer);f.cards.append(card);f.nativeFiles(['late']);f.start();
    assert.deepEqual(ids(f.owned(answer)),['late']);
    const holder=answer.nextElementSibling;
    link.click();assert.deepEqual(f.hits,['file:late']);
    const canonical=f.row('files','conversation','');f.chat.append(canonical);f.dom.flush();
    assert.equal(canonical.nextElementSibling,holder);
    assert.deepEqual(ids(f.owned(canonical)),['late']);
    assert.equal(f.holders().length,1);
});

test('proven orphan metadata remains separate without borrowing the latest answer', () => {
    const f=fixture({activeConversation:'conversation'}), answer=f.row('answer'), card=f.card('orphan','unassigned');
    card.dataset.fileOrphan='true';card.dataset.fileAction='retry';
    f.chat.append(answer);f.cards.append(card);f.start();f.dom.flush();
    assert(!answer.classList.contains('agent-message-has-files'));
    const holder=f.holders()[0];
    assert.notEqual(holder.dataset.fileOwner,'conversation:answer');assert(holder.classList.contains('agent-unassociated-files'));
    assert(holder.textContent.includes('未关联消息的文件'));
    assert.deepEqual(ids(holder.querySelectorAll('.model-file-card')),['orphan']);
    f.dom.flush();assert.equal(f.holders().length,1);
});

console.log(`Artifact cards: ${passed} passed, ${failed} failed`);
if (failed) process.exitCode=1;
