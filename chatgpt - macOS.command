#!/bin/bash
echo Opening ChuanhuChatGPT...
cd "$(dirname "${BASH_SOURCE[0]}")"
nohup python3 ChuanhuChatbot.py >/dev/null 2>&1 &
sleep 5
open http://127.0.0.1:7860
echo Finished opening ChuanhuChatGPT (http://127.0.0.1:7860/). If you kill ChuanhuChatbot, Use "pkill -f 'ChuanhuChatbot'" command in terminal.