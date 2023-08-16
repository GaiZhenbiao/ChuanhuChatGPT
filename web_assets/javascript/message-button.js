
// 为 bot 消息添加复制与切换显示按钮

function addChuanhuButton(botElement) {
    var rawMessage = botElement.querySelector('.raw-message');
    var mdMessage = botElement.querySelector('.md-message');
    // var gradioCopyMsgBtn = botElement.querySelector('div.icon-button>button[title="copy"]'); // 获取 gradio 的 copy button，它可以读取真正的原始 message
    if (!rawMessage) {
        var buttons = botElement.querySelectorAll('button.chuanhu-btn');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].parentNode.removeChild(buttons[i]);
        }
        return;
    }
    var oldCopyButton = null;
    var oldToggleButton = null;
    oldCopyButton = botElement.querySelector('button.copy-bot-btn');
    oldToggleButton = botElement.querySelector('button.toggle-md-btn');
    if (oldCopyButton) oldCopyButton.remove();
    if (oldToggleButton) oldToggleButton.remove();

    // Copy bot button
    var copyButton = document.createElement('button');
    copyButton.classList.add('chuanhu-btn');
    copyButton.classList.add('copy-bot-btn');
    copyButton.setAttribute('aria-label', 'Copy');
    copyButton.innerHTML = copyIcon;

    copyButton.addEventListener('click', async () => {
        const textToCopy = rawMessage.innerText;
        try {
            if ("clipboard" in navigator) {
                await navigator.clipboard.writeText(textToCopy);
                copyButton.innerHTML = copiedIcon;
                setTimeout(() => {
                    copyButton.innerHTML = copyIcon;
                }, 1500);
            } else {
                const textArea = document.createElement("textarea");
                textArea.value = textToCopy;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    copyButton.innerHTML = copiedIcon;
                    setTimeout(() => {
                        copyButton.innerHTML = copyIcon;
                    }, 1500);
                } catch (error) {
                    console.error("Copy failed: ", error);
                }
                document.body.removeChild(textArea);
            }
        } catch (error) {
            console.error("Copy failed: ", error);
        }
    });
    botElement.appendChild(copyButton);

    // Toggle button
    var toggleButton = document.createElement('button');
    toggleButton.classList.add('chuanhu-btn');
    toggleButton.classList.add('toggle-md-btn');
    toggleButton.setAttribute('aria-label', 'Toggle');
    var renderMarkdown = mdMessage.classList.contains('hideM');
    toggleButton.innerHTML = renderMarkdown ? mdIcon : rawIcon;
    toggleButton.addEventListener('click', () => {
        renderMarkdown = mdMessage.classList.contains('hideM');
        if (renderMarkdown){
            renderMarkdownText(botElement);
            toggleButton.innerHTML=rawIcon;
        } else {
            removeMarkdownText(botElement);
            toggleButton.innerHTML=mdIcon;
        }
    });
    botElement.insertBefore(toggleButton, copyButton);

    function renderMarkdownText(message) {
        var mdDiv = message.querySelector('.md-message');
        if (mdDiv) mdDiv.classList.remove('hideM');
        var rawDiv = message.querySelector('.raw-message');
        if (rawDiv) rawDiv.classList.add('hideM');
    }
    function removeMarkdownText(message) {
        var rawDiv = message.querySelector('.raw-message');
        if (rawDiv) {
            rawPre = rawDiv.querySelector('pre');
            if (rawPre) rawDiv.innerHTML = rawPre.innerHTML;
            rawDiv.classList.remove('hideM');
        }
        var mdDiv = message.querySelector('.md-message');
        if (mdDiv) mdDiv.classList.add('hideM');
    }
}


let timeoutId;
let isThrottled = false;
// 监听chatWrap元素的变化，为 bot 消息添加复制按钮。
var mObserver = new MutationObserver(function (mutationsList) {
    for (const mmutation of mutationsList) {
        if (mmutation.type === 'childList') {
            for (var node of mmutation.addedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message')) {
                    saveHistoryHtml();
                    disableSendBtn();
                    document.querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                }
            }
            for (var node of mmutation.removedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message')) {
                    saveHistoryHtml();
                    disableSendBtn();
                    document.querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                }
            }
        } else if (mmutation.type === 'attributes') {
            if (isThrottled) break; // 为了防止重复不断疯狂渲染，加上等待_(:з」∠)_
            isThrottled = true;
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                isThrottled = false;
                document.querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                saveHistoryHtml();
                disableSendBtn();
            }, 1500);
        }
    }
});
