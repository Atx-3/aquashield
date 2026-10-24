/**
 * AQUA SHIELD: Tactical AI Voice Assistant Engine
 * Integrates Web Speech Recognition, Siri Waveform Visualizer, and Backend Tool Execution.
 *
 * Full round trip of a voice command:
 *   microphone -> browser speech-to-text (Web Speech API, built into Chrome/Edge)
 *   -> POST /api/voice_command {query}
 *   -> backend picks + runs a tool, replies {speech_response, ui_action, data}
 *   -> browser reads the reply aloud (speechSynthesis = text-to-speech)
 *   -> app.executeTacticalAction(ui_action) updates the map / pipeline.
 * If the microphone isn't available, a text box (prompt) is used instead.
 * The quick-command buttons ("chips") send their text the same way, without speaking.
 */

class AquaShieldVoiceModule {
    constructor(appInstance) {
        this.app = appInstance;                   // the main app, to trigger UI actions
        this.recognition = null;                  // speech-to-text engine (if supported)
        this.synthesis = window.speechSynthesis;  // text-to-speech engine
        this.isListening = false;
        this.waveformCanvas = null;
        this.waveformCtx = null;
        this.animFrameId = null;
    }

    init() {
        this.initRecognition();
        this.initWaveform();
        this.bindEvents();
    }

    // Set up speech recognition. Chrome exposes it as webkitSpeechRecognition.
    initRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = false;      // stop after one sentence
            this.recognition.interimResults = true;   // show words while still speaking
            this.recognition.lang = 'en-US';

            // Started listening: stop any speech that is playing, show "Listening..."
            this.recognition.onstart = () => {
                if (this.synthesis && this.synthesis.speaking) {
                    this.synthesis.cancel();
                }
                this.setListeningState(true);
                this.updateTranscript("Listening for tactical command...", true);
            };

            // Words recognised. "Final" results are complete; "interim" are guesses so far.
            // Only a final result is sent to the backend.
            this.recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }

                if (finalTranscript) {
                    this.updateTranscript(`"${finalTranscript}"`, false);
                    this.sendVoiceQuery(finalTranscript);
                } else if (interimTranscript) {
                    this.updateTranscript(`"${interimTranscript}"`, true);
                }
            };

            // Errors: if the microphone is blocked/missing, fall back to typing
            this.recognition.onerror = (event) => {
                console.warn("Speech recognition error:", event.error);
                this.setListeningState(false);
                if (event.error === 'not-allowed' || event.error === 'service-not-allowed' || event.error === 'audio-capture') {
                    this.updateTranscript("Microphone access blocked. Click Mic for text input.", false);
                    this.promptTextInput();
                } else {
                    this.updateTranscript("Awaiting voice command...", false);
                }
            };

            this.recognition.onend = () => {
                this.setListeningState(false);
            };
        } else {
            console.warn("Web Speech API not supported in this browser. Fallback input available.");
        }
    }

    // Find the waveform <canvas> and start animating it
    initWaveform() {
        this.waveformCanvas = document.getElementById('voice-waveform');
        if (this.waveformCanvas) {
            this.waveformCtx = this.waveformCanvas.getContext('2d');
            this.drawIdleWaveform();
        }
    }

    // Decorative animated wave (blue -> purple -> red). It is a sine pattern that moves
    // with time; it gets taller and faster while listening. It does NOT react to real audio.
    drawIdleWaveform() {
        if (!this.waveformCtx) return;
        const ctx = this.waveformCtx;
        const width = this.waveformCanvas.width;
        const height = this.waveformCanvas.height;

        ctx.clearRect(0, 0, width, height);

        // Apple Siri gradient wave
        const grad = ctx.createLinearGradient(0, 0, width, 0);
        grad.addColorStop(0, '#0071e3');
        grad.addColorStop(0.5, '#af52de');
        grad.addColorStop(1, '#ff3b30');

        ctx.strokeStyle = grad;
        ctx.lineWidth = 2.2;
        ctx.lineCap = 'round';

        ctx.beginPath();
        const steps = 30;
        const sliceWidth = width / steps;
        let x = 0;
        const amp = this.isListening ? 10 : 3.5;        // wave height
        const freq = this.isListening ? 0.007 : 0.0025;  // wave speed

        // Join 31 points into a line; Date.now() makes the wave move each frame
        for (let i = 0; i <= steps; i++) {
            const v = Math.sin(i * 0.4 + Date.now() * freq) * Math.cos(i * 0.15) * amp;
            const y = height / 2 + v;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
            x += sliceWidth;
        }
        ctx.stroke();

        // Redraw on the next screen frame (animation loop)
        this.animFrameId = requestAnimationFrame(() => this.drawIdleWaveform());
    }

    bindEvents() {
        const micBtn = document.getElementById('btn-voice-mic');
        if (micBtn) {
            micBtn.addEventListener('click', () => this.toggleListening());
        }

        // Bind both .voice-chip and .voice-command-pill query chips
        // Each chip's command text is in its data-query attribute (see index.html)
        const chips = document.querySelectorAll('.voice-chip, .voice-command-pill');
        chips.forEach(chip => {
            chip.addEventListener('click', (e) => {
                e.stopPropagation();
                const query = chip.dataset.query || chip.textContent.trim();
                this.updateTranscript(`"${query}"`, false);
                this.sendVoiceQuery(query);
            });
        });
    }

    // Mic button: start listening, or stop if already listening
    toggleListening() {
        // Intercept: If AI is currently speaking, stop speech synthesis immediately and start listening
        if (this.synthesis && this.synthesis.speaking) {
            this.synthesis.cancel();
        }

        // Browser has no speech recognition -> ask for typed text
        if (!this.recognition) {
            this.promptTextInput();
            return;
        }

        if (this.isListening) {
            this.recognition.stop();
        } else {
            try {
                this.recognition.start();
            } catch (e) {
                console.warn("Speech recognition start failed, using input dialog fallback:", e);
                this.promptTextInput();
            }
        }
    }

    // Typed fallback: browser's built-in input dialog
    promptTextInput() {
        const query = prompt("Speak or type AQUA SHIELD command (e.g. 'Who is the culprit?', '24h forecast'):");
        if (query && query.trim()) {
            this.updateTranscript(`"${query.trim()}"`, false);
            this.sendVoiceQuery(query.trim());
        }
    }

    // Add/remove the "listening" CSS class on the mic button (makes it glow)
    setListeningState(listening) {
        this.isListening = listening;
        const micBtn = document.getElementById('btn-voice-mic');
        if (micBtn) {
            micBtn.classList.toggle('listening', listening);
        }
    }

    // Show text in the assistant panel; interim (unfinished) text is drawn faded
    updateTranscript(text, isInterim = false) {
        const transcriptEl = document.getElementById('voice-transcript-text');
        if (transcriptEl) {
            transcriptEl.textContent = text;
            transcriptEl.style.opacity = isInterim ? '0.7' : '1.0';
        }
    }

    // Send the command text to the backend and handle its reply
    async sendVoiceQuery(text) {
        this.updateTranscript(`Processing: "${text}"...`, true);

        try {
            const res = await fetch('/api/voice_command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: text })
            });

            const data = await res.json();
            this.handleVoiceResponse(data);
        } catch (e) {
            console.error("Voice dispatch error:", e);
            this.updateTranscript("Error communicating with AQUA SHIELD backend.", false);
        }
    }

    // Show + speak the backend's answer, then perform the requested UI action
    handleVoiceResponse(resp) {
        const speechText = resp.speech_response || "Command executed.";
        this.updateTranscript(`AQUA SHIELD: ${speechText}`, false);

        // Speak back via Web Speech Synthesis (TTS)
        this.speak(speechText);

        // Execute returned UI action
        if (resp.ui_action) {
            this.app.executeTacticalAction(resp.ui_action, resp.data);
        }
    }

    // Text-to-speech: read `text` aloud, slightly faster than normal
    speak(text) {
        if (!this.synthesis) return;
        this.synthesis.cancel(); // Stop any pending speech

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.05;
        utterance.pitch = 1.0;

        // Choose English natural voice if available
        const voices = this.synthesis.getVoices();
        const preferredVoice = voices.find(v => v.lang.includes('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('David')));
        if (preferredVoice) utterance.voice = preferredVoice;

        this.synthesis.speak(utterance);
    }
}

// Expose the class so app.js can create it
window.AquaShieldVoice = AquaShieldVoiceModule;
