
var updateInfoGotten = false;
var isLatestVersion = localStorage.getItem('isLatestVersion') || false;


var statusObserver = new MutationObserver(function (mutationsList) {
    for (const mutation of mutationsList) {
        if (mutation.type === 'attributes' || mutation.type === 'childList') {
            if (statusDisplay.innerHTML.includes('<span id="update-status"')) {
                if (getUpdateStatus() === "success") {
                    updatingInfoElement.innerText = i18n(updateSuccess_i18n);
                    noUpdateHtml();
                    localStorage.setItem('isLatestVersion', 'true');
                    isLatestVersion = true;
                    enableUpdateBtns();
                } else if (getUpdateStatus() === "failure") {
                    updatingInfoElement.innerHTML = i18n(updateFailure_i18n);
                    document.querySelector('#update-button.btn-update').disabled = true;
                    document.querySelector('#cancel-button.btn-update').disabled = false;
                } else if (getUpdateStatus() != "") {
                    updatingInfoElement.innerText = getUpdateStatus();
                    enableUpdateBtns();
                }
                updateStatus.parentNode.removeChild(updateStatus);
                if (updateSpinner) updateSpinner.stop();
            }
        }
    }
});

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

var releaseNoteElement = document.getElementById('release-note-content');
var updatingInfoElement = document.getElementById('updating-info');
async function updateLatestVersion() {
    const currentVersionElement = document.getElementById('current-version');
    const latestVersionElement = document.getElementById('latest-version-title');
    releaseNoteElement = document.getElementById('release-note-content');
    updatingInfoElement = document.getElementById('updating-info');
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

function getUpdateInfo() {
    window.open('https://github.com/gaizhenbiao/chuanhuchatgpt/releases/latest', '_blank');
    closeUpdateToast();
}

var updateSpinner = null;

function bgUpdateChuanhu() {
    updateChuanhuBtn.click();
    updatingInfoElement.innerText = i18n(updatingMsg_i18n);
    var updatingSpinner = document.getElementById('updating-spinner');
    try {
        updateSpinner = new Spin.Spinner({color:'#06AE56',top:'45%',lines:9}).spin(updatingSpinner);
    } catch (error) {
        console.error("Can't create spinner")
    }
    updatingInfoElement.classList.remove('hideK');
    disableUpdateBtns();
    const releaseNoteWrap = document.getElementById('release-note-wrap');
    releaseNoteWrap.style.setProperty('display', 'none');
    statusObserver.observe(statusDisplay, { childList: true, subtree: true, characterData: true});
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
    if (updatingInfoElement.classList.contains('hideK') === false) {
        updatingInfoElement.classList.add('hideK');
    }
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
    noUpdateHtml();
}
function noUpdateHtml() {
    const versionInfoElement = document.getElementById('version-info-title');
    const gotoUpdateBtn = document.getElementById('goto-update-btn');
    const closeUpdateBtn = document.getElementById('close-update-btn');
    const releaseNoteWrap = document.getElementById('release-note-wrap');
    releaseNoteWrap.style.setProperty('display', 'none');
    versionInfoElement.textContent = i18n(usingLatest_i18n)
    gotoUpdateBtn.classList.add('hideK');
    closeUpdateBtn.classList.remove('hideK');
}

var updateStatus = null;
function getUpdateStatus() {
    updateStatus = statusDisplay.querySelector("#update-status");
    if (updateStatus) {
        return updateStatus.innerText;
    } else {
        return "unknown";
    }
}

function disableUpdateBtns() {
    const updatesButtons = document.querySelectorAll('.btn-update');
    updatesButtons.forEach( function (btn) {
        btn.disabled = true;
    });
}
function enableUpdateBtns() {
    const updatesButtons = document.querySelectorAll('.btn-update');
    updatesButtons.forEach( function (btn) {
        btn.disabled = false;
    });
}

function setUpdateWindowHeight() {
    if (!showingUpdateInfo) {return;}
    const scrollPosition = window.scrollY;
    // const originalTop = updateToast.style.getPropertyValue('top');
    const resultTop = scrollPosition - 20 + 'px';
    updateToast.style.setProperty('top', resultTop);
}
