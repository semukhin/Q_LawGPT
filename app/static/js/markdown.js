/**
 * Модуль для обработки Markdown в сообщениях чата
 */

// Настройка marked.js
marked.setOptions({
    renderer: new marked.Renderer(),
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(lang, code).value;
            } catch (e) {}
        }
        return hljs.highlightAuto(code).value;
    },
    pedantic: false,
    gfm: true,
    breaks: true,
    sanitize: false,
    smartypants: true,
    xhtml: false
});

// Кастомный рендерер для улучшенного форматирования
const renderer = new marked.Renderer();

// Улучшенная обработка кодовых блоков
renderer.code = (code, language) => {
    const validLanguage = hljs.getLanguage(language) ? language : 'plaintext';
    const highlightedCode = hljs.highlight(validLanguage, code).value;
    
    return `
        <div class="code-block-container">
            <pre><code class="hljs language-${validLanguage}">${highlightedCode}</code></pre>
            <button class="copy-code-button" title="Копировать код">
                <i class="fas fa-copy"></i>
            </button>
        </div>
    `;
};

// Улучшенная обработка ссылок
renderer.link = (href, title, text) => {
    const safeHref = encodeURI(href);
    const titleAttr = title ? ` title="${title}"` : '';
    const isExternal = /^https?:\/\//.test(href);
    
    return `
        <a href="${safeHref}"${titleAttr}
            ${isExternal ? 'target="_blank" rel="noopener noreferrer"' : ''}>
            ${text}
            ${isExternal ? '<i class="fas fa-external-link-alt" style="margin-left: 4px; font-size: 0.8em;"></i>' : ''}
        </a>
    `;
};

marked.setOptions({ renderer });

// Функция для преобразования текста в HTML с Markdown
function markdownToHtml(text) {
    try {
        return marked(text);
    } catch (error) {
        console.error('Ошибка при обработке Markdown:', error);
        return escapeHtml(text);
    }
}

// Функция для безопасного экранирования HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Функция для добавления кнопок копирования кода
function addCodeCopyButtons() {
    document.querySelectorAll('.code-block-container').forEach(container => {
        const copyButton = container.querySelector('.copy-code-button');
        const codeBlock = container.querySelector('code');
        
        copyButton.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(codeBlock.textContent);
                copyButton.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                }, 2000);
            } catch (err) {
                console.error('Ошибка при копировании:', err);
                copyButton.innerHTML = '<i class="fas fa-times"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                }, 2000);
            }
        });
    });
}

// Экспортируем функции
window.MarkdownProcessor = {
    markdownToHtml,
    addCodeCopyButtons,
    escapeHtml
}; 