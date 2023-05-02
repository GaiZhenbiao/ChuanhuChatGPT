
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
var empty_botton = null;
var messageBotDivs = null;
var renderLatex = null;
var loginUserForm = null;
var logginUser = null;

var userLogged = false;
var usernameGotten = false;
var shouldRenderLatex = false;
var historyLoaded = false;

var ga = document.getElementsByTagName("gradio-app");
var targetNode = ga[0];
var isInIframe = (window.self !== window.top);

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
            chatbotWrap = document.querySelector('#chuanhu_chatbot > .wrap');
            apSwitch = document.querySelector('.apSwitch input[type="checkbox"]');
            renderLatex = document.querySelector("#render_latex_checkbox > label > input");
            empty_botton = document.getElementById("empty_btn")

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
            }
            if (renderLatex) {  // renderLatex 加载出来了没?
                shouldRenderLatex = renderLatex.checked;
                updateMathJax();
            }
            if (empty_botton) {
                emptyHistory();
            }
        }
    }
}

function selectHistory() {
    user_input_ta = user_input_tb.querySelector("textarea");
    if (user_input_ta) {
        observer.disconnect(); // 停止监听
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
    var sendBtn = document.getElementById("submit_btn");

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
        gradioContainer.classList.add("dark");
        document.body.style.setProperty("background-color", "var(--neutral-950)", "important");
    } else {
        gradioContainer.classList.remove("dark");
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
    const wrap = chatbot.querySelector('.wrap');
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
    if (isInIframe) {
        chatbot.style.height = `700px`;
        wrap.style.maxHeight = `calc(700px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`
    } else {
        if (screenWidth <= 320) {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 150}px)`;
            wrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 150}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        } else if (screenWidth <= 499) {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 100}px)`;
            wrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 100}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        } else {
            chatbot.style.height = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 160}px)`;
            wrap.style.maxHeight = `calc(var(--vh, 1vh) * 100 - ${statusDisplayHeight + 160}px - var(--line-sm) * 1rem - 2 * var(--block-label-margin))`;
        }
    }
}
function setChatbotScroll() {
    var scrollHeight = chatbotWrap.scrollHeight;
    chatbotWrap.scrollTo(0,scrollHeight)
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
    var copyButton = null;
    var toggleButton = null;
    copyButton = botElement.querySelector('button.copy-bot-btn');
    toggleButton = botElement.querySelector('button.toggle-md-btn');
    if (copyButton) copyButton.remove();
    if (toggleButton) toggleButton.remove();

    // Copy bot button
    var copyButton = document.createElement('button');
    copyButton.classList.add('chuanhu-btn');
    copyButton.classList.add('copy-bot-btn');
    copyButton.setAttribute('aria-label', 'Copy');
    copyButton.innerHTML = copyIcon;
    copyButton.addEventListener('click', () => {
        const textToCopy = rawMessage.innerText;
        navigator.clipboard
            .writeText(textToCopy)
            .then(() => {
                copyButton.innerHTML = copiedIcon;
                setTimeout(() => {
                    copyButton.innerHTML = copyIcon;
                }, 1500);
            })
            .catch(() => {
                console.error("copy failed");
            });
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

function addCopyCodeButton(pre) {
    var code = null;
    var firstChild = null;
    code = pre.querySelector('code');
    if (!code) return;
    firstChild = code.querySelector('div');
    if (!firstChild) return;
    var oldCopyButton = null;
    oldCopyButton = code.querySelector('button.copy-code-btn');
    // if (oldCopyButton) oldCopyButton.remove();
    if (oldCopyButton) return; // 没太有用，新生成的对话中始终会被pre覆盖，导致按钮消失，这段代码不启用……
    var codeButton = document.createElement('button');
    codeButton.classList.add('copy-code-btn');
    codeButton.textContent = '\uD83D\uDCCE';

    code.insertBefore(codeButton, firstChild);
    codeButton.addEventListener('click', function () {
        var range = document.createRange();
        range.selectNodeContents(code);
        range.setStartBefore(firstChild);
        navigator.clipboard
            .writeText(range.toString())
            .then(() => {
                codeButton.textContent = '\u2714';
                setTimeout(function () {
                    codeButton.textContent = '\uD83D\uDCCE';
                }, 2000);
            })
            .catch(e => {
                console.error(e);
                codeButton.textContent = '\u2716';
            });
    });
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

var rendertime = 0; // for debugging
var mathjaxUpdated = false;

function renderMathJax() {
    messageBotDivs = document.querySelectorAll('.message.bot');
    for (var i = 0; i < messageBotDivs.length; i++) {
        var mathJaxSpan = messageBotDivs[i].querySelector('.MathJax_Preview');
        if (!mathJaxSpan && shouldRenderLatex && !mathjaxUpdated) {
            MathJax.Hub.Queue(["Typeset", MathJax.Hub, messageBotDivs[i]]);
            rendertime +=1; // for debugging
            // console.log("renderingMathJax", i)
        }
    }
    mathjaxUpdated = true;
    console.log("MathJax Rendered")
}

function removeMathjax() {
    // var jax = MathJax.Hub.getAllJax();
    // for (var i = 0; i < jax.length; i++) {
    //     // MathJax.typesetClear(jax[i]);
    //     jax[i].Text(newmath)
    //     jax[i].Reprocess()
    // }
    // 我真的不会了啊啊啊，mathjax并没有提供转换为原先文本的办法。
    mathjaxUpdated = true;
    // console.log("MathJax removed!");
}

function updateMathJax() {
    renderLatex.addEventListener("change", function() {
        shouldRenderLatex = renderLatex.checked;
        // console.log(shouldRenderLatex)
        if (!mathjaxUpdated) {
            if (shouldRenderLatex) {
                renderMathJax();
            } else {
                console.log("MathJax Disabled")
                removeMathjax();
            }
        } else {
            if (!shouldRenderLatex) {
                mathjaxUpdated = false; // reset
            }
        }
    });
    if (shouldRenderLatex && !mathjaxUpdated) {
        renderMathJax();
    }
    mathjaxUpdated = false;
}

let timeoutId;
let isThrottled = false;
var mmutation
// 监听所有元素中 bot message 的变化，用来查找需要渲染的mathjax, 并为 bot 消息添加复制按钮。
var mObserver = new MutationObserver(function (mutationsList) {
    for (mmutation of mutationsList) {
        if (mmutation.type === 'childList') {
            for (var node of mmutation.addedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message') && node.getAttribute('data-testid') === 'bot') {
                    if (shouldRenderLatex) {
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    saveHistoryHtml();
                    document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot').forEach(addChuanhuButton);
                    document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot pre').forEach(addCopyCodeButton);
                }
            }
            for (var node of mmutation.removedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message') && node.getAttribute('data-testid') === 'bot') {
                    if (shouldRenderLatex) {
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    saveHistoryHtml();
                    document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot').forEach(addChuanhuButton);
                    document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot pre').forEach(addCopyCodeButton);
                }
            }
        } else if (mmutation.type === 'attributes') {
            if (mmutation.target.nodeType === 1 && mmutation.target.classList.contains('message') && mmutation.target.getAttribute('data-testid') === 'bot') {
                document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot pre').forEach(addCopyCodeButton); // 目前写的是有点问题的，会导致加button次数过多，但是bot对话内容生成时又是不断覆盖pre的……
                if (isThrottled) break; // 为了防止重复不断疯狂渲染，加上等待_(:з」∠)_
                isThrottled = true;
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => {
                    isThrottled = false;
                    if (shouldRenderLatex) {
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    document.querySelectorAll('#chuanhu_chatbot>.wrap>.message-wrap .message.bot').forEach(addChuanhuButton);
                    saveHistoryHtml();
                }, 500);
            }
        }
    }
});
mObserver.observe(document.documentElement, { attributes: true, childList: true, subtree: true });

var loadhistorytime = 0; // for debugging
function saveHistoryHtml() {
    var historyHtml = document.querySelector('#chuanhu_chatbot > .wrap');
    localStorage.setItem('chatHistory', historyHtml.innerHTML);
    console.log("History Saved")
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
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].parentNode.removeChild(buttons[i]);
        }
        var fakeHistory = document.createElement('div');
        fakeHistory.classList.add('history-message');
        fakeHistory.innerHTML = tempDiv.innerHTML;
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
function emptyHistory() {
    empty_botton.addEventListener("click", function () {
        clearHistoryHtml();
    });
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
window.addEventListener('scroll', setChatbotHeight);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", adjustDarkMode);

// button svg code
const copyIcon   = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></span>';
const copiedIcon = '<span><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"></polyline></svg></span>';
const mdIcon     = '<span><svg version="1.1" viewBox="0 0 16 12" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><g transform="translate(.89568 .14467)" fill="currentColor" fill-rule="nonzero"><path d="m3.3444 11.046c0.46893 0 0.90596-0.13231 1.3111-0.39693 0.40513-0.26462 0.75997-0.64154 1.0645-1.1308 0.30456-0.48923 0.54218-1.0726 0.71287-1.7501 0.17069-0.67748 0.25604-1.427 0.25604-2.2485 0-1.099-0.14849-2.0631-0.44548-2.8922-0.29698-0.82913-0.69818-1.4744-1.2036-1.9357-0.5054-0.46133-1.0706-0.69199-1.6955-0.69199-0.62485 0-1.19 0.23066-1.6954 0.69199-0.5054 0.46133-0.90659 1.1066-1.2036 1.9357-0.29698 0.82913-0.44548 1.7932-0.44548 2.8922 0 0.82149 0.085445 1.571 0.25634 2.2485 0.17089 0.67748 0.40851 1.2608 0.71287 1.7501 0.30436 0.48923 0.6592 0.86616 1.0645 1.1308s0.84222 0.39693 1.3107 0.39693zm0-0.95334c-0.42933 0-0.82399-0.1921-1.184-0.5763-0.36-0.3842-0.64801-0.92018-0.86403-1.6079-0.21602-0.68776-0.32403-1.484-0.32403-2.3887 0-0.90004 0.10801-1.6929 0.32403-2.3785 0.21602-0.68561 0.50403-1.2206 0.86403-1.6051 0.36-0.38443 0.75466-0.57876 1.184-0.58299 0.43786 0 0.83773 0.19116 1.1996 0.57347 0.36188 0.38231 0.65085 0.91638 0.8669 1.6022 0.21605 0.68581 0.32408 1.4828 0.32408 2.3909 0 0.90004-0.10803 1.693-0.32408 2.3788-0.21605 0.68584-0.50502 1.2219-0.8669 1.6082-0.36188 0.38631-0.76175 0.58159-1.1996 0.58582zm-1.2514-2.4761c0.50523 0 0.91061-0.1611 1.2161-0.48331 0.30551-0.32221 0.45827-0.74631 0.45827-1.2723 0-0.5217-0.15276-0.94377-0.45827-1.2662s-0.71089-0.48366-1.2161-0.48366c-0.50477 0-0.90991 0.16122-1.2154 0.48366-0.30551 0.32244-0.45827 0.74451-0.45827 1.2662 0 0.526 0.15276 0.9501 0.45827 1.2723 0.30551 0.32221 0.71066 0.48331 1.2154 0.48331zm-0.47607-1.9676c-0.10579-0.013092-0.18831-0.074651-0.24756-0.18468-0.059245-0.11003-0.07637-0.23083-0.051376-0.36241 0.025391-0.13118 0.083776-0.23804 0.17516-0.32056s0.18785-0.1134 0.28941-0.092636c0.11003 0.020762 0.1936 0.085297 0.25073 0.1936 0.057129 0.10831 0.071114 0.22614 0.041954 0.35349-0.022018 0.13158-0.077362 0.23863-0.16603 0.32115s-0.1861 0.1132-0.29229 0.092041zm9.2941 5.397c0.46847 0 0.90528-0.13231 1.3104-0.39693s0.76-0.64154 1.0645-1.1308c0.30452-0.48923 0.54225-1.0726 0.71317-1.7501 0.17092-0.67748 0.25639-1.427 0.25639-2.2485 0-1.099-0.14859-2.0631-0.44577-2.8922-0.29718-0.82913-0.69837-1.4744-1.2036-1.9357-0.5052-0.46133-1.0703-0.69199-1.6952-0.69199-0.62531 0-1.1906 0.23066-1.6958 0.69199-0.5052 0.46133-0.90628 1.1066-1.2032 1.9357-0.29695 0.82913-0.44543 1.7932-0.44543 2.8922 0 0.82149 0.085346 1.571 0.25604 2.2485 0.17069 0.67748 0.40832 1.2608 0.71287 1.7501 0.30456 0.48923 0.6594 0.86616 1.0645 1.1308 0.40513 0.26462 0.84212 0.39693 1.311 0.39693zm0-0.95909c-0.43739 0-0.83597-0.1921-1.1957-0.5763-0.35977-0.3842-0.64768-0.91922-0.86373-1.6051-0.21605-0.68584-0.32408-1.4811-0.32408-2.3858 0-0.90004 0.10803-1.6929 0.32408-2.3785 0.21605-0.68561 0.50396-1.2206 0.86373-1.6051 0.35977-0.38443 0.75835-0.57684 1.1957-0.57724 0.43356 0 0.83034 0.1921 1.1903 0.5763 0.36 0.3842 0.64812 0.91826 0.86437 1.6022s0.32438 1.478 0.32438 2.3823c0 0.90388-0.10812 1.6987-0.32438 2.3845-0.21625 0.68581-0.50437 1.2209-0.86437 1.6054-0.36 0.38443-0.75678 0.57684-1.1903 0.57724zm-1.2629-2.4703c0.50484 0 0.91191-0.1611 1.2212-0.48331 0.30932-0.32221 0.46397-0.74631 0.46397-1.2723 0-0.5217-0.15466-0.94377-0.46397-1.2662s-0.71639-0.48366-1.2212-0.48366c-0.5014 0-0.90676 0.16122-1.2161 0.48366s-0.46397 0.74451-0.46397 1.2662c0 0.526 0.15466 0.9501 0.46397 1.2723 0.30932 0.32221 0.71467 0.48331 1.2161 0.48331zm-0.47032-1.9676c-0.10619-0.016927-0.18891-0.079445-0.24815-0.18755s-0.074254-0.22795-0.045029-0.35954c0.024928-0.13118 0.081181-0.23804 0.16876-0.32056s0.18407-0.1134 0.28946-0.092636c0.11042 0.016927 0.19324 0.080503 0.24845 0.19073 0.055211 0.11022 0.069923 0.22901 0.044136 0.35636-0.025391 0.13158-0.081561 0.23863-0.16851 0.32115-0.08695 0.08252-0.18332 0.1132-0.28912 0.092041z"/></g></g></svg></span>';
const rawIcon    = '<span><svg version="1.1" viewBox="0 0 20 9" height=".8em" width=".8em" xmlns="http://www.w3.org/2000/svg"><g fill="none" fill-rule="evenodd"><g transform="translate(.36664 .76806)" fill="currentColor" fill-rule="nonzero"><path d="m5.0103 7.6388c0.52652 0 1.0205-0.099066 1.4818-0.2972 0.46136-0.19813 0.8667-0.47292 1.216-0.82435s0.62305-0.75785 0.82118-1.2192 0.2972-0.95532 0.2972-1.4818-0.099066-1.0203-0.2972-1.4815c-0.19813-0.4612-0.47186-0.86655-0.82118-1.2161s-0.75466-0.62334-1.216-0.82148c-0.46136-0.19813-0.95531-0.2972-1.4818-0.2972-0.53029 0-1.0261 0.099066-1.4875 0.2972-0.4614 0.19813-0.86674 0.47196-1.216 0.82148-0.34929 0.34952-0.62311 0.75488-0.82148 1.2161-0.19836 0.4612-0.29755 0.95502-0.29755 1.4815s0.099182 1.0204 0.29755 1.4818 0.47219 0.86781 0.82148 1.2192c0.34929 0.35144 0.75463 0.62622 1.216 0.82435 0.4614 0.19813 0.95724 0.2972 1.4875 0.2972zm0-1.1309c-0.49538 0-0.94706-0.12067-1.355-0.36201s-0.73274-0.566-0.97432-0.97397c-0.24157-0.40797-0.36236-0.85988-0.36236-1.3557 0-0.49538 0.12079-0.94611 0.36236-1.3522 0.24157-0.40608 0.56635-0.7298 0.97432-0.97114s0.85964-0.36201 1.355-0.36201c0.49161 0 0.94044 0.12067 1.3465 0.36201 0.40605 0.24134 0.73082 0.566 0.97432 0.97397s0.36524 0.85776 0.36524 1.3494c0 0.49538-0.12175 0.94621-0.36524 1.3525-0.24349 0.40628-0.56826 0.73105-0.97432 0.97432-0.40605 0.24326-0.85488 0.36489-1.3465 0.36489zm9.2987 1.1309c0.52652 0 1.0205-0.099066 1.4818-0.2972 0.46136-0.19813 0.86766-0.47292 1.2189-0.82435s0.62602-0.75785 0.82435-1.2192 0.2975-0.95532 0.2975-1.4818-0.099166-1.0203-0.2975-1.4815c-0.19833-0.4612-0.47312-0.86655-0.82435-1.2161s-0.75754-0.62334-1.2189-0.82148c-0.46136-0.19813-0.95531-0.2972-1.4818-0.2972-0.52606 0-1.0199 0.099066-1.4815 0.2972-0.46159 0.19813-0.86799 0.47196-1.2192 0.82148-0.3512 0.34952-0.62491 0.75488-0.82113 1.2161-0.19622 0.4612-0.29432 0.95502-0.29432 1.4815s0.098108 1.0204 0.29432 1.4818 0.46992 0.86781 0.82113 1.2192c0.3512 0.35144 0.7576 0.62622 1.2192 0.82435 0.46159 0.19813 0.95542 0.2972 1.4815 0.2972zm0-1.1309c-0.49155 0-0.9413-0.12163-1.3493-0.36489-0.40797-0.24326-0.73264-0.56803-0.97402-0.97432-0.24138-0.40628-0.36206-0.85712-0.36206-1.3525 0-0.49161 0.12069-0.9414 0.36206-1.3494 0.24138-0.40797 0.56605-0.73263 0.97402-0.97397 0.40797-0.24134 0.85773-0.36201 1.3493-0.36201 0.49584 0 0.94679 0.12067 1.3528 0.36201 0.40605 0.24134 0.73072 0.56506 0.97402 0.97114 0.24329 0.40608 0.36494 0.85682 0.36494 1.3522 0 0.49584-0.12165 0.94775-0.36494 1.3557-0.24329 0.40797-0.56797 0.73263-0.97402 0.97397-0.40605 0.24134-0.857 0.36201-1.3528 0.36201zm-12.709-3.4895h-1.1406c-0.30621 0-0.45931 0.15519-0.45931 0.46556v0.33157c0 0.3074 0.1531 0.4611 0.45931 0.4611h1.1406v-1.2582zm16.12 1.2582h1.1342c0.30621 0 0.45931-0.1537 0.45931-0.4611v-0.33157c0-0.31037-0.1531-0.46556-0.45931-0.46556h-1.1342v1.2582zm-9.2115-0.19122c0.15644-0.098455 0.33717-0.17253 0.54218-0.22222 0.20501-0.04969 0.40799-0.074535 0.60893-0.074535s0.40403 0.024845 0.60928 0.074535c0.20524 0.04969 0.38585 0.12376 0.54183 0.22222v-1.1725c-0.17635-0.08404-0.36874-0.14401-0.57719-0.17992-0.20845-0.035904-0.39975-0.053856-0.57392-0.053856s-0.36631 0.017952-0.57645 0.053856-0.40169 0.095876-0.57466 0.17992v1.1725z"/></g></g></svg></span>';
