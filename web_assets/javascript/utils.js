

function isImgUrl(url) {
    const imageExtensions = /\.(jpg|jpeg|png|gif|bmp|webp)$/i;
    if (url.startsWith('data:image/')) {
        return true;
    }
    if (url.match(imageExtensions)) {
        return true;
    }
    if (url.startsWith('http://') || url.startsWith('https://')) {
        return true;
    }

    return false;
}

function downloadHistory(username, historyname) {
    let fileUrl;
    if (username === null) {
        fileUrl = `/file=./history/${historyname}`;
    } else {
        fileUrl = `/file=./history/${username}/${historyname}`;
    }
    downloadFile(fileUrl + ".json", historyname + ".json");
}

function downloadHistoryMarkdown(username, historyname) {
    let fileUrl;
    if (username === null) {
        fileUrl = `/file=./history/${historyname}`;
    } else {
        fileUrl = `/file=./history/${username}/${historyname}`;
    }
    downloadFile(fileUrl + ".md", historyname + ".md");
}

function downloadFile(fileUrl, filename="") {
    // 发送下载请求
    fetch(fileUrl)
        .then(response => response.blob())
        .then(blob => {
            // 创建一个临时的URL
            const url = URL.createObjectURL(blob);

            // 创建一个隐藏的<a>元素，设置下载属性
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;

            // 添加到DOM并触发点击事件
            document.body.appendChild(a);
            a.click();

            // 清理临时URL和DOM中的<a>元素
            URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(error => {
            console.error('Failed to download file:', error);
        });
}


/* NOTE: These reload functions are not used in the current version of the code.
 *       From stable-diffusion-webui
 */
function restart_reload() {
    document.body.innerHTML = '<h1 style="font-family:ui-monospace,monospace;margin-top:20%;color:lightgray;text-align:center;">Reloading...</h1>';

    var requestPing = function () {
        requestGet("./internal/ping", {}, function (data) {
            location.reload();
        }, function () {
            setTimeout(requestPing, 500);
        });
    };

    setTimeout(requestPing, 2000);

    return [];
}

function requestGet(url, data, handler, errorHandler) {
    var xhr = new XMLHttpRequest();
    var args = Object.keys(data).map(function (k) {
        return encodeURIComponent(k) + '=' + encodeURIComponent(data[k]);
    }).join('&');
    xhr.open("GET", url + "?" + args, true);

    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                try {
                    var js = JSON.parse(xhr.responseText);
                    handler(js);
                } catch (error) {
                    console.error(error);
                    errorHandler();
                }
            } else {
                errorHandler();
            }
        }
    };
    var js = JSON.stringify(data);
    xhr.send(js);
}
