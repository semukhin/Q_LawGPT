// Функции для работы с формами
function showLoginForm() {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById('loginForm').style.display = 'block';
    document.getElementById('registerForm').style.display = 'none';
    document.getElementById('forgotPasswordForm').style.display = 'none';
}

function showRegisterForm() {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById('registerForm').style.display = 'block';
    document.getElementById('loginForm').style.display = 'none';
    document.getElementById('forgotPasswordForm').style.display = 'none';
}

function showForgotPasswordForm() {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById('forgotPasswordForm').style.display = 'block';
    document.getElementById('loginForm').style.display = 'none';
    document.getElementById('registerForm').style.display = 'none';
}

function hideAllForms() {
    document.getElementById('overlay').style.display = 'none';
    document.getElementById('loginForm').style.display = 'none';
    document.getElementById('registerForm').style.display = 'none';
    document.getElementById('forgotPasswordForm').style.display = 'none';
}

// Функции для работы с токеном
function setToken(token) {
    localStorage.setItem('token', token);
    updateUIState(true);
}

function getToken() {
    return localStorage.getItem('token');
}

function removeToken() {
    localStorage.removeItem('token');
    updateUIState(false);
}

// Функция для получения CSRF токена
function getCSRFToken() {
    // Сначала пробуем получить из глобальной конфигурации
    if (window.APP_CONFIG && window.APP_CONFIG.csrfToken) {
        return window.APP_CONFIG.csrfToken;
    }
    // Затем пробуем получить из мета-тега
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
        return metaToken.getAttribute('content');
    }
    return null;
}

// Обновление состояния UI
function updateUIState(isAuthenticated) {
    const authButtons = document.getElementById('authButtons');
    const userControls = document.getElementById('userControls');
    const chatInterface = document.getElementById('chatInterface');

    if (isAuthenticated) {
        authButtons.style.display = 'none';
        userControls.style.display = 'flex';
        chatInterface.style.display = 'block';
        hideAllForms();
    } else {
        authButtons.style.display = 'flex';
        userControls.style.display = 'none';
        chatInterface.style.display = 'none';
        showLoginForm();
    }
}

// Обработчики форм
document.getElementById('registerFormContent').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData();
    formData.append('email', document.getElementById('register-email').value);
    formData.append('first_name', document.getElementById('register-first-name').value);
    formData.append('last_name', document.getElementById('register-last-name').value);
    formData.append('password', document.getElementById('register-password').value);

    try {
        console.log('Sending registration request...');
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken);
        
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'X-CSRF-TOKEN': csrfToken
            },
            credentials: 'include',
            body: formData
        });

        console.log('Response status:', response.status);
        const contentType = response.headers.get('content-type');
        console.log('Response content type:', contentType);
        
        let result;
        const responseText = await response.text();
        console.log('Raw response:', responseText);
        
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response as JSON:', e);
            throw new Error('Неверный формат ответа от сервера');
        }

        if (!response.ok) {
            console.error('Registration failed:', result);
            throw new Error(result.detail || 'Ошибка при регистрации');
        }

        console.log('Registration successful:', result);
        alert('Проверьте вашу почту для подтверждения регистрации');
        showLoginForm();
    } catch (error) {
        console.error('Error during registration:', error);
        alert(error.message || 'Ошибка при отправке запроса');
    }
});

// Обработчик формы логина
document.getElementById('loginFormContent').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    formData.append('username', email);
    formData.append('password', password);
    formData.append('grant_type', 'password');

    try {
        console.log('Sending login request...');
        console.log('Email:', email);
        
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'include',
            body: formData
        });

        console.log('Response status:', response.status);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));
        
        const contentType = response.headers.get('content-type');
        console.log('Response content type:', contentType);
        
        const responseText = await response.text();
        console.log('Raw response:', responseText);
        
        let result;
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response as JSON:', e);
            throw new Error('Ошибка сервера: ' + responseText);
        }

        if (!response.ok) {
            console.error('Login failed:', result);
            throw new Error(result.detail || 'Ошибка при входе');
        }

        console.log('Login successful:', result);
        
        if (result.access_token) {
            setToken(result.access_token);
            document.getElementById('userEmail').textContent = email;
            console.log('Token set successfully');
            updateUIState(true);
            hideAllForms();
        } else {
            throw new Error('Token not received');
        }
    } catch (error) {
        console.error('Error during login:', error);
        alert(error.message || 'Ошибка при отправке запроса');
    }
});

document.getElementById('forgotPasswordFormContent').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const data = {
        email: document.getElementById('forgot-email').value
    };

    try {
        console.log('Sending password reset request...');
        const response = await fetch('/api/auth/forgot-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': getCSRFToken(),
                'Accept': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        console.log('Response status:', response.status);
        const contentType = response.headers.get('content-type');
        console.log('Response content type:', contentType);
        
        let result;
        const responseText = await response.text();
        console.log('Raw response:', responseText);
        
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response as JSON:', e);
            throw new Error('Неверный формат ответа от сервера');
        }

        if (!response.ok) {
            console.error('Password reset request failed:', result);
            throw new Error(result.detail || 'Ошибка при отправке запроса на восстановление пароля');
        }

        console.log('Password reset request successful:', result);
        alert('Инструкции по восстановлению пароля отправлены на вашу почту');
        showLoginForm();
    } catch (error) {
        console.error('Error during password reset request:', error);
        alert(error.message || 'Ошибка при отправке запроса');
    }
});

// Функция выхода
async function logout() {
    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'X-CSRF-TOKEN': getCSRFToken()
            }
        });

        if (response.ok) {
            removeToken();
        }
    } catch (error) {
        console.error('Ошибка при выходе:', error);
    }
    removeToken();
}

// Проверка аутентификации при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    const token = getToken();
    if (token) {
        // Проверяем валидность токена
        fetch('/api/auth/profile', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        }).then(response => {
            if (response.ok) {
                updateUIState(true);
            } else {
                removeToken();
            }
        }).catch(() => {
            removeToken();
        });
    } else {
        updateUIState(false);
    }
}); 