// Selector/declaration contract only; real browser animation/computed styles
// are verified separately by the independent visual QA.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync('tests/javascript/message-actions.test.cjs', 'utf8');
const context = vm.createContext({assert});
vm.runInContext(source.slice(source.indexOf('const escape ='), source.indexOf('\nfunction fixture(')) + '\nglobalThis.dom = createDOM();', context);
const document = context.dom.document;
const css = fs.readFileSync('web_assets/stylesheet/chatbot.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
const hiddenRule = rules.find(([, , body]) => /animation\s*:\s*none\s*!important/.test(body) && /display\s*:\s*none\s*!important/.test(body));
assert(hiddenRule, 'Hidden generation must disable display and opacity animation');
const selector = hiddenRule[1].trim();
const app = document.createElement('div'); app.className = 'gradio-container'; document.body.append(app);
const cases = [
    ['wrap center hidden hide generating svelte-137ftxg', true],
    ['wrap default hidden hide generating svelte-137ftxg', true],
    ['wrap center full generating svelte-137ftxg', false],
    ['wrap center minimal generating svelte-137ftxg', false],
    ['wrap center full hide generating svelte-137ftxg', false],
    ['wrap svelte-1scun43', false],
    ['wrap hidden', false],
];
for (const [classes, expected] of cases) {
    const node = document.createElement('div'); node.className = classes; app.append(node);
    assert.equal(document.querySelectorAll(selector).includes(node), expected, classes);
    node.remove();
}
const outside = document.createElement('div'); outside.className = 'wrap hidden generating'; document.body.append(outside);
assert(!document.querySelectorAll(selector).includes(outside), 'Rule stays within this Gradio app');
console.log('Progress overlay selector contract: 2 hidden-generation positives and 6 exclusions passed; no browser geometry claim');
