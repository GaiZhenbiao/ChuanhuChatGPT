
// ChuanhuChat core javascript

const MAX_HISTORY_LENGTH = 32;

var key_down_history = [];
var currentIndex = -1;

var gradioContainer = null;
var user_input_ta = null;
var user_input_tb = null;
var userInfoDiv = null;
var appTitleDiv = null;
var chatbotArea = null;
var chatbot = null;
var chatbotIndicator = null;
var uploaderIndicator = null;
var chatListIndicator = null;
var chatbotWrap = null;
var apSwitch = null;
var messageBotDivs = null;
var loginUserForm = null;
var logginUser = null;
var updateToast = null;
var sendBtn = null;
var cancelBtn = null;
// var sliders = null;
var updateChuanhuBtn = null;
var rebootChuanhuBtn = null;
var statusDisplay = null;

var historySelector = null;
var chuanhuPopup = null;
var settingBox = null;
var trainingBox = null;
var popupWrapper = null;
var chuanhuHeader = null;
var menu = null;
var toolbox = null;
// var trainBody = null;

var isInIframe = (window.self !== window.top);
var currentTime = new Date().getTime();

let windowWidth = window.innerWidth; // 初始窗口宽度

function addInit() {
    // var needInit = {chatbotIndicator, uploaderIndicator};
    // WIP: 因为 gradio 修改了 file uploader, 暂时无法检查 uploaderIndicator
    // 在之后再考虑修复文件上传功能
    var needInit = {chatbotIndicator};

    chatbotIndicator = gradioApp().querySelector('#chuanhu-chatbot > div.wrap');
    uploaderIndicator = gradioApp().querySelector('#upload-index-file > div[data-testid="block-label"]');
    chatListIndicator = gradioApp().querySelector('#history-select-dropdown > div.wrap');

    for (let elem in needInit) {
        if (needInit[elem] == null) {
            // addInited = false;
            return false;
        }
    }

    chatbotObserver.observe(chatbotIndicator, { attributes: true, childList: true, subtree: true });
    chatListObserver.observe(chatListIndicator, { attributes: true });
    setUploader();
    setPasteUploader();
    setDragUploader();
    return true;
}

function initialize() {
    gradioObserver.observe(gradioApp(), { childList: true, subtree: true });

    loginUserForm = gradioApp().querySelector(".gradio-container > .main > .wrap > .panel > .form")
    gradioContainer = gradioApp().querySelector(".gradio-container");
    user_input_tb = gradioApp().getElementById('user-input-tb');
    userInfoDiv = gradioApp().getElementById("user-info");
    appTitleDiv = gradioApp().getElementById("app-title");
    chatbotArea = gradioApp().querySelector('#chatbot-area');
    chatbot = gradioApp().querySelector('#chuanhu-chatbot');
    chatbotWrap = gradioApp().querySelector('#chuanhu-chatbot > .wrapper > .bubble-wrap');
    apSwitch = gradioApp().querySelector('.apSwitch input[type="checkbox"]');
    updateToast = gradioApp().querySelector("#toast-update");
    sendBtn = gradioApp().getElementById("submit-btn");
    cancelBtn = gradioApp().getElementById("cancel-btn");
    // sliders = gradioApp().querySelectorAll('input[type="range"]');
    updateChuanhuBtn = gradioApp().getElementById("update-chuanhu-btn");
    rebootChuanhuBtn = gradioApp().getElementById("reboot-chuanhu-btn");
    statusDisplay = gradioApp().querySelector('#status-display');

    historySelector = gradioApp().querySelector('#history-select-dropdown');
    chuanhuPopup = gradioApp().querySelector('#chuanhu-popup');
    settingBox = gradioApp().querySelector('#chuanhu-setting');
    trainingBox = gradioApp().querySelector('#chuanhu-training');
    popupWrapper = gradioApp().querySelector('#popup-wrapper');
    chuanhuHeader = gradioApp().querySelector('#chuanhu-header');
    menu = gradioApp().querySelector('#menu-area');
    toolbox = gradioApp().querySelector('#toolbox-area');
    // trainBody = gradioApp().querySelector('#train-body');

    // if (loginUserForm) {
    // localStorage.setItem("userLogged", true);
    // userLogged = true;
    // }

    adjustDarkMode();
    adjustSide();
    setChatList();
    setChatListHeader();
    setLoclize();
    selectHistory();
    // setChatbotHeight();
    setPopupBoxPosition();
    // setSlider();
    setCheckboxes();
    setAutocomplete();
    checkModel();

    settingBox.classList.add('hideBox');
    trainingBox.classList.add('hideBox');

    if (!historyLoaded) loadHistoryHtml();
    if (!usernameGotten) getUserInfo();

    setUpdater();

    setChatbotScroll();
    setTimeout(showOrHideUserInfo(), 2000);

    // setHistroyPanel();
    // trainBody.classList.add('hide-body');



    return true;
}

function gradioApp() {
    const elems = document.getElementsByTagName('gradio-app');
    const elem = elems.length == 0 ? document : elems[0];

    if (elem !== document) {
        elem.getElementById = function(id) {
            return document.getElementById(id);
        };
    }
    return elem.shadowRoot ? elem.shadowRoot : elem;
}

function showConfirmationDialog(a, file, c) {
    if (file != "") {
        var result = confirm(i18n(deleteConfirm_i18n_pref) + file + i18n(deleteConfirm_i18n_suff));
        if (result) {
            return [a, file, c];
        }
    }
    return [a, "CANCELED", c];
}

function selectHistory() {
    user_input_ta = user_input_tb.querySelector("textarea");
    if (user_input_ta) {
        disableSendBtn();
        // 在 textarea 上监听 keydown 事件
        user_input_ta.addEventListener("keydown", function (event) {
            var value = user_input_ta.value.trim();
            // 判断按下的是否为方向键
            if (event.code === 'ArrowUp' || event.code === 'ArrowDown') {
                // 如果按下的是方向键，且输入框中有内容，且历史记录中没有该内容，则不执行操作
                if (value && key_down_history.indexOf(value) === -1)
                    return;
                // 对于需要响应的动作，阻止默认行为。
                event.preventDefault();
                var length = key_down_history.length;
                if (length === 0) {
                    currentIndex = -1; // 如果历史记录为空，直接将当前选中的记录重置
                    return;
                }
                if (currentIndex === -1) {
                    currentIndex = length;
                }
                if (event.code === 'ArrowUp' && currentIndex > 0) {
                    currentIndex--;
                    user_input_ta.value = key_down_history[currentIndex];
                } else if (event.code === 'ArrowDown' && currentIndex < length - 1) {
                    currentIndex++;
                    user_input_ta.value = key_down_history[currentIndex];
                }
                user_input_ta.selectionStart = user_input_ta.value.length;
                user_input_ta.selectionEnd = user_input_ta.value.length;
                const input_event = new InputEvent("input", { bubbles: true, cancelable: true });
                user_input_ta.dispatchEvent(input_event);
            } else if (event.code === "Enter") {
                if (value) {
                    currentIndex = -1;
                    if (key_down_history.indexOf(value) === -1) {
                        key_down_history.push(value);
                        if (key_down_history.length > MAX_HISTORY_LENGTH) {
                            key_down_history.shift();
                        }
                    }
                }
            }
        });
    }
}

function disableSendBtn() {
    sendBtn.disabled = user_input_ta.value.trim() === '';
    user_input_ta.addEventListener('input', () => {
        sendBtn.disabled = user_input_ta.value.trim() === '';
    });
}

function checkModel() {
    const model = gradioApp().querySelector('#model-select-dropdown input');
    var modelValue = model.value;
    checkGPT();
    checkXMChat();
    function checkGPT() {
        modelValue = model.value;
        if (modelValue.toLowerCase().includes('gpt')) {
            gradioApp().querySelector('#header-btn-groups').classList.add('is-gpt');
        } else {
            gradioApp().querySelector('#header-btn-groups').classList.remove('is-gpt');
        }
        // console.log('gpt model checked')
    }
    function checkXMChat() {
        modelValue = model.value;
        if (modelValue.includes('xmchat')) {
            chatbotArea.classList.add('is-xmchat');
        } else {
            chatbotArea.classList.remove('is-xmchat');
        }
    }

    model.addEventListener('blur', ()=>{
        setTimeout(()=>{
            checkGPT();
            checkXMChat();
        }, 100);
    });
}

function toggleDarkMode(isEnabled) {
    if (isEnabled) {
        document.body.classList.add("dark");
        document.querySelector('meta[name="theme-color"]').setAttribute('content', '#171717');
        document.body.style.setProperty("background-color", "var(--neutral-950)", "important");
    } else {
        document.body.classList.remove("dark");
        document.querySelector('meta[name="theme-color"]').setAttribute('content', '#ffffff');
        document.body.style.backgroundColor = "";
    }
}
function adjustDarkMode() {
    const darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");
    apSwitch.checked = darkModeQuery.matches;
    toggleDarkMode(darkModeQuery.matches);
    darkModeQuery.addEventListener("change", (e) => {
        apSwitch.checked = e.matches;
        toggleDarkMode(e.matches);
    });
    apSwitch.addEventListener("change", (e) => {
        toggleDarkMode(e.target.checked);
    });
}
function btnToggleDarkMode() {
    apSwitch.checked = !apSwitch.checked;
    toggleDarkMode(apSwitch.checked);
}

function setScrollShadow() {
    const toolboxScroll = toolbox.querySelector('#toolbox-area > .gradio-group > div.styler > .gradio-tabs > div.tab-nav');
    const toolboxTabs = toolboxScroll.querySelectorAll('button');
    let toolboxScrollWidth = 0;
    toolboxTabs.forEach((tab) => {
        toolboxScrollWidth += tab.offsetWidth; // 获取按钮宽度并累加
    });
    function adjustScrollShadow() {
        if (toolboxScroll.scrollLeft > 0) {
            toolboxScroll.classList.add('scroll-shadow-left');
        } else {
            toolboxScroll.classList.remove('scroll-shadow-left');
        }

        if (toolboxScroll.scrollLeft + toolboxScroll.clientWidth < toolboxScrollWidth) {
            toolboxScroll.classList.add('scroll-shadow-right');
        } else {
            toolboxScroll.classList.remove('scroll-shadow-right');
        }
    }
    toolboxScroll.addEventListener('scroll', () => {
        adjustScrollShadow();
    });
    // no, I failed to make shadow appear on the top layer...
}

function setPopupBoxPosition() {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    popupWrapper.style.height = `${screenHeight}px`;
    popupWrapper.style.width = `${screenWidth}px`;
    // const popupBoxWidth = 680;
    // const popupBoxHeight = 400;
    // chuanhuPopup.style.left = `${(screenWidth - popupBoxWidth) / 2}px`;
    // chuanhuPopup.style.top = `${(screenHeight - popupBoxHeight) / 2}px`;
}

function updateVH() {
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

function setChatbotHeight() {
    return;
    const screenWidth = window.innerWidth;
    const statusDisplay = document.querySelector('#status-display');
    const statusDisplayHeight = statusDisplay ? statusDisplay.offsetHeight : 0;
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
    if (isInIframe) {
        chatbot.style.height = `700px`;
        chatbotWrap.style.maxHeight = `calc(700px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`
    } else {
        if (screenWidth <= 320) {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 150}px)`;
            chatbotWrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 150}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        } else if (screenWidth <= 499) {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 100}px)`;
            chatbotWrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 100}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        } else {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 160}px)`;
            chatbotWrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 160}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        }
    }
}
function setChatbotScroll() {
    var scrollHeight = chatbotWrap.scrollHeight;
    chatbotWrap.scrollTo(0,scrollHeight)
}

function setAutocomplete() {
    // 避免API Key被当成密码导致的模型下拉框被当成用户名而引发的浏览器自动填充行为
    const apiKeyInput = gradioApp().querySelector("#api-key input");
    apiKeyInput.setAttribute("autocomplete", "new-password");
}

function clearChatbot(a, b) {
    clearHistoryHtml();
    // clearMessageRows();
    return [a, b]
}

function chatbotContentChanged(attempt = 1, force = false) {
    // console.log('chatbotContentChanged');
    for (var i = 0; i < attempt; i++) {
        setTimeout(() => {
            // clearMessageRows();
            saveHistoryHtml();
            disableSendBtn();
            // updateSlider();
            updateCheckboxes();
            bindFancyBox();

            gradioApp().querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot').forEach(addChuanhuButton);

            if (chatbotIndicator.classList.contains('hide')) { // generation finished
                setLatestMessage();
                setChatList();
            }

            if (!chatbotIndicator.classList.contains('translucent')) { // message deleted
                var checkLatestAdded = setInterval(() => {
                    var latestMessageNow = gradioApp().querySelector('#chuanhu-chatbot .message-wrap .message.bot:last-of-type');
                    if (latestMessageNow && latestMessageNow.querySelector('.message-btn-row')) {
                        clearInterval(checkLatestAdded);
                    } else {
                        setLatestMessage();
                    }
                }, 200);
            }


        }, i === 0 ? 0 : 200);
    }
    // 理论上是不需要多次尝试执行的，可惜gradio的bug导致message可能没有渲染完毕，所以尝试500ms后再次执行
}

var chatbotObserver = new MutationObserver(() => {
    console.log('chatbotContentChanged');
    chatbotContentChanged(1);
    if (chatbotIndicator.classList.contains('hide')) {
        // setLatestMessage();
        chatbotContentChanged(2);
    }
    if (!chatbotIndicator.classList.contains('translucent')) {
        chatbotContentChanged(2);
    }

});

var chatListObserver = new MutationObserver(() => {
    setChatList();
});

// 监视页面内部 DOM 变动
var gradioObserver = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].addedNodes.length) {
            if (addInit()) {
                gradioObserver.disconnect();
                return;
            }
        }
    }
});

// 监视页面变化
window.addEventListener("DOMContentLoaded", function () {
    // const ga = document.getElementsByTagName("gradio-app");
    updateVH();
    windowWidth = window.innerWidth;
    gradioApp().addEventListener("render", initialize);
    isInIframe = (window.self !== window.top);
    historyLoaded = false;
});
window.addEventListener('resize', ()=>{
    // setChatbotHeight();
    updateVH();
    windowWidth = window.innerWidth;
    setPopupBoxPosition();
    adjustSide();
});
window.addEventListener('orientationchange', (event) => {
    updateVH();
    windowWidth = window.innerWidth;
    setPopupBoxPosition();
    adjustSide();
});
window.addEventListener('scroll', ()=>{setPopupBoxPosition();});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", adjustDarkMode);

// console suprise
var styleTitle1 = `
font-size: 16px;
font-family: ui-monospace, monospace;
color: #06AE56;
`
var styleDesc1 = `
font-size: 12px;
font-family: ui-monospace, monospace;
`
function makeML(str) {
    let l = new String(str)
    l = l.substring(l.indexOf("/*") + 3, l.lastIndexOf("*/"))
    return l
}
let ChuanhuInfo = function () {
    /*
   ________                      __             ________          __
  / ____/ /_  __  ______ _____  / /_  __  __   / ____/ /_  ____ _/ /_
 / /   / __ \/ / / / __ `/ __ \/ __ \/ / / /  / /   / __ \/ __ `/ __/
/ /___/ / / / /_/ / /_/ / / / / / / / /_/ /  / /___/ / / / /_/ / /_
\____/_/ /_/\__,_/\__,_/_/ /_/_/ /_/\__,_/   \____/_/ /_/\__,_/\__/

   川虎Chat (Chuanhu Chat) - GUI for ChatGPT API and many LLMs
 */
}
let description = `
© 2023 Chuanhu, MZhao, Keldos
GitHub repository: [https://github.com/GaiZhenbiao/ChuanhuChatGPT]\n
Enjoy our project!\n
`
console.log(`%c${makeML(ChuanhuInfo)}`,styleTitle1);
console.log(`%c${description}`, styleDesc1);
