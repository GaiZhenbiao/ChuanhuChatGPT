function openSettingBox() {
    chuanhuPopup.classList.add('showBox');
    popupWrapper.classList.add('showBox');
    settingBox.classList.remove('hideBox');
    trainingBox.classList.add('hideBox');
    showMask();

}

function openTrainingBox() {
    chuanhuPopup.classList.add('showBox');
    popupWrapper.classList.add('showBox');
    trainingBox.classList.remove('hideBox');
    settingBox.classList.add('hideBox');
    showMask();
}

function showMask() {
    const mask = document.createElement('div');
    mask.classList.add('chuanhu-mask');
    popupWrapper.appendChild(mask);
    document.body.classList.add('popup-open');
    mask.addEventListener('click', () => {
        closeBox();
    });
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
        toolboxOpening = false;
    } else if (sideArea == menu) {
        menuOpening = false;
    }
    adjustMask();
}

function openSide(sideArea) {
    sideArea.classList.add('showSide');
    if (sideArea == toolbox) {
        chuanhuHeader.classList.add('under-box');
        toolboxOpening = true;
    } else if (sideArea == menu) {
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

// function bgSelectHistory(a,b,c){
//     const historySelectorInput = gradioApp().querySelector('#history-select-dropdown input');
//     let file = historySelectorInput.value;
//     return [a,file,c]
// }

// function testTrain() {
    
//     trainBody.classList.toggle('hide-body');
//     trainingBox.classList.remove('hideBox');

//     var chuanhuBody = document.querySelector('#chuanhu-body');
//     chuanhuBody.classList.toggle('hide-body');
// }