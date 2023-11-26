function suggestAPIKey() {
    switchTab(0);
    openSettingBox();
    let apiKeyForm = settingBox.querySelector('.gradio-tabs > .gradio-tabitem > div:nth-child(1) > div.form:nth-child(1)');
    letThisSparkle(apiKeyForm);
}

function letThisSparkle(element) {
    element.classList.add('chuanhu-sparkle');
    setTimeout(() => {element.classList.remove('chuanhu-sparkle');}, 3000);
}

function switchTab(tabIndex) {
    let tabButtons = gradioApp().querySelectorAll('#chuanhu-setting .tab-nav > button');
    let tab = tabButtons[tabIndex];
    tab.click();
}

function openSettingBox() {
    chuanhuPopup.classList.add('showBox');
    popupWrapper.classList.add('showBox');
    settingBox.classList.remove('hideBox');
    trainingBox.classList.add('hideBox');
    showMask("box");
}

function openTrainingBox() {
    chuanhuPopup.classList.add('showBox');
    popupWrapper.classList.add('showBox');
    trainingBox.classList.remove('hideBox');
    settingBox.classList.add('hideBox');
    showMask("box");
}

function openChatMore() {
    chatbotArea.classList.add('show-chat-more');
    showMask("chat-more");
}

function closeChatMore() {
    chatbotArea.classList.remove('show-chat-more');
    chatbotArea.querySelector('.chuanhu-mask')?.remove();
}


function showMask(obj) {
    const mask = document.createElement('div');
    mask.classList.add('chuanhu-mask');
    if (obj == "box") {
        mask.classList.add('mask-blur');
        document.body.classList.add('popup-open');
        popupWrapper.appendChild(mask);
    } else if (obj == "chat-more") {
        mask.classList.add('transparent-mask');
        chatbotArea.querySelector('#chatbot-input-more-area').parentNode.appendChild(mask);
    } else if (obj == "update-toast") {
        mask.classList.add('chuanhu-top-mask');
        if (document.querySelector('.chuanhu-top-mask')) {
            for (var i = 0; i < document.querySelectorAll('.chuanhu-top-mask').length; i++) {
                document.querySelectorAll('.chuanhu-top-mask')[i].remove();
            }
        }
        document.body.appendChild(mask);
        // mask.classList.add('transparent-mask');
    }
    

    mask.addEventListener('click', () => {
        if (obj == "box") {
            closeBox();
        } else if (obj == "chat-more") {
            closeChatMore();
        } else if (obj == "update-toast") {
            closeUpdateToast();
        }
    });
}

function chatMoreBtnClick() {
    if (chatbotArea.classList.contains('show-chat-more')) {
        closeChatMore();
    } else {
        openChatMore();
    }
}

function closeBtnClick(obj) {
    if (obj == "box") {
        closeBox();
    } else if (obj == "toolbox") {
        closeSide(toolbox);
        wantOpenToolbox = false;
    }
}

function closeBox() {
    chuanhuPopup.classList.remove('showBox');
    popupWrapper.classList.remove('showBox');
    trainingBox.classList.add('hideBox');
    settingBox.classList.add('hideBox');
    document.querySelector('.chuanhu-mask')?.remove();
    document.body.classList.remove('popup-open');
}

function closeSide(sideArea) {
    document.body.classList.remove('popup-open');
    sideArea.classList.remove('showSide');
    if (sideArea == toolbox) {
        chuanhuHeader.classList.remove('under-box');
        chatbotArea.classList.remove('toolbox-open')
        toolboxOpening = false;
    } else if (sideArea == menu) {
        chatbotArea.classList.remove('menu-open')
        menuOpening = false;
    }
    adjustMask();
}

function openSide(sideArea) {
    sideArea.classList.add('showSide');
    if (sideArea == toolbox) {
        chuanhuHeader.classList.add('under-box');
        chatbotArea.classList.add('toolbox-open')
        toolboxOpening = true;
    } else if (sideArea == menu) {
        chatbotArea.classList.add('menu-open')
        menuOpening = true;
    }
    // document.body.classList.add('popup-open');
}

function menuClick() {
    shouldAutoClose = false;
    if (menuOpening) {
        closeSide(menu);
        wantOpenMenu = false;
    } else {
        if (windowWidth < 1024 && toolboxOpening) {
            closeSide(toolbox);
            wantOpenToolbox = false;
        }
        openSide(menu);
        wantOpenMenu = true;
    }
    adjustSide();
}

function toolboxClick() {
    shouldAutoClose = false;
    if (toolboxOpening) {
        closeSide(toolbox);
        wantOpenToolbox = false;
    } else {
        if (windowWidth < 1024 && menuOpening) {
            closeSide(menu);
            wantOpenMenu = false;
        }
        openSide(toolbox);
        wantOpenToolbox = true;
    }
    adjustSide();
}

var menuOpening = false;
var toolboxOpening = false;
var shouldAutoClose = true;
var wantOpenMenu = windowWidth > 768;
var wantOpenToolbox = windowWidth >= 1024;

function adjustSide() {
    if (windowWidth >= 1024) {
        shouldAutoClose = true;
        if (wantOpenMenu) {
            openSide(menu);
            if (wantOpenToolbox) openSide(toolbox);
        } else if (wantOpenToolbox) {
            openSide(toolbox);
        } else {
            closeSide(menu);
            closeSide(toolbox);
        }
    } else if (windowWidth > 768 && windowWidth < 1024 ) {
        shouldAutoClose = true;
        if (wantOpenToolbox) {
            if (wantOpenMenu) {
                closeSide(toolbox);
                openSide(menu);
            } else {
                closeSide(menu);
                openSide(toolbox);
            }
        } else if (wantOpenMenu) {
            if (wantOpenToolbox) {
                closeSide(menu);
                openSide(toolbox);
            } else {
                closeSide(toolbox);
                openSide(menu);
            }
        } else if (!wantOpenMenu && !wantOpenToolbox){
            closeSide(menu);
            closeSide(toolbox);
        }
    } else { // windowWidth <= 768
        if (shouldAutoClose) {
            closeSide(menu);
            // closeSide(toolbox);
        }
    }
    checkChatbotWidth();
    adjustMask();
}

function adjustMask() {
    var sideMask = null;
    if (!gradioApp().querySelector('.chuanhu-side-mask')) {
        sideMask = document.createElement('div');
        sideMask.classList.add('chuanhu-side-mask');
        gradioApp().appendChild(sideMask);
        sideMask.addEventListener('click', () => {
            closeSide(menu);
            closeSide(toolbox);
        });
    }
    sideMask = gradioApp().querySelector('.chuanhu-side-mask');

    if (windowWidth > 768) {
        sideMask.style.backgroundColor = 'rgba(0, 0, 0, 0)';
        setTimeout(() => {sideMask.style.display = 'none'; }, 100);
        return;
    }
    // if (windowWidth <= 768)
    if (menuOpening || toolboxOpening) {
        document.body.classList.add('popup-open');
        sideMask.style.display = 'block';
        setTimeout(() => {sideMask.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';}, 200);
        sideMask.classList.add('mask-blur');
    } else if (!menuOpening && !toolboxOpening) {
        sideMask.style.backgroundColor = 'rgba(0, 0, 0, 0)';
        setTimeout(() => {sideMask.style.display = 'none'; }, 100);
    }
}

function checkChatbotWidth() {
    // let chatbotWidth = chatbotArea.clientWidth;
    // if (chatbotWidth > 488) {
    if (windowWidth > 768) {
        chatbotArea.classList.add('chatbot-full-width');
    } else {
        chatbotArea.classList.remove('chatbot-full-width');
    }

    if (windowWidth > 768) {
        chatbotArea.classList.remove('no-toolbox');
        chatbotArea.classList.remove('no-menu');

        if (!chatbotArea.classList.contains('toolbox-open') && chatbotArea.classList.contains('menu-open')) {
            chatbotArea.classList.add('no-toolbox');
        } else if (!chatbotArea.classList.contains('menu-open') && chatbotArea.classList.contains('toolbox-open')) {
            chatbotArea.classList.add('no-menu');
        } else if (!chatbotArea.classList.contains('menu-open') && !chatbotArea.classList.contains('toolbox-open')) {
            chatbotArea.classList.add('no-toolbox');
            chatbotArea.classList.add('no-menu');
        }
    }

    checkChatMoreMask();
}

function checkChatMoreMask() {
    if (!chatbotArea.classList.contains('chatbot-full-width')) {
        chatbotArea.querySelector('.chuanhu-mask')?.remove();
        chatbotArea.classList.remove('show-chat-more');
    }
}

/*
function setHistroyPanel() {
    const historySelectorInput = gradioApp().querySelector('#history-select-dropdown input');
    const historyPanel = document.createElement('div');
    historyPanel.classList.add('chuanhu-history-panel');
    historySelector.parentNode.insertBefore(historyPanel, historySelector);
    var historyList=null;

    historySelectorInput.addEventListener('click', (e) => {
        e.stopPropagation();
        historyList = gradioApp().querySelector('#history-select-dropdown ul.options');

        if (historyList) {
            // gradioApp().querySelector('.chuanhu-history-panel')?.remove();
            historyPanel.innerHTML = '';
            let historyListClone = historyList.cloneNode(true);
            historyListClone.removeAttribute('style');
            // historyList.classList.add('hidden');
            historyList.classList.add('hideK');
            historyPanel.appendChild(historyListClone);
            addHistoryPanelListener(historyPanel);
            // historySelector.parentNode.insertBefore(historyPanel, historySelector);
        }
    });
}
*/

// function addHistoryPanelListener(historyPanel){
//     historyPanel.querySelectorAll('ul.options > li').forEach((historyItem) => {
//         historyItem.addEventListener('click', (e) => {
//             const historySelectorInput = gradioApp().querySelector('#history-select-dropdown input');
//             const historySelectBtn = gradioApp().querySelector('#history-select-btn');
//             historySelectorInput.value = historyItem.innerText;
//             historySelectBtn.click();
//         });
//     });
// }


// function testTrain() {
    
//     trainBody.classList.toggle('hide-body');
//     trainingBox.classList.remove('hideBox');

//     var chuanhuBody = document.querySelector('#chuanhu-body');
//     chuanhuBody.classList.toggle('hide-body');
// }