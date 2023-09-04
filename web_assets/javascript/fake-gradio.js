
// Fake gradio components!

// buttons
function newChatClick() {
    gradioApp().querySelector('#empty-btn').click();
}

// index files
function transUpload() {
    var grUploader = gradioApp().querySelector("#upload-index-file > .center.flex");
    var chatbotUploader = gradioApp().querySelector("#upload-files-btn");
    let uploaderEvents = ["click", "drag", "dragend", "dragenter", "dragleave", "dragover", "dragstart", "drop"];
    transEventListeners(chatbotUploader, grUploader, uploaderEvents);
}

// checkbox
var grSingleSessionCB;
var grOnlineSearchCB;
var chatbotSingleSessionCB;
var chatbotOnlineSearchCB;
function setCheckboxes() {
    chatbotSingleSessionCB = gradioApp().querySelector('input[name="single-session-cb"]');
    chatbotOnlineSearchCB = gradioApp().querySelector('input[name="online-search-cb"]');
    grSingleSessionCB = gradioApp().querySelector("#gr-single-session-cb > label > input");
    grOnlineSearchCB = gradioApp().querySelector("#gr-websearch-cb > label> input");

    chatbotSingleSessionCB.addEventListener('change', (e) => {
        grSingleSessionCB.checked = chatbotSingleSessionCB.checked;
        gradioApp().querySelector('#change-single-session-btn').click();
    });
    chatbotOnlineSearchCB.addEventListener('change', (e) => {
        grOnlineSearchCB.checked = chatbotOnlineSearchCB.checked;
        gradioApp().querySelector('#change-online-search-btn').click();
    });
    grSingleSessionCB.addEventListener('change', (e) => {
        chatbotSingleSessionCB.checked = grSingleSessionCB.checked;
    });
    grOnlineSearchCB.addEventListener('change', (e) => {
        chatbotOnlineSearchCB.checked = grOnlineSearchCB.checked;
    });
}

function bgChangeSingleSession() {
    // const grSingleSessionCB = gradioApp().querySelector("#gr-single-session-cb > label > input");
    let a = chatbotSingleSessionCB.checked;
    return [a];
}
function bgChangeOnlineSearch() {
    // const grOnlineSearchCB = gradioApp().querySelector("#gr-websearch-cb > label> input");
    let a = chatbotOnlineSearchCB.checked;
    return [a];
}

// UTILS
function transEventListeners(target, source, events) {
    events.forEach((sourceEvent) => {
        target.addEventListener(sourceEvent, function (targetEvent) {
            if(targetEvent.preventDefault) targetEvent.preventDefault();
            if(targetEvent.stopPropagation) targetEvent.stopPropagation();

            source.dispatchEvent(new Event(sourceEvent, {detail: targetEvent.detail}));
            // console.log(targetEvent.detail);
        });
    });
    /* 事实上，我发现这样写的大多数gradio组件并不适用。。所以。。。生气 */
}

function bgSelectHistory(a,b,c){
    const historySelectorInput = gradioApp().querySelector('#history-select-dropdown input');
    let file = historySelectorInput.value;
    return [a,file,c]
}
