
var historyLoaded = false;
var loadhistorytime = 0; // for debugging


function saveHistoryHtml() {
    var historyHtml = document.querySelector('#chuanhu-chatbot>.wrapper>.wrap');
    if (!historyHtml) return;   // no history, do nothing
    localStorage.setItem('chatHistory', historyHtml.innerHTML);
    // console.log("History Saved")
    historyLoaded = false;
}

function loadHistoryHtml() {
    var historyHtml = localStorage.getItem('chatHistory');
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = historyHtml;
    if (!historyHtml || tempDiv.innerText.trim() === "") {
        historyLoaded = true;
        return; // no history, do nothing
    }
    userLogged = localStorage.getItem('userLogged');
    if (userLogged){
        historyLoaded = true;
        return; // logged in, do nothing
    }
    if (!historyLoaded) {
        var fakeHistory = document.createElement('div');
        fakeHistory.classList.add('history-message');
        fakeHistory.innerHTML = tempDiv.innerHTML;
        const forViewStyle = document.createElement('style');
        forViewStyle.innerHTML = '.wrapper>.wrap>.history-message>:last-child::after { content: "' + i18n(forView_i18n) + '"!important; }';
        document.head.appendChild(forViewStyle);
        chatbotWrap.insertBefore(fakeHistory, chatbotWrap.firstChild);
        // var fakeHistory = document.createElement('div');
        // fakeHistory.classList.add('history-message');
        // fakeHistory.innerHTML = historyHtml;
        // chatbotWrap.insertBefore(fakeHistory, chatbotWrap.firstChild);
        historyLoaded = true;
        console.log("History Loaded");
        loadhistorytime += 1; // for debugging
    } else {
        historyLoaded = false;
    }
}

function clearHistoryHtml() {
    localStorage.removeItem("chatHistory");
    historyMessages = chatbotWrap.querySelector('.history-message');
    if (historyMessages) {
        chatbotWrap.removeChild(historyMessages);
        console.log("History Cleared");
    }
}
