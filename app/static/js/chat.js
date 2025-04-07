// Инициализация чата
document.addEventListener('DOMContentLoaded', () => {
    const messageInput = document.querySelector('#messageInput');
    const sendButton = document.querySelector('#sendMessage');
    const messageContainer = document.querySelector('#messageContainer');
    let currentConversationId = null;
    let selectedFile = null;

    // Инициализация голосового ввода
    if (messageInput) {
        const voiceInput = new VoiceInput(messageInput);
        voiceInput.mount();
    }

    // Функция для добавления сообщения в контейнер
    function addMessage(content, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = isUser ? 'user-message' : 'assistant-message';
        
        const messageText = document.createElement('div');
        messageText.className = 'message-text markdown-content';
        messageText.innerHTML = marked.parse(content);
        
        // Подсветка кода
        messageText.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightBlock(block);
        });
        
        messageDiv.appendChild(messageText);
        messageContainer.appendChild(messageDiv);
        messageContainer.scrollTop = messageContainer.scrollHeight;
    }

    document.getElementById('fileInput').addEventListener('change', function(e) {
        selectedFile = e.target.files[0];
        const fileNameDiv = document.getElementById('selectedFileName');
        if (selectedFile) {
            fileNameDiv.textContent = `Выбран файл: ${selectedFile.name}`;
            fileNameDiv.classList.remove('hidden');
        } else {
            fileNameDiv.classList.add('hidden');
        }
    });

    // Функция для отправки сообщения
    async function sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();
        
        if (!message && !selectedFile) return;
        
        const token = localStorage.getItem('token');
        if (!token) {
            alert('Необходимо войти в систему');
            return;
        }

        try {
            const formData = new FormData();
            formData.append('message', message);
            if (selectedFile) {
                formData.append('file', selectedFile);
            }
            if (currentConversationId) {
                formData.append('conversation_id', currentConversationId);
            }

            // Добавляем сообщение пользователя
            addMessage(message, true);
            messageInput.value = '';
            
            // Сбрасываем выбранный файл
            selectedFile = null;
            document.getElementById('selectedFileName').classList.add('hidden');
            document.getElementById('fileInput').value = '';

            const response = await fetch('/api/chat/send', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: formData
            });

            if (response.status === 401) {
                // Токен истёк или недействителен
                localStorage.removeItem('token');
                window.location.reload();
                return;
            }

            const data = await response.json();
            if (response.ok) {
                currentConversationId = data.conversation_id;
                addMessage(data.assistant_response);
            } else {
                throw new Error(data.detail || 'Ошибка при отправке сообщения');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            addMessage('Произошла ошибка при отправке сообщения: ' + error.message);
        }
    }

    // Обработчики событий
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
}); 