// Exercise the shipped composer and Gradio's actual Textbox Enter handler.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const {execFileSync} = require('child_process');
const repo = path.resolve(__dirname, '../..');
const nativeSource = process.argv[2] || execFileSync(path.join(repo, '.venv/bin/python'), ['-c',
    'from pathlib import Path; import gradio; print(Path(gradio.__file__).parent / "_frontend_code/textbox/shared/Textbox.svelte")'
], {encoding: 'utf8'}).trim();
const nativeMatch = fs.readFileSync(nativeSource, 'utf8').match(/async function handle_keypress\(e: KeyboardEvent\): Promise<void> \{[\s\S]*?\n\t\}/);
assert(nativeMatch, 'The installed Gradio Textbox must expose its real Enter handler');
const nativeKeypress = nativeMatch[0].replace('(e: KeyboardEvent): Promise<void>', '(e)');

// A small event/DOM harness keeps these tests offline and dependency-free. It
// implements capture/bubble ordering, live selectors, and mutation delivery;
// submission decisions come exclusively from the real production functions.
const observers = new Set();
function changed(target, type, attributeName) {
    for (const observer of observers) {
        if (!observer.target || !observer.target.contains(target)) continue;
        if (type === 'attributes' && !observer.options.attributeFilter.includes(attributeName)) continue;
        observer.records.push({target, type, attributeName});
        if (observer.queued) continue;
        observer.queued = true;
        queueMicrotask(() => {
            observer.queued = false;
            if (observer.records.length) observer.callback(observer.records.splice(0));
        });
    }
}
class Element {
    constructor(tag, attributes = {}) {
        this.tag = tag; this.attributes = {...attributes}; this.children = []; this.parentNode = null;
        this.listeners = new Map(); this.value = ''; this._disabled = false; this.hidden = false;
        this._text = ''; this.classes = new Set((attributes.class || '').split(' ').filter(Boolean));
        this.classList = {contains: name => this.classes.has(name),
            add: name => {this.classes.add(name); changed(this, 'attributes', 'class');},
            remove: name => {this.classes.delete(name); changed(this, 'attributes', 'class');}};
    }
    get disabled() {return this._disabled;}
    set disabled(value) {
        if (this._disabled !== value) {this._disabled = value; changed(this, 'attributes', 'disabled');}
    }
    get textContent() {return this._text + this.children.map(child => child.textContent).join('');}
    set textContent(value) {this._text = value; changed(this, 'characterData');}
    contains(other) {return other === this || this.children.some(child => child.contains(other));}
    appendChild(child) {child.parentNode = this; this.children.push(child); changed(this, 'childList'); return child;}
    removeChild(child) {this.children.splice(this.children.indexOf(child), 1); child.parentNode = null; changed(this, 'childList');}
    matches(selector) {
        if (selector.includes(',')) return selector.split(',').some(part => this.matches(part.trim()));
        const parts = selector.split(/\s+/);
        const final = parts.pop();
        const tag = final.match(/^[a-z]+/i)?.[0];
        const id = final.match(/#([\w-]+)/)?.[1];
        const classes = [...final.matchAll(/\.([\w-]+)/g)].map(match => match[1]);
        const attrs = [...final.matchAll(/\[([^=\]]+)(?:="?([^"\]]+)"?)?\]/g)];
        if ((tag && tag !== this.tag) || (id && id !== this.attributes.id) || classes.some(name => !this.classes.has(name)) ||
            attrs.some(([, key, value]) => !(key in this.attributes) || (value !== undefined && this.attributes[key] !== value))) return false;
        if (!parts.length) return true;
        for (let ancestor = this.parentNode; ancestor; ancestor = ancestor.parentNode)
            if (ancestor.matches(parts.join(' '))) return true;
        return false;
    }
    querySelectorAll(selector) {
        return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
    addEventListener(type, callback, capture = false) {
        const callbacks = this.listeners.get(type) || [];
        if (!callbacks.some(item => item.callback === callback && item.capture === capture)) callbacks.push({callback, capture});
        this.listeners.set(type, callbacks);
    }
    removeEventListener(type, callback, capture = false) {
        this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item.callback !== callback || item.capture !== capture));
    }
    dispatchEvent(event) {
        event.target = this;
        const route = [];
        for (let node = this; node; node = node.parentNode) route.push(node);
        event.composedPath = () => route;
        const invoke = (node, capture) => {
            for (const listener of node.listeners.get(event.type) || []) {
                if (event.stopped) return;
                if (listener.capture === capture) listener.callback(event);
            }
        };
        for (const node of [...route].reverse()) invoke(node, true);
        for (const node of route) invoke(node, false);
        return !event.defaultPrevented;
    }
    click() {if (!this.disabled) this.dispatchEvent(new TestEvent('click'));}
}
class TestEvent {
    constructor(type, options = {}) {Object.assign(this, options); this.type = type; this.defaultPrevented = false; this.stopped = false;}
    preventDefault() {this.defaultPrevented = true;}
    stopImmediatePropagation() {this.stopped = true;}
}
class MutationObserver {
    constructor(callback) {this.callback = callback; this.records = []; this.queued = false; observers.add(this);}
    observe(target, options) {this.target = target; this.options = options;}
    disconnect() {this.target = null; this.records = [];}
}
const document = new Element('document');
document.getElementsByTagName = () => [];
document.getElementById = id => document.querySelector('#' + id);
document.documentElement = document.appendChild(new Element('html'));
const body = document.documentElement.appendChild(new Element('body'));
const textBox = body.appendChild(new Element('div', {id: 'user-input-tb'}));
let textarea = textBox.appendChild(new Element('textarea'));
let button = body.appendChild(new Element('button', {id: 'submit-btn'}));
const preview = body.appendChild(new Element('div', {id: 'agent-pending-files'}));
const label = preview.appendChild(new Element('span', {'data-testid': 'block-label'}));
const picker = body.appendChild(new Element('div', {id: 'agent-upload-files'}));
let conversation = 'chat-a', busy = false;
const submitted = [];
const window = {innerWidth: 1000, addEventListener() {}, matchMedia: () => ({addEventListener() {}}),
    chuanhuInputConversation: () => conversation, chuanhuInputBusy: () => busy};
window.self = window; window.top = window;
const context = {window, document, MutationObserver, Event: TestEvent, InputEvent: TestEvent, console: {log() {}},
    tick: async () => {}, lines: 1, max_lines: 5, dispatch: type => submitted.push(type)};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(repo, 'web_assets/javascript/ChuanhuChat.js'), 'utf8'), context);
vm.runInContext(nativeKeypress, context);
function mountNative() {
    textarea.addEventListener('keypress', context.handle_keypress);
    button.addEventListener('click', () => submitted.push('click'));
}
function pending(ids, target = conversation, rowCount = ids.length) {
    label.textContent = JSON.stringify({target, ids});
    for (const row of preview.querySelectorAll('tr.file')) preview.removeChild(row);
    for (let index = 0; index < rowCount; index++) preview.appendChild(new Element('tr', {class: 'file'}));
}
async function flush() {for (let i = 0; i < 4; i++) await Promise.resolve();}
function input(value) {textarea.value = value; textarea.dispatchEvent(new TestEvent('input'));}
async function enter(options = {}) {
    const keydown = new TestEvent('keydown', {key: 'Enter', code: 'Enter', ...options});
    textarea.dispatchEvent(keydown);
    let keypress;
    if (!keydown.defaultPrevented) {
        keypress = new TestEvent('keypress', {key: 'Enter', code: 'Enter', ...options});
        textarea.dispatchEvent(keypress);
    }
    await flush();
    return {keydown, keypress};
}
async function assertBlocked(reason) {
    window.chuanhuRefreshSendButton();
    assert(button.disabled, reason + ': Send disabled');
    const count = submitted.length;
    button.click();
    const event = await enter();
    assert(event.keydown.defaultPrevented, reason + ': Enter blocked');
    // The native keypress path is guarded even for a separately delivered event.
    textarea.dispatchEvent(new TestEvent('keypress', {key: 'Enter'}));
    await flush();
    assert.equal(submitted.length, count, reason + ': no submission');
}
(async () => {
    mountNative(); pending([]);
    context.user_input_tb = textBox;
    context.selectHistory();
    await assertBlocked('Initial empty input');

    // The same display filename is intentionally irrelevant: readiness uses the
    // two independent IDs issued by the server for a/same.txt and b/same.txt.
    pending(['first-same-file', 'second-same-file']); await flush();
    assert.equal(button.disabled, false, 'Ready attachments enable Send with an empty textarea');
    const beforeClick = submitted.length; button.click();
    assert.equal(submitted.length, beforeClick + 1);
    const beforeEnter = submitted.length; const validEnter = await enter();
    assert.equal(validEnter.keydown.defaultPrevented, false);
    assert.equal(submitted.length, beforeEnter + 1, 'Real Gradio Enter emits exactly one submit');
    assert.equal(submitted.at(-1), 'submit');
    assert.deepEqual(Array.from(context.key_down_history), [], 'Empty attachment turns do not enter text history');

    input('   '); assert.equal(button.disabled, false);
    pending(['second-same-file']); await flush(); assert.equal(button.disabled, false);
    pending([]); await flush(); await assertBlocked('Removing every attachment');
    input('ordinary text'); assert.equal(button.disabled, false);
    await enter(); assert.deepEqual(Array.from(context.key_down_history), ['ordinary text']);
    input('');

    for (const [ids, target, rows] of [[['old'], 'chat-old', 1], [['a', 'b'], conversation, 1],
        [['duplicate', 'duplicate'], conversation, 2], [[''], conversation, 1]]) {
        pending(ids, target, rows); await flush(); await assertBlocked('Stale or incomplete pending metadata');
    }
    label.textContent = 'not JSON'; await flush(); await assertBlocked('Malformed pending metadata');
    pending(['ready']); await flush();

    for (const flag of ['chuanhuAgentUploading', 'chuanhuAgentUploadStaging']) {
        window[flag] = true;
        await assertBlocked(flag);
        input('text cannot bypass upload'); await assertBlocked(flag + ' with text');
        window[flag] = false; window.chuanhuRefreshSendButton();
        assert.equal(button.disabled, false, 'Explicit upload completion refresh enables Send without a DOM change');
        input('');
    }
    for (const name of ['uploading', 'file-preview-holder']) {
        const progress = picker.appendChild(new Element('div', {class: name})); await flush();
        await assertBlocked('Native picker ' + name);
        picker.removeChild(progress); await flush(); assert.equal(button.disabled, false);
    }
    busy = true; await assertBlocked('Active/pending turn');
    busy = false; window.chuanhuRefreshSendButton(); assert.equal(button.disabled, false);
    button.classList.add('hidden'); await flush(); await assertBlocked('Remote turn still running after local busy clears');
    button.classList.remove('hidden'); await flush(); assert.equal(button.disabled, false);
    textarea.disabled = true; await flush(); await assertBlocked('Native textbox disabled');
    textarea.disabled = false; await flush(); assert.equal(button.disabled, false);

    conversation = 'chat-new'; window.chuanhuRefreshSendButton(); await assertBlocked('New chat rejects the previous preview');
    conversation = ''; window.chuanhuRefreshSendButton(); await assertBlocked('Ordinary model cannot send stale Agent attachments');
    input('ordinary model text'); assert.equal(button.disabled, false);
    await enter(); assert.equal(submitted.at(-1), 'submit');
    const beforeShift = submitted.length; const shifted = await enter({shiftKey: true});
    assert.equal(shifted.keydown.defaultPrevented, false);
    assert.equal(submitted.length, beforeShift, 'Shift+Enter preserves native multiline editing');

    // Gradio may replace native elements. Delegation and live selectors must
    // survive it, and repeated chat updates must not accumulate handlers.
    textBox.removeChild(textarea); body.removeChild(button);
    textarea = textBox.appendChild(new Element('textarea'));
    button = body.appendChild(new Element('button', {id: 'submit-btn'})); mountNative();
    conversation = 'chat-replaced'; pending(['replacement-file']); await flush();
    for (let i = 0; i < 10; i++) context.disableSendBtn();
    assert.equal(document.listeners.get('input').length, 1);
    for (const type of ['click', 'keydown', 'keypress']) assert.equal(document.listeners.get(type).length, 1);
    assert.equal(button.disabled, false);
    const beforeRemount = submitted.length; await enter(); assert.equal(submitted.length, beforeRemount + 1);
    pending([]); await flush(); await assertBlocked('Cleared remounted composer');
    console.log('File-only Send and real Gradio Enter, clear/remove, upload/staging/busy guards, model isolation and remount passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
