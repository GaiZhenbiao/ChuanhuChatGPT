
// i18n

const language = navigator.language.slice(0,2);

const forView_i18n = {
    'zh': "仅供查看",
    'en': "For viewing only",
    'ja': "閲覧専用",
    'ko': "읽기 전용",
    'fr': "Pour consultation seulement",
    'es': "Solo para visualización",
    'sv': "Endast för visning",
};

const deleteConfirm_i18n_pref = {
    'zh': "你真的要删除 ",
    'en': "Are you sure you want to delete ",
    'ja': "本当に ",
    'ko': "정말로 ",
    'sv': "Är du säker på att du vill ta bort "
};

const deleteConfirm_i18n_suff = {
    'zh': " 吗？",
    'en': " ?",
    'ja': " を削除してもよろしいですか？",
    'ko': " 을(를) 삭제하시겠습니까?",
    'sv': " ?"
};

const usingLatest_i18n = {
    'zh': "您使用的就是最新版！",
    'en': "You are using the latest version!",
    'ja': "最新バージョンを使用しています！",
    'ko': "최신 버전을 사용하고 있습니다!",
    'sv': "Du använder den senaste versionen!"
};

const updatingMsg_i18n = {
    'zh': "正在尝试更新...",
    'en': "Trying to update...",
    'ja': "更新を試みています...",
    'ko': "업데이트를 시도 중...",
    'sv': "Försöker uppdatera..."
}

const updateSuccess_i18n = {
    'zh': "更新成功，请重启本程序。",
    'en': "Updated successfully, please restart this program.",
    'ja': "更新が成功しました、このプログラムを再起動してください。",
    'ko': "업데이트 성공, 이 프로그램을 재시작 해주세요.",
    'sv': "Uppdaterat framgångsrikt, starta om programmet."
}

const updateFailure_i18n = {
    'zh': '更新失败，请尝试<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新" target="_blank">手动更新</a>。',
    'en': 'Update failed, please try <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新" target="_blank">manually updating</a>.',
    'ja': '更新に失敗しました、<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新" target="_blank">手動での更新</a>をお試しください。',
    'ko': '업데이트 실패, <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新" target="_blank">수동 업데이트</a>를 시도하십시오.',
    'sv': 'Uppdateringen misslyckades, prova att <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新" target="_blank">uppdatera manuellt</a>.'
}


function i18n(msg) {
    return msg.hasOwnProperty(language) ? msg[language] : msg['en'];
}
