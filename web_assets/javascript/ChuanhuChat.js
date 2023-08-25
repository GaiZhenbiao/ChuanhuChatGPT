
// ChuanhuChat core javascript

const MAX_HISTORY_LENGTH = 32;

var key_down_history = [];
var currentIndex = -1;

var gradioContainer = null;
var user_input_ta = null;
var user_input_tb = null;
var userInfoDiv = null;
var appTitleDiv = null;
var chatbot = null;
var chatbotIndicator = null;
var chatbotWrap = null;
var apSwitch = null;
var messageBotDivs = null;
var loginUserForm = null;
var logginUser = null;
var updateToast = null;
var sendBtn = null;
var cancelBtn = null;
var sliders = null;
var updateChuanhuBtn = null;
var statusDisplay = null;

var isInIframe = (window.self !== window.top);
var currentTime = new Date().getTime();
var initialized = false;

// gradio 页面加载好了么??? 我能动你的元素了么??
function gradioLoaded(mutations) {
    for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].addedNodes.length) {
            if (initialized) {
                observer.disconnect(); // 停止监听
                return;
            }
            initialize();
        }
    }
}

function initialize() {
    var needInit = {gradioContainer, apSwitch, user_input_tb, userInfoDiv, appTitleDiv, chatbot, chatbotIndicator, chatbotWrap, statusDisplay, sliders, updateChuanhuBtn};
    initialized = true;

    loginUserForm = gradioApp().querySelector(".gradio-container > .main > .wrap > .panel > .form")
    gradioContainer = gradioApp().querySelector(".gradio-container");
    user_input_tb = gradioApp().getElementById('user-input-tb');
    userInfoDiv = gradioApp().getElementById("user-info");
    appTitleDiv = gradioApp().getElementById("app-title");
    chatbot = gradioApp().querySelector('#chuanhu-chatbot');
    chatbotIndicator = gradioApp().querySelector('#chuanhu-chatbot>div.wrap');
    chatbotWrap = gradioApp().querySelector('#chuanhu-chatbot > .wrapper > .wrap');
    apSwitch = gradioApp().querySelector('.apSwitch input[type="checkbox"]');
    updateToast = gradioApp().querySelector("#toast-update");
    sendBtn = gradioApp().getElementById("submit-btn");
    cancelBtn = gradioApp().getElementById("cancel-btn");
    sliders = gradioApp().querySelectorAll('input[type="range"]');
    updateChuanhuBtn = gradioApp().getElementById("update-chuanhu-btn");
    statusDisplay = gradioApp().querySelector('#status-display');

    if (loginUserForm) {
        localStorage.setItem("userLogged", true);
        userLogged = true;
    }

    for (let elem in needInit) {
        if (needInit[elem] == null) {
            initialized = false;
            return;
        }
    }

    if (initialized) {
        adjustDarkMode();
        selectHistory();
        setTimeout(showOrHideUserInfo(), 2000);
        setChatbotHeight();
        setChatbotScroll();
        setSlider();
        setAvatar();
        if (!historyLoaded) loadHistoryHtml();
        if (!usernameGotten) getUserInfo();
        chatbotObserver.observe(chatbotIndicator, { attributes: true });

        const lastCheckTime = localStorage.getItem('lastCheckTime') || 0;
        const longTimeNoCheck = currentTime - lastCheckTime > 3 * 24 * 60 * 60 * 1000;
        if (longTimeNoCheck && !updateInfoGotten && !isLatestVersion || isLatestVersion && !updateInfoGotten) {
            updateLatestVersion();
        }
    }
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

function adjustDarkMode() {
    function toggleDarkMode(isEnabled) {
        if (isEnabled) {
            document.body.classList.add("dark");
            document.body.style.setProperty("background-color", "var(--neutral-950)", "important");
        } else {
            document.body.classList.remove("dark");
            document.body.style.backgroundColor = "";
        }
    }
    
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

function setChatbotHeight() {
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

var botAvatarUrl = "";
var userAvatarUrl = "";
function setAvatar() {
    var botAvatar = gradioApp().getElementById("config-bot-avatar-url").innerText;
    var userAvatar = gradioApp().getElementById("config-user-avatar-url").innerText;

    if (botAvatar == "none") {
        botAvatarUrl = "";
    } else if (isImgUrl(botAvatar)) {
        botAvatarUrl = botAvatar;
    } else {
        // botAvatarUrl = "https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63";
        botAvatarUrl = "/file=web_assets/chatbot.png"
    }

    if (userAvatar == "none") {
        userAvatarUrl = "";
    } else if (isImgUrl(userAvatar)) {
        userAvatarUrl = userAvatar;
    } else {
        userAvatarUrl = "data:image/svg+xml,%3Csvg width='32px' height='32px' viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'%3E%3Cg stroke='none' stroke-width='1' fill='none' fill-rule='evenodd'%3E%3Crect fill-opacity='0.5' fill='%23bbbbbb' x='0' y='0' width='32' height='32'%3E%3C/rect%3E%3Cg transform='translate(5, 4)' fill='%23999999' fill-opacity='0.8' fill-rule='nonzero'%3E%3Cpath d='M2.29372246,24 L19.7187739,24 C20.4277609,24 20.985212,23.8373915 21.3911272,23.5121746 C21.7970424,23.1869576 22,22.7418004 22,22.1767029 C22,21.3161536 21.7458721,20.4130827 21.2376163,19.4674902 C20.7293605,18.5218977 19.9956681,17.6371184 19.036539,16.8131524 C18.07741,15.9891863 16.9210688,15.3177115 15.5675154,14.798728 C14.2139621,14.2797445 12.6914569,14.0202527 11,14.0202527 C9.30854307,14.0202527 7.78603793,14.2797445 6.43248458,14.798728 C5.07893122,15.3177115 3.92259002,15.9891863 2.96346097,16.8131524 C2.00433193,17.6371184 1.27063951,18.5218977 0.762383704,19.4674902 C0.254127901,20.4130827 0,21.3161536 0,22.1767029 C0,22.7418004 0.202957595,23.1869576 0.608872784,23.5121746 C1.01478797,23.8373915 1.57640453,24 2.29372246,24 Z M11.0124963,11.6521659 C11.9498645,11.6521659 12.8155943,11.3906214 13.6096856,10.8675324 C14.403777,10.3444433 15.042131,9.63605539 15.5247478,8.74236856 C16.0073646,7.84868174 16.248673,6.84722464 16.248673,5.73799727 C16.248673,4.65135034 16.0071492,3.67452644 15.5241015,2.80752559 C15.0410538,1.94052474 14.4024842,1.25585359 13.6083929,0.753512156 C12.8143016,0.251170719 11.9490027,0 11.0124963,0 C10.0759899,0 9.20860836,0.255422879 8.41035158,0.766268638 C7.6120948,1.2771144 6.97352528,1.96622098 6.49464303,2.8335884 C6.01576078,3.70095582 5.77631966,4.67803631 5.77631966,5.76482987 C5.77631966,6.86452653 6.01554533,7.85912886 6.49399667,8.74863683 C6.97244801,9.63814481 7.60871935,10.3444433 8.40281069,10.8675324 C9.19690203,11.3906214 10.0667972,11.6521659 11.0124963,11.6521659 Z'%3E%3C/path%3E%3C/g%3E%3C/g%3E%3C/svg%3E";
    }
}

function clearChatbot() {
    clearHistoryHtml();
    clearMessageRows();
}

function chatbotContentChanged(attempt = 1) {
    for (var i = 0; i < attempt; i++) {
        setTimeout(() => {
            // clearMessageRows();
            saveHistoryHtml();
            disableSendBtn();
            gradioApp().querySelectorAll('#chuanhu-chatbot .message-wrap .message.user').forEach((userElement) => {addAvatars(userElement, 'user')});
            gradioApp().querySelectorAll('#chuanhu-chatbot .message-wrap .message.bot').forEach((botElement) => {addAvatars(botElement, 'bot'); addChuanhuButton(botElement)});
        }, i === 0 ? 0 : 500);
    }
    // 理论上是不需要多次尝试执行的，可惜gradio的bug导致message可能没有渲染完毕，所以尝试500ms后再次执行
}

var chatbotObserver = new MutationObserver(() => {
    clearMessageRows();
    chatbotContentChanged(1);
    if (chatbotIndicator.classList.contains('hide')) {
        chatbotContentChanged(2);
    }
});

// 监视页面内部 DOM 变动
var observer = new MutationObserver(function (mutations) {
    gradioLoaded(mutations);
});

// 监视页面变化
window.addEventListener("DOMContentLoaded", function () {
    const ga = document.getElementsByTagName("gradio-app");
    observer.observe(ga[0], { childList: true, subtree: true });
    isInIframe = (window.self !== window.top);
    historyLoaded = false;
});
window.addEventListener('resize', setChatbotHeight);
window.addEventListener('scroll', function(){setChatbotHeight(); setUpdateWindowHeight();});
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
console.log(`%c${makeML(ChuanhuInfo)}`,styleTitle1)
console.log(`%c${description}`, styleDesc1)

// button svg code
const copyIcon   = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></span>';
const copiedIcon = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"></polyline></svg></span>';
const mdIcon     = '<span><svg stroke="currentColor" fill="none" stroke-width="1" viewBox="0 0 14 18" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g transform-origin="center" transform="scale(0.85)"><path d="M1.5,0 L12.5,0 C13.3284271,-1.52179594e-16 14,0.671572875 14,1.5 L14,16.5 C14,17.3284271 13.3284271,18 12.5,18 L1.5,18 C0.671572875,18 1.01453063e-16,17.3284271 0,16.5 L0,1.5 C-1.01453063e-16,0.671572875 0.671572875,1.52179594e-16 1.5,0 Z" stroke-width="1.8"></path><line x1="3.5" y1="3.5" x2="10.5" y2="3.5"></line><line x1="3.5" y1="6.5" x2="8" y2="6.5"></line></g><path d="M4,9 L10,9 C10.5522847,9 11,9.44771525 11,10 L11,13.5 C11,14.0522847 10.5522847,14.5 10,14.5 L4,14.5 C3.44771525,14.5 3,14.0522847 3,13.5 L3,10 C3,9.44771525 3.44771525,9 4,9 Z" stroke="none" fill="currentColor"></path></svg></span>';
const rawIcon    = '<span><svg stroke="currentColor" fill="none" stroke-width="1.8" viewBox="0 0 18 14" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g transform-origin="center" transform="scale(0.85)"><polyline points="4 3 0 7 4 11"></polyline><polyline points="14 3 18 7 14 11"></polyline><line x1="12" y1="0" x2="6" y2="14"></line></g></svg></span>';
