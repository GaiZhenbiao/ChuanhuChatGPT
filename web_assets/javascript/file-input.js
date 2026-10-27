
// paste和upload部分参考:
// https://github.com/binary-husky/gpt_academic/tree/master/themes/common.js
// @Kilig947


function setPasteUploader() {
    input = user_input_tb.querySelector("textarea")
    let paste_files = [];
    if (input) {
        input.addEventListener("paste", async function (e) {
            if (window.chuanhuSupports?.("input_attachments") === false) return;
            const clipboardData = e.clipboardData || window.clipboardData;
            const items = clipboardData.items;
            if (items) {
                for (i = 0; i < items.length; i++) {
                    if (items[i].kind === "file") { // 确保是文件类型
                        const file = items[i].getAsFile();
                        // 将每一个粘贴的文件添加到files数组中
                        paste_files.push(file);
                        e.preventDefault();  // 避免粘贴文件名到输入框
                    }
                }
                if (paste_files.length > 0) {
                    // 按照文件列表执行批量上传逻辑
                    await upload_files(paste_files);
                    paste_files = [];
                }
            }
        });
    }
}

var hintArea;
function setDragUploader() {
    input = chatbotArea;
    if (input) {
        const dragEvents = ["dragover", "dragenter"];
        const leaveEvents = ["dragleave", "dragend", "drop"];

        const onDrag = function (e) {
            if (window.chuanhuSupports?.('input_attachments') === false) { e.preventDefault(); return; }
            e.preventDefault();
            e.stopPropagation();
            if (!chatbotArea.classList.contains("with-file")) {
                chatbotArea.classList.add("dragging");
                draggingHint();
            } else {
                statusDisplayMessage(clearFileHistoryMsg_i18n, 2000);
            }
        };

        const onLeave = function (e) {
            e.preventDefault();
            e.stopPropagation();
            chatbotArea.classList.remove("dragging");
            if (hintArea) {
                hintArea.remove();
            }
        };

        dragEvents.forEach(event => {
            input.addEventListener(event, onDrag);
        });

        leaveEvents.forEach(event => {
            input.addEventListener(event, onLeave);
        });

        input.addEventListener("drop", async function (e) {
            const files = e.dataTransfer.files;
            await upload_files(files);
        });
    }
}

async function upload_files(files) {
    if (window.chuanhuSupports?.('input_attachments') === false || window.chuanhuInputBusy?.()) return;
    const selector = window.chuanhuInputTarget?.() || '#upload-index-file';
    if (selector === '#agent-upload-files' && window.chuanhuAgentUploading) return;
    const uploadInputElement = gradioApp().querySelector(selector + ' input[type=file]');
    if (!files || !files.length) return;
    if (!uploadInputElement || uploadInputElement.disabled) return;
    const transfer = new DataTransfer();
    Array.from(files).forEach(file => transfer.items.add(file));
    uploadInputElement.files = transfer.files;
    uploadInputElement.dispatchEvent(new Event('change', { bubbles: true }));

}

function draggingHint() {
    hintArea = chatbotArea.querySelector(".dragging-hint");
    if (hintArea) {
        return;
    }
    hintArea = document.createElement("div");
    hintArea.classList.add("dragging-hint");
    hintArea.innerHTML = `<div class="dragging-hint-text"><p>${dropUploadMsg_i18n}</p></div>`;
    chatbotArea.appendChild(hintArea);
}
