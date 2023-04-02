// custom javascript here
const MAX_HISTORY_LENGTH = 32;

var key_down_history = [];
var currentIndex = -1;
var user_input_ta;

var ga = document.getElementsByTagName("gradio-app");
var targetNode = ga[0];
var observer = new MutationObserver(function(mutations) {
    for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].addedNodes.length) {
          var user_input_tb = document.getElementById('user_input_tb');
          if (user_input_tb) {
            // 监听到user_input_tb被添加到DOM树中
            // 这里可以编写元素加载完成后需要执行的代码
            user_input_ta = user_input_tb.querySelector("textarea");
            if (user_input_ta){
                observer.disconnect(); // 停止监听
                // 在 textarea 上监听 keydown 事件
                user_input_ta.addEventListener("keydown", function (event) {     
                    var value = user_input_ta.value.trim();               
                    // 判断按下的是否为方向键
                    if (event.code === 'ArrowUp' || event.code === 'ArrowDown') {
                        // 如果按下的是方向键，且输入框中有内容，且历史记录中没有该内容，则不执行操作
                        if(value && key_down_history.indexOf(value) === -1)
                            return;
                        // 对于需要响应的动作，阻止默认行为。
                        event.preventDefault();
                        var length = key_down_history.length;
                        if(length === 0) {
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
                        const input_event = new InputEvent("input", {bubbles: true, cancelable: true});
                        user_input_ta.dispatchEvent(input_event);
                    }else if(event.code === "Enter") {
                        if (value) {
                            currentIndex = -1;
                            if(key_down_history.indexOf(value) === -1){
                                key_down_history.push(value);
                                if (key_down_history.length > MAX_HISTORY_LENGTH) {
                                    key_down_history.shift();
                                }
                            }
                        }
                    }
                });
                break;
            }
          }
        }
      }
});

// 监听目标节点的子节点列表是否发生变化
observer.observe(targetNode, { childList: true ,  subtree: true });

