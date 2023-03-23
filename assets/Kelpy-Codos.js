// ==UserScript==
// @name         Kelpy Codos
// @namespace    https://github.com/Keldos-Li/Kelpy-Codos
// @version      1.0.5
// @author       Keldos; https://keldos.me/
// @description  Add copy button to PRE tags before CODE tag, for Chuanhu ChatGPT especially. 
//               Based on Chuanhu ChatGPT version: ac04408 (2023-3-22)
// @license      GPL-3.0
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    function addCopyButton(pre) {
        var code = pre.querySelector('code');
        if (!code) {
            return; // 如果没有找到 <code> 元素，则不添加按钮
        }
        var firstChild = code.firstChild;
        if (!firstChild) {
            return; // 如果 <code> 元素没有子节点，则不添加按钮
        }
        var button = document.createElement('button');
        button.textContent = '\uD83D\uDCCE'; // 使用 📎 符号作为“复制”按钮的文本
        button.style.position = 'relative';
        button.style.float = 'right';
        button.style.fontSize = '1em'; // 可选：调整按钮大小
        button.style.background = 'none'; // 可选：去掉背景颜色
        button.style.border = 'none'; // 可选：去掉边框
        button.style.cursor = 'pointer'; // 可选：显示指针样式
        button.addEventListener('click', function () {
            var range = document.createRange();
            range.selectNodeContents(code);
            range.setStartBefore(firstChild); // 将范围设置为第一个子节点之前
            var selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);

            try {
                var success = document.execCommand('copy');
                if (success) {
                    button.textContent = '\u2714';
                    setTimeout(function () {
                        button.textContent = '\uD83D\uDCCE'; // 恢复按钮为“复制”
                    }, 2000);
                } else {
                    button.textContent = '\u2716';
                }
            } catch (e) {
                console.error(e);
                button.textContent = '\u2716';
            }

            selection.removeAllRanges();
        });
        code.insertBefore(button, firstChild); // 将按钮插入到第一个子元素之前
    }

    function handleNewElements(mutationsList, observer) {
        for (var mutation of mutationsList) {
            if (mutation.type === 'childList') {
                for (var node of mutation.addedNodes) {
                    if (node.nodeName === 'PRE') {
                        addCopyButton(node);
                    }
                }
            }
        }
    }

    var observer = new MutationObserver(handleNewElements);
    observer.observe(document.documentElement, { childList: true, subtree: true });

    document.querySelectorAll('pre').forEach(addCopyButton);
})();
