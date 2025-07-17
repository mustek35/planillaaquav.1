// speechWorker.js

self.onmessage = function(e) {
    const { message, voiceLang, pitch, rate } = e.data;

    if ('speechSynthesis' in self) {
        const utterance = new SpeechSynthesisUtterance(message);

        const voices = self.speechSynthesis.getVoices();
        const selectedVoice = voices.find(voice => voice.lang === voiceLang);

        if (selectedVoice) {
            utterance.voice = selectedVoice;
        } else {
            console.error('Voz seleccionada no encontrada.');
        }

        utterance.pitch = pitch || 1.4;
        utterance.rate = rate || 1.4;

        utterance.onend = function() {
            self.postMessage('end');
        };

        self.speechSynthesis.speak(utterance);
    } else {
        console.error('La síntesis de voz no es soportada en este navegador.');
    }
};
