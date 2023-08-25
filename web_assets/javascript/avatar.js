
function addAvatars(messageElement, role='user'||'bot') {
    if(messageElement.innerHTML === '') {
        return;
    }
    if (messageElement.classList.contains('avatar-added') || messageElement.classList.contains('hide')) {
        return;
    }
    if (role === 'bot' && botAvatarUrl === "" || role === 'user' && userAvatarUrl === "") {
        messageElement.classList.add('avatar-added');
        return;
    }


    const messageRow = document.createElement('div');
    messageRow.classList.add('message-row');
    messageElement.classList.add('avatar-added');

    if (role === 'bot') {
        messageRow.classList.add('bot-message-row');
    } else if (role === 'user') {
        messageRow.classList.add('user-message-row');
    }

    const avatarDiv = document.createElement('div');
    avatarDiv.classList.add('chatbot-avatar');
    if (role === 'bot') {
        avatarDiv.classList.add('bot-avatar');
        avatarDiv.innerHTML = `<img src="${botAvatarUrl}" alt="bot-avatar" />`;
    } else if (role === 'user') {
        avatarDiv.classList.add('user-avatar');
        avatarDiv.innerHTML = `<img src="${userAvatarUrl}" alt="user-avatar" />`;
    }

    messageElement.parentNode.replaceChild(messageRow, messageElement);

    if (role === 'bot') {
        messageRow.appendChild(avatarDiv);
        messageRow.appendChild(messageElement);
    } else  if (role === 'user') {
        messageRow.appendChild(messageElement);
        messageRow.appendChild(avatarDiv);
    }
}

function clearMessageRows() {
    const messageRows = chatbotWrap.querySelectorAll('.message-row');
    messageRows.forEach((messageRow) => {
        if (messageRow.innerText === '') {
            messageRow.parentNode.removeChild(messageRow);
        }
    });
}