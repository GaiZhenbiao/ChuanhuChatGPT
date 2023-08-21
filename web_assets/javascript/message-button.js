
// 为 bot 消息添加复制与切换显示按钮

function addChuanhuButton(botElement) {
    var rawMessage = botElement.querySelector('.raw-message');
    var mdMessage = botElement.querySelector('.md-message');
    
    if (!rawMessage) { // 如果没有 raw message，说明是早期历史记录，去除按钮
        var buttons = botElement.querySelectorAll('button.chuanhu-btn');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].parentNode.removeChild(buttons[i]);
        }
        return;
    }
    botElement.querySelectorAll('button.copy-bot-btn, button.toggle-md-btn').forEach(btn => btn.remove()); // 就算原先有了，也必须重新添加，而不是跳过

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
        if (renderMarkdown) {
            renderMarkdownText(botElement);
            toggleButton.innerHTML=rawIcon;
        } else {
            removeMarkdownText(botElement);
            toggleButton.innerHTML=mdIcon;
        }
        chatbotContentChanged(1); // to set md or raw in read-only history html
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
            rawDiv.innerHTML = rawDiv.querySelector('pre')?.innerHTML || rawDiv.innerHTML;
            rawDiv.classList.remove('hideM');
        }
        var mdDiv = message.querySelector('.md-message');
        if (mdDiv) mdDiv.classList.add('hideM');
    }
}


