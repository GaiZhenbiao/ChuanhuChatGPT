// custom javascript here
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
window.onload = function() {
    console.log("loaded");
    sleep(2000).then(() => {  // 玄学避免加载不完全
        console.log(document.querySelector("#is_pinned > label > input"));

        const is_pinned = document.querySelector("#is_pinned > label > input");

        is_pinned.addEventListener("change", function(ev) {
            const elem = document.querySelector(':root');
            if (ev.target.checked) {
                console.log("pinned");
                elem.style.setProperty('--side-bar-width', '300px');
                elem.style.setProperty('--side-bar-display', 'flex');

                elem.style.setProperty('--side-bar-bg', 'var(--neutral-950)');
                elem.style.setProperty('--side-bar-icon', 'none');
            } else {
                console.log("unpinned");
                elem.style.setProperty('--side-bar-width', '20px');
                elem.style.setProperty('--side-bar-display', 'none');

                elem.style.setProperty('--side-bar-bg', 'var(--primary-800)');
                elem.style.setProperty('--side-bar-icon', 'inline');
            }

        });
    });
}