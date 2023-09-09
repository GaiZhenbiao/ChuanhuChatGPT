
var currentChatName = null;

function setChatList() {
    var selectedChat = null;
    var chatList = gradioApp().querySelector('fieldset#history-select-dropdown');
    selectedChat = chatList.querySelector(".wrap label.selected")
    if (!selectedChat) {
        currentChatName = null;
        return;
    }

    // if (userLogged) {
    //     currentChatName = username + "/" + selectedChat.querySelector('span').innerText;
    // } else {
        currentChatName = selectedChat.querySelector('span').innerText;
    // }

    if (selectedChat.classList.contains('added-chat-btns')) {
        return;
    }

    chatList.querySelector('.chat-selected-btns')?.remove(); // remove old buttons
    chatList.querySelectorAll('.added-chat-btns').forEach(chat => chat.classList.remove('added-chat-btns'));

    var ChatSelectedBtns = document.createElement('div');
    ChatSelectedBtns.classList.add('chat-selected-btns');
    selectedChat.classList.add('added-chat-btns');
    ChatSelectedBtns.innerHTML = selectedChatBtns;

    var renameBtn = ChatSelectedBtns.querySelector('#history-rename-btn');
    renameBtn.addEventListener('click', function () {
        gradioApp().querySelector('#gr-history-save-btn').click();
    });

    var deleteBtn = ChatSelectedBtns.querySelector('#history-delete-btn');
    deleteBtn.addEventListener('click', function () {
        gradioApp().querySelector('#gr-history-delete-btn').click();
    });
    selectedChat.appendChild(ChatSelectedBtns);

    return;
}

function saveChatHistory(a, b, c, d) {
    var fileName = b;
    fileName = prompt(renameChat_i18n, b);
    if (fileName && fileName.trim() !== "") {
        return [a, fileName, c, d];
    } else {
        return [a, "", c, d];
    }
}

const selectedChatBtns = `
<button id="history-rename-btn"><svg class="icon-need-hover" stroke="currentColor" fill="none" stroke-width="2" height="18px" width="18px" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg></button>
<button id="history-delete-btn"><svg class="icon-need-hover" stroke="currentColor" fill="none" stroke-width="2" height="18px" width="18px" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button>
`
