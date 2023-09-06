
// 为 bot 消息添加复制与切换显示按钮 以及最新消息加上重新生成，删除最新消息，嗯。

function addChuanhuButton(botRow) {

    botElement = botRow.querySelector('.message.bot');
    isLatestMessage = botElement.classList.contains('latest');

    var rawMessage = botElement.querySelector('.raw-message');
    var mdMessage = botElement.querySelector('.md-message');
    
    if (!rawMessage) { // 如果没有 raw message，说明是早期历史记录，去除按钮
        // var buttons = botElement.querySelectorAll('button.chuanhu-btn');
        // for (var i = 0; i < buttons.length; i++) {
        //     buttons[i].parentNode.removeChild(buttons[i]);
        // }
        botElement.querySelector('.message-btn-row')?.remove();
        botElement.querySelector('.message-btn-column')?.remove();
        return;
    }
    // botElement.querySelectorAll('button.copy-bot-btn, button.toggle-md-btn').forEach(btn => btn.remove()); // 就算原先有了，也必须重新添加，而不是跳过
    if (!isLatestMessage) botElement.querySelector('.message-btn-row')?.remove();
    botElement.querySelector('.message-btn-column')?.remove();

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
    // botElement.appendChild(copyButton);

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
    // botElement.insertBefore(toggleButton, copyButton);

    var messageBtnColumn = document.createElement('div');
    messageBtnColumn.classList.add('message-btn-column');
    messageBtnColumn.appendChild(toggleButton);
    messageBtnColumn.appendChild(copyButton);
    botElement.appendChild(messageBtnColumn);

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

function setLatestMessage() {
    var latestMessage = gradioApp().querySelector('#chuanhu-chatbot > .wrapper > .wrap > .message-wrap .message.bot.latest');
    if (latestMessage) addLatestMessageButtons(latestMessage);
}

function addLatestMessageButtons(botElement) {
    botElement.querySelector('.message-btn-row')?.remove();

    var messageBtnRow = document.createElement('div');
    messageBtnRow.classList.add('message-btn-row');
    var messageBtnRowLeading = document.createElement('div');
    messageBtnRowLeading.classList.add('message-btn-row-leading');
    var messageBtnRowTrailing = document.createElement('div');
    messageBtnRowTrailing.classList.add('message-btn-row-trailing');

    messageBtnRow.appendChild(messageBtnRowLeading);
    messageBtnRow.appendChild(messageBtnRowTrailing);

    botElement.appendChild(messageBtnRow);

    var regenerateButton = document.createElement('button');
    regenerateButton.classList.add('chuanhu-btn');
    regenerateButton.classList.add('regenerate-btn');
    regenerateButton.setAttribute('aria-label', 'Regenerate');
    regenerateButton.innerHTML = regenIcon + `<span>${i18n(regenerate_i18n)}</span>`;

    var gradioRetryBtn = gradioApp().querySelector('#gr-retry-btn');
    regenerateButton.addEventListener('click', () => {
        gradioRetryBtn.click();
    });

    var deleteButton = document.createElement('button');
    deleteButton.classList.add('chuanhu-btn');
    deleteButton.classList.add('delete-latest-btn');
    deleteButton.setAttribute('aria-label', 'Delete');
    deleteButton.innerHTML = deleteIcon + `<span>${i18n(delete_i18n)}</span>`;

    var gradioDelLastBtn = gradioApp().querySelector('#gr-dellast-btn');
    deleteButton.addEventListener('click', () => {
        gradioDelLastBtn.click();
        chatbotContentChanged(2);
    });

    messageBtnRowLeading.appendChild(regenerateButton);
    messageBtnRowLeading.appendChild(deleteButton);
}


// button svg code
const copyIcon   = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></span>';
const copiedIcon = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"></polyline></svg></span>';
const mdIcon     = '<span><svg stroke="currentColor" fill="none" stroke-width="1" viewBox="0 0 14 18" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g transform-origin="center" transform="scale(0.85)"><path d="M1.5,0 L12.5,0 C13.3284271,-1.52179594e-16 14,0.671572875 14,1.5 L14,16.5 C14,17.3284271 13.3284271,18 12.5,18 L1.5,18 C0.671572875,18 1.01453063e-16,17.3284271 0,16.5 L0,1.5 C-1.01453063e-16,0.671572875 0.671572875,1.52179594e-16 1.5,0 Z" stroke-width="1.8"></path><line x1="3.5" y1="3.5" x2="10.5" y2="3.5"></line><line x1="3.5" y1="6.5" x2="8" y2="6.5"></line></g><path d="M4,9 L10,9 C10.5522847,9 11,9.44771525 11,10 L11,13.5 C11,14.0522847 10.5522847,14.5 10,14.5 L4,14.5 C3.44771525,14.5 3,14.0522847 3,13.5 L3,10 C3,9.44771525 3.44771525,9 4,9 Z" stroke="none" fill="currentColor"></path></svg></span>';
const rawIcon    = '<span><svg stroke="currentColor" fill="none" stroke-width="1.8" viewBox="0 0 18 14" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g transform-origin="center" transform="scale(0.85)"><polyline points="4 3 0 7 4 11"></polyline><polyline points="14 3 18 7 14 11"></polyline><line x1="12" y1="0" x2="6" y2="14"></line></g></svg></span>';

const regenIcon  = '<span><svg viewBox="0 0 15.6737 14.3099" height="11px" width="10px" xmlns="http://www.w3.org/2000/svg"><g fill="currentColor"><path d="M8.52344 14.3043C12.4453 14.3043 15.6737 11.0704 15.6737 7.15396C15.6737 3.23385 12.4453 0 8.52344 0C4.61357 0 1.39193 3.20969 1.37314 7.11614L2.77012 7.11614C2.78891 3.94173 5.34391 1.40431 8.52344 1.40431C11.7096 1.40431 14.2785 3.96418 14.2785 7.15396C14.2785 10.3401 11.7096 12.9163 8.52344 12.9073C6.6559 12.9036 5.0325 12.0192 3.98219 10.6317C3.70247 10.3165 3.29141 10.2174 2.96431 10.4686C2.65796 10.6988 2.60863 11.1321 2.91325 11.5028C4.17573 13.1677 6.28972 14.3043 8.52344 14.3043ZM0.520576 5.73631C-0.0035439 5.73631-0.140743 6.14811 0.149274 6.53993L1.86425 8.89772C2.08543 9.20509 2.4372 9.20143 2.65301 8.89772L4.36628 6.53626C4.64726 6.14981 4.51544 5.73631 3.99839 5.73631Z"/></g></svg></span>';
const deleteIcon = '<span><svg viewBox="0 0 17.0644 12.9388" height="11px" width="11px" xmlns="http://www.w3.org/2000/svg"><g fill="currentColor"><path d="M4.85464 12.9388L12.2098 12.9388C13.6299 12.9388 14.26 12.2074 14.4792 10.7927L15.6069 3.38561L14.2702 3.42907L13.1479 10.686C13.049 11.3506 12.7252 11.6268 12.12 11.6268L4.94444 11.6268C4.32818 11.6268 4.01711 11.3506 3.91652 10.686L2.79421 3.42907L1.45752 3.38561L2.5852 10.7927C2.80443 12.2147 3.43453 12.9388 4.85464 12.9388ZM1.5018 4.10325L15.5643 4.10325C16.5061 4.10325 17.0644 3.49076 17.0644 2.55799L17.0644 1.55796C17.0644 0.623227 16.5061 0.0144053 15.5643 0.0144053L1.5018 0.0144053C0.588798 0.0144053 0 0.623227 0 1.55796L0 2.55799C0 3.49076 0.561696 4.10325 1.5018 4.10325ZM1.72372 2.88176C1.41559 2.88176 1.26666 2.7255 1.26666 2.412L1.26666 1.70028C1.26666 1.39215 1.41559 1.23589 1.72372 1.23589L15.3444 1.23589C15.6542 1.23589 15.7978 1.39215 15.7978 1.70028L15.7978 2.412C15.7978 2.7255 15.6542 2.88176 15.3444 2.88176Z"/><path d="M6.62087 10.2995C6.77686 10.2995 6.90282 10.2353 7.01438 10.1274L8.53038 8.60625L10.0517 10.1274C10.1633 10.2316 10.2876 10.2995 10.4526 10.2995C10.7594 10.2995 11.0131 10.0368 11.0131 9.72824C11.0131 9.56151 10.9542 9.44092 10.8427 9.32936L9.33033 7.81679L10.8463 6.29151C10.965 6.17458 11.0184 6.0557 11.0184 5.90166C11.0184 5.58407 10.7685 5.33044 10.4526 5.33044C10.302 5.33044 10.1814 5.38928 10.0608 5.5062L8.53038 7.03269L7.01072 5.50987C6.89379 5.39831 6.77686 5.33947 6.62087 5.33947C6.31036 5.33947 6.05307 5.59311 6.05307 5.90166C6.05307 6.05936 6.11019 6.18899 6.22346 6.29688L7.73579 7.81679L6.22346 9.33303C6.1119 9.44092 6.05307 9.56688 6.05307 9.72824C6.05307 10.0405 6.3067 10.2995 6.62087 10.2995Z"/></g></svg></span>';
// const deleteIcon = '<span><svg stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" height="11px" width="11px" viewBox="0 0 216 163" version="1.1" xmlns="http://www.w3.org/2000/svg"><rect x="0.5" y="0.5" width="215" height="39" rx="9"/><path d="M197.485,39.535 L181.664,145.870 C180.953,150.648 178.547,154.805 175.110,157.768 C171.674,160.731 167.207,162.500 162.376,162.500 L53.558,162.500 C48.737,162.500 44.278,160.738 40.843,157.785 C37.409,154.831 34.999,150.686 34.278,145.919 L18.173,39.535 L197.485,39.535 Z" /><line x1="79.5" y1="71.5" x2="135.5" y2="127.5"/><line x1="79.5" y1="127.5" x2="135.5" y2="71.5"/></svg></span>'
