
var gradioUploader = null;

function testUpload(target) {
    gradioUploader = gradioApp().querySelector("#upload-index-file > .center.flex");
    let uploaderEvents = ["click", "drag", "dragend", "dragenter", "dragleave", "dragover", "dragstart", "drop"];
    transEventListeners(target, gradioUploader, uploaderEvents);
}


function transEventListeners(target, source, events) {
    events.forEach((sourceEvent) => {
        target.addEventListener(sourceEvent, function (targetEvent) {
            if(targetEvent.preventDefault) targetEvent.preventDefault();
            if(targetEvent.stopPropagation) targetEvent.stopPropagation();

            source.dispatchEvent(new Event(sourceEvent, {detail: targetEvent.detail}));
            console.log(targetEvent.detail);
        });
    });
}


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
