
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
// 监听所有元素中message的变化，用来查找需要渲染的mathjax
var mObserver = new MutationObserver(function (mutationsList, observer) {
    for (var mutation of mutationsList) {
        if (mutation.type === 'childList') {
            for (var node of mutation.addedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message') && node.classList.contains('bot')) {
                    if (shouldRenderLatex) {
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    saveHistoryHtml();
                }
            }
            for (var node of mutation.removedNodes) {
                if (node.nodeType === 1 && node.classList.contains('message') && node.classList.contains('bot')) {
                    if (shouldRenderLatex) {
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    saveHistoryHtml();
                }
            }
        } else if (mutation.type === 'attributes') {
            if (mutation.target.nodeType === 1 && mutation.target.classList.contains('message') && mutation.target.classList.contains('bot')) {
                if (isThrottled) break; // 为了防止重复不断疯狂渲染，加上等待_(:з」∠)_
                isThrottled = true;
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => {
                    isThrottled = false;
                    if (shouldRenderLatex) {
                        // console.log("changed");
                        renderMathJax();
                        mathjaxUpdated = false;
                    }
                    saveHistoryHtml();
                }, 500);
            }
        }
    }
});
mObserver.observe(targetNode, { attributes: true, childList: true, subtree: true });

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
            var fakeHistory = document.createElement('div');
            fakeHistory.classList.add('history-message');
            fakeHistory.innerHTML = historyHtml;
            chatbotWrap.insertBefore(fakeHistory, chatbotWrap.firstChild);
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