function openSettingBox() {
    chuanhuPopup.classList.add('showBox');
    settingBox.classList.remove('hideBox');
    showMask();

}

function openTrainingBox() {
    chuanhuPopup.classList.add('showBox');
    trainingBox.classList.remove('hideBox');
    showMask();
}

function showMask() {
    const mask = document.createElement('div');
    mask.classList.add('chuanhu-mask');
    document.body.appendChild(mask);
    mask.addEventListener('click', () => {
        closeBox();
    });
}

function closeBox() {
    chuanhuPopup.classList.remove('showBox');
    trainingBox.classList.add('hideBox');
    settingBox.classList.add('hideBox');
    document.querySelector('.chuanhu-mask')?.remove();
}

function menuClick() {
    var menu = gradioApp().querySelector('#menu-area');
    // var menuBtn = gradioApp().querySelector('.menu-btn');
    if (menu.classList.contains('hideSide')) {
        menu.classList.remove('hideSide');
        // menuBtn.classList.add('active');
    } else {
        menu.classList.add('hideSide');
        // menuBtn.classList.remove('active');
    }
}

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

// function bgSelectHistory(a,b,c){
//     const historySelectorInput = gradioApp().querySelector('#history-select-dropdown input');
//     let file = historySelectorInput.value;
//     return [a,file,c]
// }