// Инициализация чата
document.addEventListener('DOMContentLoaded', () => {
    const messageInput = document.querySelector('#messageInput');
    const sendButton = document.querySelector('#sendMessage');
    const messageContainer = document.querySelector('#messageContainer');
    let currentConversationId = null;
    let selectedFile = null;
    // Глобальные переменные для WebSocket и голосового ввода
    let chatWebSocket = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;

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

    // Инициализация WebSocket соединения
    function initWebSocket() {
        const token = localStorage.getItem('token');
        if (!token) return;
        
        const clientId = uuid(); // Создаем уникальный ID клиента
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat/${clientId}`;
        
        chatWebSocket = new WebSocket(wsUrl);
        
        chatWebSocket.onopen = function(e) {
            console.log("WebSocket соединение установлено");
            
            // Отправляем токен для аутентификации
            chatWebSocket.send(JSON.stringify({
                type: "auth",
                token: token
            }));
        };
        
        chatWebSocket.onmessage = function(event) {
            const data = JSON.parse(event.data);
            console.log("Received WebSocket message:", data);
            
            switch(data.type) {
                case "thinking":
                    // Обновляем "размышления" ассистента
                    updateThinking(data.content);
                    break;
                    
                case "answer":
                    // Добавляем финальный ответ ассистента
                    addMessage(data.content, false);
                    // Сохраняем рассуждения
                    if (data.reasoning) {
                        setMessageThinking(currentAssistantMessageId, data.reasoning);
                    }
                    break;
                    
                case "message_created":
                    // Запоминаем ID сообщений
                    currentUserMessageId = data.user_message_id;
                    currentAssistantMessageId = data.assistant_message_id;
                    break;
                    
                case "error":
                    // Отображаем ошибку
                    addErrorMessage(data.content);
                    break;
            }
        };
        
        chatWebSocket.onclose = function(event) {
            if (event.wasClean) {
                console.log(`WebSocket соединение закрыто корректно, код=${event.code} причина=${event.reason}`);
            } else {
                console.log('WebSocket соединение прервано');
                // Пробуем переподключиться через 5 секунд
                setTimeout(initWebSocket, 5000);
            }
        };
        
        chatWebSocket.onerror = function(error) {
            console.error(`WebSocket ошибка: ${error.message}`);
        };
    }

    // Отправка сообщения через WebSocket
    function sendWebSocketMessage(message, conversationId = null) {
        if (!chatWebSocket || chatWebSocket.readyState !== WebSocket.OPEN) {
            console.error("WebSocket не подключен");
            return false;
        }
        
        chatWebSocket.send(JSON.stringify({
            type: "message",
            message: message,
            conversation_id: conversationId
        }));
        
        return true;
    }

    // Функция для генерации UUID (для клиентского ID)
    function uuid() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    // Инициализация голосового ввода
    function initVoiceInput() {
        document.getElementById('startVoiceBtn').addEventListener('click', startVoiceRecording);
        document.getElementById('stopVoiceBtn').addEventListener('click', stopVoiceRecording);
    }

    // Начало записи голоса
    async function startVoiceRecording() {
        if (isRecording) return;
        
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = async () => {
                isRecording = false;
                document.getElementById('startVoiceBtn').style.display = 'inline-block';
                document.getElementById('stopVoiceBtn').style.display = 'none';
                
                // Создаем аудио-блоб
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                await sendAudioForTranscription(audioBlob);
            };
            
            mediaRecorder.start();
            isRecording = true;
            
            // Обновляем UI
            document.getElementById('startVoiceBtn').style.display = 'none';
            document.getElementById('stopVoiceBtn').style.display = 'inline-block';
            
        } catch (err) {
            console.error("Ошибка при доступе к микрофону:", err);
            alert("Не удалось получить доступ к микрофону");
        }
    }

    // Остановка записи голоса
    function stopVoiceRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            // Остальное обрабатывается в onstop callback
        }
    }

    // Отправка аудио для транскрибации
    async function sendAudioForTranscription(audioBlob) {
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.wav');
        
        try {
            const response = await fetch('/api/voice/transcribe', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ошибка! статус: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.text) {
                // Добавляем текст в поле ввода
                document.getElementById('messageInput').value = data.text;
                // Фокусируемся на поле ввода
                document.getElementById('messageInput').focus();
            } else {
                alert("Не удалось распознать речь");
            }
            
        } catch (error) {
            console.error("Ошибка при отправке аудио:", error);
            alert("Ошибка при отправке аудио: " + error.message);
        }
    }

    // Форматирование времени с добавлением даты
    function formatTime(timestamp) {
        if (!timestamp) return '';
        
        const date = new Date(timestamp);
        
        // Форматируем дату (DD.MM.YYYY)
        const day = date.getDate().toString().padStart(2, '0');
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const year = date.getFullYear();
        
        // Форматируем время (HH:MM)
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        
        return `${day}.${month}.${year} ${hours}:${minutes}`;
    }

    // Обновление UI для отображения "размышлений"
    function updateThinking(content) {
        const thinkingContainer = document.getElementById('thinkingContainer');
        if (!thinkingContainer) return;
        
        thinkingContainer.innerHTML = content.replace(/\n/g, '<br>');
        thinkingContainer.style.display = 'block';
        
        // Прокручиваем до последнего сообщения
        document.getElementById('messagesContainer').scrollTop = document.getElementById('messagesContainer').scrollHeight;
    }

    // Сохранение "размышлений" для конкретного сообщения
    function setMessageThinking(messageId, thinking) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) return;
        
        const thinkingElement = messageElement.querySelector('.message-thinking');
        if (thinkingElement) {
            thinkingElement.innerHTML = thinking.replace(/\n/g, '<br>');
        } else {
            const newThinkingElement = document.createElement('div');
            newThinkingElement.className = 'message-thinking';
            newThinkingElement.innerHTML = thinking.replace(/\n/g, '<br>');
            messageElement.querySelector('.message-content').appendChild(newThinkingElement);
        }
    }

    // Инициализация при загрузке страницы
    document.addEventListener('DOMContentLoaded', function() {
        // Инициализация WebSocket если пользователь авторизован
        if (localStorage.getItem('token')) {
            initWebSocket();
        }
        
        // Инициализация голосового ввода
        initVoiceInput();
        
        // Обработчик событий авторизации
        document.addEventListener('user-authenticated', function() {
            // Подключаем WebSocket при авторизации
            initWebSocket();
        });
        
        document.addEventListener('user-logout', function() {
            // Закрываем WebSocket при выходе
            if (chatWebSocket) {
                chatWebSocket.close();
                chatWebSocket = null;
            }
        });
    });