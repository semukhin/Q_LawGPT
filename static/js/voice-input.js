class VoiceInput {
    constructor(inputElement) {
        this.inputElement = inputElement;
    }

    mount() {
        // Заглушка для голосового ввода
        // В будущем здесь будет реализация
        console.log('Voice input mounted');
    }
}

// Экспортируем класс для использования в других модулях
window.VoiceInput = VoiceInput; 