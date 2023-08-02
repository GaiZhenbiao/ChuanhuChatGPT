
// custom javascript here

const MAX_HISTORY_LENGTH = 32;

var key_down_history = [];
var currentIndex = -1;
var user_input_ta;

var gradioContainer = null;
var user_input_ta = null;
var user_input_tb = null;
var userInfoDiv = null;
var appTitleDiv = null;
var chatbot = null;
var chatbotWrap = null;
var apSwitch = null;
var messageBotDivs = null;
var loginUserForm = null;
var logginUser = null;
var updateToast = null;
var sendBtn = null;
var cancelBtn = null;
var sliders = null;

var userLogged = false;
var usernameGotten = false;
var historyLoaded = false;
var updateInfoGotten = false;
var isLatestVersion = localStorage.getItem('isLatestVersion') || false;

var ga = document.getElementsByTagName("gradio-app");
var targetNode = ga[0];
var isInIframe = (window.self !== window.top);
var language = navigator.language.slice(0,2);
var currentTime = new Date().getTime();

var forView_i18n = {
    'zh': "仅供查看",
    'en': "For viewing only",
    'ja': "閲覧専用",
    'ko': "읽기 전용",
    'fr': "Pour consultation seulement",
    'es': "Solo para visualización",
};

var deleteConfirm_i18n_pref = {
    'zh': "你真的要删除 ",
    'en': "Are you sure you want to delete ",
    'ja': "本当に ",
    'ko': "정말로 ",
};
var deleteConfirm_i18n_suff = {
    'zh': " 吗？",
    'en': " ?",
    'ja': " を削除してもよろしいですか？",
    'ko': " 을(를) 삭제하시겠습니까?",
};
var deleteConfirm_msg_pref = "Are you sure you want to delete ";
var deleteConfirm_msg_suff = " ?";

var usingLatest_i18n = {
    'zh': "您使用的就是最新版！",
    'en': "You are using the latest version!",
    'ja': "最新バージョンを使用しています！",
    'ko': "최신 버전을 사용하고 있습니다!",
};

// gradio 页面加载好了么??? 我能动你的元素了么??
function gradioLoaded(mutations) {
    for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].addedNodes.length) {
            loginUserForm = document.querySelector(".gradio-container > .main > .wrap > .panel > .form")
            gradioContainer = document.querySelector(".gradio-container");
            user_input_tb = document.getElementById('user_input_tb');
            userInfoDiv = document.getElementById("user_info");
            appTitleDiv = document.getElementById("app_title");
            chatbot = document.querySelector('#chuanhu_chatbot');
            chatbotWrap = document.querySelector('#chuanhu_chatbot > .wrapper > .wrap');
            apSwitch = document.querySelector('.apSwitch input[type="checkbox"]');
            updateToast = document.querySelector("#toast-update");
            sendBtn = document.getElementById("submit_btn");
            cancelBtn = document.getElementById("cancel_btn");
            sliders = document.querySelectorAll('input[type="range"]');

            if (loginUserForm) {
                localStorage.setItem("userLogged", true);
                userLogged = true;
            }

            if (gradioContainer && apSwitch) {  // gradioCainter 加载出来了没?
                adjustDarkMode();
            }
            if (user_input_tb) {  // user_input_tb 加载出来了没?
                selectHistory();
            }
            if (userInfoDiv && appTitleDiv) {  // userInfoDiv 和 appTitleDiv 加载出来了没?
                if (!usernameGotten) {
                    getUserInfo();
                }
                setTimeout(showOrHideUserInfo(), 2000);
            }
            if (chatbot) {  // chatbot 加载出来了没?
                setChatbotHeight();
            }
            if (chatbotWrap) {
                if (!historyLoaded) {
                    loadHistoryHtml();
                }
                setChatbotScroll();
                mObserver.observe(chatbotWrap, { attributes: true, childList: true, subtree: true, characterData: true});
            }
            if (sliders) {
                setSlider();
            }
            if (updateToast) {
                const lastCheckTime = localStorage.getItem('lastCheckTime') || 0;
                const longTimeNoCheck = currentTime - lastCheckTime > 3 * 24 * 60 * 60 * 1000;
                if (longTimeNoCheck && !updateInfoGotten && !isLatestVersion || isLatestVersion && !updateInfoGotten) {
                    updateLatestVersion();
                }
            }
            if (cancelBtn) {
                submitObserver.observe(cancelBtn, { attributes: true, characterData: true});
            }
        }
    }
}

function webLocale() {
    // console.log("webLocale", language);
    if (forView_i18n.hasOwnProperty(language)) {
        var forView = forView_i18n[language];
        var forViewStyle = document.createElement('style');
        forViewStyle.innerHTML = '.wrapper>.wrap>.history-message>:last-child::after { content: "' + forView + '"!important; }';
        document.head.appendChild(forViewStyle);
    }
    if (deleteConfirm_i18n_pref.hasOwnProperty(language)) {
        deleteConfirm_msg_pref = deleteConfirm_i18n_pref[language];
        deleteConfirm_msg_suff = deleteConfirm_i18n_suff[language];
    }
}

function showConfirmationDialog(a, file, c) {
    if (file != "") {
        var result = confirm(deleteConfirm_msg_pref + file + deleteConfirm_msg_suff);
        if (result) {
            return [a, file, c];
        }
    }
    return [a, "CANCELED", c];
}

function selectHistory() {
    user_input_ta = user_input_tb.querySelector("textarea");
    if (user_input_ta) {
        observer.disconnect(); // 停止监听
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

var username = null;
function getUserInfo() {
    if (usernameGotten) {
        return;
    }
    userLogged = localStorage.getItem('userLogged');
    if (userLogged) {
        username = userInfoDiv.innerText;
        if (username) {
            if (username.includes("getting user info…")) {
                setTimeout(getUserInfo, 500);
                return;
            } else if (username === " ") {
                localStorage.removeItem("username");
                localStorage.removeItem("userLogged")
                userLogged = false;
                usernameGotten = true;
                return;
            } else {
                username = username.match(/User:\s*(.*)/)[1] || username;
                localStorage.setItem("username", username);
                usernameGotten = true;
                clearHistoryHtml();
            }
        }
    }
}

function toggleUserInfoVisibility(shouldHide) {
    if (userInfoDiv) {
        if (shouldHide) {
            userInfoDiv.classList.add("hideK");
        } else {
            userInfoDiv.classList.remove("hideK");
        }
    }
}
function showOrHideUserInfo() {
    // Bind mouse/touch events to show/hide user info
    appTitleDiv.addEventListener("mouseenter", function () {
        toggleUserInfoVisibility(false);
    });
    userInfoDiv.addEventListener("mouseenter", function () {
        toggleUserInfoVisibility(false);
    });
    sendBtn.addEventListener("mouseenter", function () {
        toggleUserInfoVisibility(false);
    });

    appTitleDiv.addEventListener("mouseleave", function () {
        toggleUserInfoVisibility(true);
    });
    userInfoDiv.addEventListener("mouseleave", function () {
        toggleUserInfoVisibility(true);
    });
    sendBtn.addEventListener("mouseleave", function () {
        toggleUserInfoVisibility(true);
    });

    appTitleDiv.ontouchstart = function () {
        toggleUserInfoVisibility(false);
    };
    userInfoDiv.ontouchstart = function () {
        toggleUserInfoVisibility(false);
    };
    sendBtn.ontouchstart = function () {
        toggleUserInfoVisibility(false);
    };

    appTitleDiv.ontouchend = function () {
        setTimeout(function () {
            toggleUserInfoVisibility(true);
        }, 3000);
    };
    userInfoDiv.ontouchend = function () {
        setTimeout(function () {
            toggleUserInfoVisibility(true);
        }, 3000);
    };
    sendBtn.ontouchend = function () {
        setTimeout(function () {
            toggleUserInfoVisibility(true);
        }, 3000); // Delay 1 second to hide user info
    };

    // Hide user info after 2 second
    setTimeout(function () {
        toggleUserInfoVisibility(true);
    }, 2000);
}

function toggleDarkMode(isEnabled) {
    if (isEnabled) {
        document.body.classList.add("dark");
        document.body.style.setProperty("background-color", "var(--neutral-950)", "important");
    } else {
        document.body.classList.remove("dark");
        document.body.style.backgroundColor = "";
    }
}
function adjustDarkMode() {
    const darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");

    // 根据当前颜色模式设置初始状态
    apSwitch.checked = darkModeQuery.matches;
    toggleDarkMode(darkModeQuery.matches);
    // 监听颜色模式变化
    darkModeQuery.addEventListener("change", (e) => {
        apSwitch.checked = e.matches;
        toggleDarkMode(e.matches);
    });
    // apSwitch = document.querySelector('.apSwitch input[type="checkbox"]');
    apSwitch.addEventListener("change", (e) => {
        toggleDarkMode(e.target.checked);
    });
}

function setChatbotHeight() {
    const screenWidth = window.innerWidth;
    const statusDisplay = document.querySelector('#status_display');
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
var rangeInputs = null;
var numberInputs = null;
function setSlider() {
    rangeInputs = document.querySelectorAll('input[type="range"]');
    numberInputs = document.querySelectorAll('input[type="number"]')
    setSliderRange();
    rangeInputs.forEach(rangeInput => {
        rangeInput.addEventListener('input', setSliderRange);
    });
    numberInputs.forEach(numberInput => {
        numberInput.addEventListener('input', setSliderRange);
    })
}
function setSliderRange() {
    var range = document.querySelectorAll('input[type="range"]');
    range.forEach(range => {
        range.style.backgroundSize = (range.value - range.min) / (range.max - range.min) * 100 + '% 100%';
    });
}

function addChuanhuButton(botElement) {
    var rawMessage = null;
    var mdMessage = null;
    rawMessage = botElement.querySelector('.raw-message');
    mdMessage = botElement.querySelector('.md-message');
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
}

function renderMarkdownText(message) {
    var mdDiv = message.querySelector('.md-message');
    if (mdDiv) mdDiv.classList.remove('hideM');
    var rawDiv = message.querySelector('.raw-message');
    if (rawDiv) rawDiv.classList.add('hideM');
}
function removeMarkdownText(message) {
    var rawDiv = message.querySelector('.raw-message');
    if (rawDiv) rawDiv.classList.remove('hideM');
    var mdDiv = message.querySelector('.md-message');
    if (mdDiv) mdDiv.classList.add('hideM');
}

let timeoutId;
let isThrottled = false;
var mmutation
// 监听chatWrap元素的变化，为 bot 消息添加复制按钮。
var mObserver = new MutationObserver(function (mutationsList) {
    for (mmutation of mutationsList) {
        if (mmutation.type === 'childList') {
            for (var node of mmutation.addedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message')) {
                    saveHistoryHtml();
                    disableSendBtn();
                    document.querySelectorAll('#chuanhu_chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                }
            }
            for (var node of mmutation.removedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message')) {
                    saveHistoryHtml();
                    disableSendBtn();
                    document.querySelectorAll('#chuanhu_chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                }
            }
        } else if (mmutation.type === 'attributes') {
            if (isThrottled) break; // 为了防止重复不断疯狂渲染，加上等待_(:з」∠)_
            isThrottled = true;
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                isThrottled = false;
                document.querySelectorAll('#chuanhu_chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
                saveHistoryHtml();
                disableSendBtn();
            }, 1500);
        }
    }
});
// mObserver.observe(targetNode, { attributes: true, childList: true, subtree: true, characterData: true});

var submitObserver = new MutationObserver(function (mutationsList) {
    document.querySelectorAll('#chuanhu_chatbot .message-wrap .message.bot').forEach(addChuanhuButton);
    saveHistoryHtml();
});

var loadhistorytime = 0; // for debugging
function saveHistoryHtml() {
    var historyHtml = document.querySelector('#chuanhu_chatbot>.wrapper>.wrap');
    if (!historyHtml) return;   // no history, do nothing
    localStorage.setItem('chatHistory', historyHtml.innerHTML);
    // console.log("History Saved")
    historyLoaded = false;
}
function loadHistoryHtml() {
    var historyHtml = localStorage.getItem('chatHistory');
    if (!historyHtml) {
        historyLoaded = true;
        return; // no history, do nothing
    }
    userLogged = localStorage.getItem('userLogged');
    if (userLogged){
        historyLoaded = true;
        return; // logged in, do nothing
    }
    if (!historyLoaded) {
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = historyHtml;
        var buttons = tempDiv.querySelectorAll('button.chuanhu-btn');
        var gradioCopyButtons = tempDiv.querySelectorAll('button.copy_code_button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].parentNode.removeChild(buttons[i]);
        }
        for (var i = 0; i < gradioCopyButtons.length; i++) {
            gradioCopyButtons[i].parentNode.removeChild(gradioCopyButtons[i]);
        }
        var fakeHistory = document.createElement('div');
        fakeHistory.classList.add('history-message');
        fakeHistory.innerHTML = tempDiv.innerHTML;
        webLocale();
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

var showingUpdateInfo = false;
async function getLatestRelease() {
    try {
        const response = await fetch('https://api.github.com/repos/gaizhenbiao/chuanhuchatgpt/releases/latest');
        if (!response.ok) {
            console.log(`Error: ${response.status} - ${response.statusText}`);
            updateInfoGotten = true;
            return null;
          }
        const data = await response.json();
        updateInfoGotten = true;
        return data;
    } catch (error) {
        console.log(`Error: ${error}`);
        updateInfoGotten = true;
        return null;
    }
}
async function updateLatestVersion() {
    const currentVersionElement = document.getElementById('current-version');
    const latestVersionElement = document.getElementById('latest-version-title');
    const releaseNoteElement = document.getElementById('release-note-content');
    const currentVersion = currentVersionElement.textContent;
    const versionTime = document.getElementById('version-time').innerText;
    const localVersionTime = versionTime !== "unknown" ? (new Date(versionTime)).getTime() : 0;
    updateInfoGotten = true; //无论成功与否都只执行一次，否则容易api超限...
    try {
        const data = await getLatestRelease();
        const releaseNote = data.body;
        if (releaseNote) {
            releaseNoteElement.innerHTML = marked.parse(releaseNote, {mangle: false, headerIds: false});
        }
        const latestVersion = data.tag_name;
        const latestVersionTime = (new Date(data.created_at)).getTime();
        if (latestVersionTime) {
            if (localVersionTime < latestVersionTime) {
                latestVersionElement.textContent = latestVersion;
                console.log(`New version ${latestVersion} found!`);
                if (!isInIframe) {openUpdateToast();}      
            } else {
                noUpdate();
            }
            currentTime = new Date().getTime();
            localStorage.setItem('lastCheckTime', currentTime);
        }
    } catch (error) {
        console.error(error);
    }
}
function getUpdate() {
    window.open('https://github.com/gaizhenbiao/chuanhuchatgpt/releases/latest', '_blank');
    closeUpdateToast();
}
function cancelUpdate() {
    closeUpdateToast();
}
function openUpdateToast() {
    showingUpdateInfo = true;
    setUpdateWindowHeight();
}
function closeUpdateToast() {
    updateToast.style.setProperty('top', '-500px');
    showingUpdateInfo = false;
}
function manualCheckUpdate() {
    openUpdateToast();
    updateLatestVersion();
    currentTime = new Date().getTime();
    localStorage.setItem('lastCheckTime', currentTime);
}
function noUpdate() {
    localStorage.setItem('isLatestVersion', 'true');
    isLatestVersion = true;
    const versionInfoElement = document.getElementById('version-info-title');
    const releaseNoteWrap = document.getElementById('release-note-wrap');
    const gotoUpdateBtn = document.getElementById('goto-update-btn');
    const closeUpdateBtn = document.getElementById('close-update-btn');

    versionInfoElement.textContent = usingLatest_i18n.hasOwnProperty(language) ? usingLatest_i18n[language] : usingLatest_i18n['en'];
    releaseNoteWrap.style.setProperty('display', 'none');
    gotoUpdateBtn.classList.add('hideK');
    closeUpdateBtn.classList.remove('hideK');
}
function setUpdateWindowHeight() {
    if (!showingUpdateInfo) {return;}
    const scrollPosition = window.scrollY;
    // const originalTop = updateToast.style.getPropertyValue('top');
    const resultTop = scrollPosition - 20 + 'px';
    updateToast.style.setProperty('top', resultTop);
}
    
// 监视页面内部 DOM 变动
var observer = new MutationObserver(function (mutations) {
    gradioLoaded(mutations);
});
observer.observe(targetNode, { childList: true, subtree: true });

// 监视页面变化
window.addEventListener("DOMContentLoaded", function () {
    isInIframe = (window.self !== window.top);
    historyLoaded = false;
});
window.addEventListener('resize', setChatbotHeight);
window.addEventListener('scroll', function(){setChatbotHeight();setUpdateWindowHeight();});
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
