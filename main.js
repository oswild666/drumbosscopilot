// Убедимся, что DOM полностью загружен, прежде чем выполнять скрипт
document.addEventListener('DOMContentLoaded', () => {
    console.log('3aebu4CHORD Initialized');

    // Глобальные переменные и состояние
    const state = {
        bpm: 120,
        swing: 0,
        patternSize: 16,
        scale: 'None',
        isPlaying: false,
        currentStep: 0,
        pingPongMode: false,
    };

    const patternContainer = document.getElementById('pattern-container');
    let audioContext;
    let mainGain;

    // --- Утилиты для звука ---
    const noteFrequencies = {
        'C': 261.63, 'C#': 277.18, 'D': 293.66, 'D#': 311.13, 'E': 329.63, 'F': 349.23,
        'F#': 369.99, 'G': 392.00, 'G#': 415.30, 'A': 440.00, 'A#': 466.16, 'B': 493.88
    };

    function getFrequency(note) {
        const octave = parseInt(note.slice(-1), 10);
        const noteName = note.slice(0, -1).toUpperCase();
        const baseFreq = noteFrequencies[noteName];
        if (!baseFreq) return null;
        return baseFreq * Math.pow(2, octave - 4); // Октава 4 как базовая
    }

    // --- Звуковой движок ---
    let synth;

    function setupAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            mainGain = audioContext.createGain();
            mainGain.connect(audioContext.destination);
            mainGain.gain.value = 0.7;
            synth = new Synth(audioContext, mainGain);
        }
    }

    class Synth {
        constructor(audioContext, destination) {
            this.audioContext = audioContext;
            this.destination = destination;
            this.activeVoices = {}; // Для полифонии

            // Дефолтные параметры. Позже они будут управляться из UI
            this.params = {
                osc1: { type: 'sine', gain: 0.5, adsr: { a: 0.01, d: 0.1, s: 0.8, r: 0.2 } },
                osc2: { type: 'square', gain: 0.5, adsr: { a: 0.01, d: 0.1, s: 0.8, r: 0.2 } },
                osc3: { type: 'sawtooth', gain: 0.5, adsr: { a: 0.01, d: 0.1, s: 0.8, r: 0.2 } },
                osc4: { type: 'triangle', gain: 0.5, adsr: { a: 0.01, d: 0.1, s: 0.8, r: 0.2 } },
                ringMod1: { gain: 0.5 },
                ringMod2: { gain: 0.5 },
                preFilter1: { type: 'lowpass', freq: 8000, q: 1, adsr: { a: 0.1, d: 0.2, s: 0.5, r: 0.2 } },
                postFilter1: { type: 'highpass', freq: 100, q: 1 },
                chainMix: 0.5, // 0 = chain 1, 1 = chain 2
            };
        }

        noteOn(note, velocity, time) {
            const freq = getFrequency(note);
            if (!freq) return;

            const noteVelocity = velocity / 127;
            const now = time || this.audioContext.currentTime;

            // --- Создание всех узлов для голоса ---
            const nodes = {
                oscs: [this.audioContext.createOscillator(), this.audioContext.createOscillator(), this.audioContext.createOscillator(), this.audioContext.createOscillator()],
                envs: [this.audioContext.createGain(), this.audioContext.createGain(), this.audioContext.createGain(), this.audioContext.createGain()],

                // Цепочка 1
                rm1_mod: this.audioContext.createGain(), // Модулятор для RM1
                rm1_carrier: this.audioContext.createGain(), // Несущая для RM1
                chain1_sum: this.audioContext.createGain(),
                preFilter1: this.audioContext.createBiquadFilter(),
                postFilter1: this.audioContext.createBiquadFilter(),

                // Цепочка 2
                rm2_mod: this.audioContext.createGain(),
                rm2_carrier: this.audioContext.createGain(),
                chain2_sum1: this.audioContext.createGain(),
                chain2_sum2: this.audioContext.createGain(),
                chain2_inverter: this.audioContext.createGain(),
                chain2_final_sum: this.audioContext.createGain(),
                preFilter2: this.audioContext.createBiquadFilter(),
                postFilter2: this.audioContext.createBiquadFilter(),

                outputGain: this.audioContext.createGain(),
            };

            // --- Настройка параметров ---
            nodes.oscs.forEach((osc, i) => {
                osc.type = this.params[`osc${i+1}`].type;
                osc.frequency.setValueAtTime(freq, now);
                osc.connect(nodes.envs[i]);
            });

            // --- Маршрутизация ---
            // Цепочка 1: Осц1+Осц2 + (Осц3 + RingModulator) → Pre-фильтры → Post-фильтр → Лимитер.
            // Интерпретация: (Osc1 + Osc2) + (Osc3 в качестве несущей, модулированный Osc4)
            nodes.envs[0].connect(nodes.chain1_sum); // Osc1 -> sum
            nodes.envs[1].connect(nodes.chain1_sum); // Osc2 -> sum

            nodes.envs[3].connect(nodes.rm1_mod); // Osc4 (модулятор)
            nodes.rm1_mod.connect(nodes.rm1_carrier.gain); // -> модулирует громкость несущей
            nodes.envs[2].connect(nodes.rm1_carrier); // Osc3 (несущая)
            nodes.rm1_carrier.connect(nodes.chain1_sum); // RM output -> sum

            nodes.chain1_sum.connect(nodes.preFilter1);
            nodes.preFilter1.connect(nodes.postFilter1);

            // Цепочка 2: Осц4+Осц3 - (Осц2 + RingModulator) → аналогично.
            // Интерпретация: (Osc4 + Osc3) - (Osc2 + (Osc1 как несущая, модулированный Osc2))
            nodes.envs[3].connect(nodes.chain2_sum1); // Osc4 -> sum1
            nodes.envs[2].connect(nodes.chain2_sum1); // Osc3 -> sum1

            nodes.envs[1].connect(nodes.rm2_mod); // Osc2 (модулятор)
            nodes.rm2_mod.connect(nodes.rm2_carrier.gain);
            nodes.envs[0].connect(nodes.rm2_carrier); // Osc1 (несущая)

            nodes.rm2_carrier.connect(nodes.chain2_sum2); // RM2 -> sum2
            nodes.envs[1].connect(nodes.chain2_sum2); // Osc2 -> sum2

            nodes.chain2_inverter.gain.value = -1; // Инвертор фазы
            nodes.chain2_sum2.connect(nodes.chain2_inverter);

            nodes.chain2_sum1.connect(nodes.chain2_final_sum);
            nodes.chain2_inverter.connect(nodes.chain2_final_sum);

            // Подключаем фильтры для цепи 2
            nodes.chain2_final_sum.connect(nodes.preFilter2);
            nodes.preFilter2.connect(nodes.postFilter2);

            // Микширование цепочек (пока просто суммируем, позже добавим кроссфейдер)
            nodes.postFilter1.connect(nodes.outputGain);
            nodes.postFilter2.connect(nodes.outputGain);
            nodes.outputGain.connect(this.destination);

            // --- Запуск огибающих ---
            nodes.envs.forEach((env, i) => {
                 this.triggerEnvelope(env.gain, this.params[`osc${i+1}`].adsr, now, noteVelocity * this.params[`osc${i+1}`].gain);
            });

            // --- Запуск осцилляторов ---
            nodes.oscs.forEach(osc => osc.start(now));

            this.activeVoices[note] = nodes;

            const duration = (60 / state.bpm);
            this.noteOff(note, now + duration);
        }

        noteOff(note, time) {
            const voice = this.activeVoices[note];
            if (!voice) return;

            const now = time || this.audioContext.currentTime;

            // Get the release time for each envelope and find the max
            const releaseTimes = voice.envs.map((env, i) => this.params[`osc${i + 1}`].adsr.r);
            const maxReleaseTime = Math.max(...releaseTimes, 0.01); // ensure at least a small release time

            // Trigger the release phase for all oscillator envelopes
            voice.envs.forEach((envNode, i) => {
                const adsr = this.params[`osc${i + 1}`].adsr;
                envNode.gain.cancelScheduledValues(now);
                // Set value to current value to start the ramp from there
                envNode.gain.setValueAtTime(envNode.gain.value, now);
                envNode.gain.linearRampToValueAtTime(0, now + adsr.r);
            });

            // Schedule the oscillators to stop after the longest release phase
            voice.oscs.forEach(osc => {
                osc.stop(now + maxReleaseTime);
            });

            // Remove the voice from the active list
            delete this.activeVoices[note];
        }

        triggerEnvelope(param, adsr, time, maxVal) {
            param.setValueAtTime(0, time);
            param.linearRampToValueAtTime(maxVal, time + adsr.a);
            param.linearRampToValueAtTime(maxVal * adsr.s, time + adsr.a + adsr.d);
        }
    }

    function playNote(note, velocity, time) {
        if (synth) {
            synth.noteOn(note, velocity, time);
        }
    }


    // --- Логика Секвенсера ---
    function createPatternGrid(size) {
        patternContainer.innerHTML = ''; // Очищаем контейнер перед созданием новой сетки
        for (let i = 0; i < size; i++) {
            const cell = document.createElement('div');
            cell.classList.add('pattern-cell');
            cell.dataset.step = i;

            // Цветовая подсветка
            if (i % 8 === 0) cell.classList.add('highlight-8');
            else if (i % 4 === 0) cell.classList.add('highlight-4');
            else if (i % 2 === 0) cell.classList.add('highlight-2');

            cell.innerHTML = `
                <div class="cell-row cell-step-number">${String(i).padStart(2, '0')}</div>
                <div class="cell-row"><input type="text" class="note-input" placeholder="---"></div>
                <div class="cell-row"><input type="number" class="velocity-input" value="100" min="0" max="127"></div>
                <div class="cell-row">
                    <select class="chord-select">
                        <option>---</option>
                        <option>Maj</option>
                        <option>min</option>
                        <option>Maj7</option>
                        <option>min7</option>
                        <option>dim</option>
                    </select>
                </div>
                <div class="cell-row"><span class="reserved-row"></span></div>
                <div class="cell-row"><input type="number" class="mod-input" value="0" min="0" max="99"></div>
            `;
            patternContainer.appendChild(cell);
        }
    }


    let schedulerTimer = null;

    // --- Логика Секвенсера ---

    function highlightStep(step) {
        document.querySelectorAll('.pattern-cell.active').forEach(cell => cell.classList.remove('active'));
        const currentCell = document.querySelector(`.pattern-cell[data-step="${step}"]`);
        if (currentCell) {
            currentCell.classList.add('active');
        }
    }

    const chords = {
        'Maj': [0, 4, 7],
        'min': [0, 3, 7],
        'Maj7': [0, 4, 7, 11],
        'min7': [0, 3, 7, 10],
        'dim': [0, 3, 6],
    };

    const allNotes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

    function transposeNote(note, semitones) {
        const octave = parseInt(note.slice(-1), 10);
        const noteName = note.slice(0, -1).toUpperCase();
        const noteIndex = allNotes.indexOf(noteName);
        if (noteIndex === -1) return null;

        const newIndex = (noteIndex + semitones) % 12;
        const octaveOffset = Math.floor((noteIndex + semitones) / 12);

        return `${allNotes[newIndex]}${octave + octaveOffset}`;
    }

    function playStep(step) {
        highlightStep(step);
        const cell = document.querySelector(`.pattern-cell[data-step="${step}"]`);
        if (!cell) return;

        const baseNote = cell.querySelector('.note-input').value;
        if (!baseNote || baseNote === '---') return;

        const velocity = cell.querySelector('.velocity-input').value;
        const chordName = cell.querySelector('.chord-select').value;
        const chordIntervals = chords[chordName];

        if (chordIntervals) {
            chordIntervals.forEach(interval => {
                const noteToPlay = transposeNote(baseNote, interval);
                if (noteToPlay) {
                    playNote(noteToPlay.toUpperCase(), velocity, audioContext.currentTime);
                }
            });
        } else {
            playNote(baseNote.toUpperCase(), velocity, audioContext.currentTime);
        }
    }

    let playbackDirection = 1; // 1 for forward, -1 for backward

    function scheduler() {
        playStep(state.currentStep);

        if (state.pingPongMode) {
            if (state.currentStep >= state.patternSize - 1 && playbackDirection === 1) {
                playbackDirection = -1;
            } else if (state.currentStep <= 0 && playbackDirection === -1) {
                playbackDirection = 1;
            }
            state.currentStep += playbackDirection;
        } else {
            state.currentStep = (state.currentStep + 1) % state.patternSize;
        }
    }

    function startPlayback() {
        if (state.isPlaying) return;
        setupAudioContext(); // Инициализация аудио по первому действию
        state.isPlaying = true;
        const interval = 60000 / state.bpm / 4; // 16-е ноты
        schedulerTimer = setInterval(scheduler, interval);
        document.getElementById('play-pause-btn').textContent = 'PAUSE';
    }

    function stopPlayback() {
        if (!state.isPlaying) return;
        state.isPlaying = false;
        clearInterval(schedulerTimer);
        schedulerTimer = null;
        document.getElementById('play-pause-btn').textContent = 'PLAY';
    }

    function resetPlayback() {
        stopPlayback();
        state.currentStep = 0;
        highlightStep(-1); // Снять подсветку
        document.getElementById('play-pause-btn').textContent = 'PLAY';
    }

    // --- Обработчики событий ---
    function setupEventListeners() {
        document.getElementById('play-pause-btn').addEventListener('click', () => {
            state.isPlaying ? stopPlayback() : startPlayback();
        });

        document.getElementById('stop-btn').addEventListener('click', resetPlayback);

        document.getElementById('play-from-begin-btn').addEventListener('click', () => {
            resetPlayback();
            startPlayback();
        });

        document.getElementById('loop-mode-btn').addEventListener('click', (e) => {
            state.pingPongMode = !state.pingPongMode;
            e.target.textContent = state.pingPongMode ? '→←' : '→';
        });

        document.getElementById('bpm-input').addEventListener('change', (e) => {
            state.bpm = parseInt(e.target.value, 10);
            if (state.isPlaying) {
                stopPlayback();
                startPlayback();
            }
        });

        document.getElementById('edit-sound-btn').addEventListener('click', () => {
            document.getElementById('synth-editor').classList.toggle('hidden');
        });

        let isModRecording = false;
        let modTargetPath = null;

        document.getElementById('add-mod-btn').addEventListener('click', () => {
            isModRecording = !isModRecording;
            document.body.classList.toggle('mod-recording-active', isModRecording);
            document.getElementById('add-mod-btn').classList.toggle('recording', isModRecording);
            if (!isModRecording) {
                modTargetPath = null; // Сбрасываем цель, когда выходим из режима записи
            }
        });

        // --- Обработчики для контролов синтезатора ---
        const synthEditor = document.getElementById('synth-editor');

        function getParamPath(target) {
            const oscPanel = target.closest('.osc-panel');
            if (oscPanel) {
                const oscNum = oscPanel.dataset.osc;
                if (target.classList.contains('osc-gain')) return `osc${oscNum}.gain`;
                if (target.classList.contains('osc-type')) return `osc${oscNum}.type`;
            }
            // Добавить другие параметры (фильтры и т.д.)
            return null;
        }

        synthEditor.addEventListener('click', (e) => {
            if (isModRecording) {
                const path = getParamPath(e.target);
                if (path) {
                    modTargetPath = path;
                    const modTrackSelect = document.getElementById('mod-track-select');
                    // Проверяем, существует ли уже такой трек
                    if (![...modTrackSelect.options].some(opt => opt.value === path)) {
                        const option = new Option(path, path, true, true);
                        modTrackSelect.add(option);
                    } else {
                         modTrackSelect.value = path;
                    }
                    isModRecording = false; // Выходим из режима выбора цели
                    document.body.classList.remove('mod-recording-active');
                    document.getElementById('add-mod-btn').classList.remove('recording');
                }
            }
        });

        synthEditor.addEventListener('input', (e) => {
            if (!synth) return;
            const path = getParamPath(e.target);
            if(!path) return;

            const value = e.target.classList.contains('osc-type') ? e.target.value : parseFloat(e.target.value);

            // Обновляем параметр в реальном времени
            const pathParts = path.split('.');
            let paramObj = synth.params;
            for (let i = 0; i < pathParts.length - 1; i++) {
                paramObj = paramObj[pathParts[i]];
            }
            paramObj[pathParts[pathParts.length - 1]] = value;


            // Если идет запись модуляции для этого параметра
            if (modTargetPath === path && state.isPlaying) {
                const currentCell = document.querySelector(`.pattern-cell[data-step="${state.currentStep}"]`);
                if (currentCell) {
                    const modInput = currentCell.querySelector('.mod-input');
                    modInput.value = e.target.value; // Записываем значение в ячейку
                }
            }
        });


        // Клавиатурный ввод нот
        const keyToNote = {
            'q': 'C3', '2': 'C#3', 'w': 'D3', '3': 'D#3', 'e': 'E3', 'r': 'F3', '5': 'F#3', 't': 'G3', '6': 'G#3', 'y': 'A3', '7': 'A#3', 'u': 'B3',
            'a': 'C4', 's': 'D4', 'd': 'E4', 'f': 'F4', 'g': 'G4', 'h': 'A4', 'j': 'B4',
            'z': 'C5', 'x': 'D5', 'c': 'E5', 'v': 'F5', 'b': 'G5', 'n': 'A5', 'm': 'B5',
        };
        patternContainer.addEventListener('focusin', (e) => {
            if (e.target.classList.contains('note-input')) {
                e.target.addEventListener('keydown', (event) => {
                    if (keyToNote[event.key]) {
                        event.preventDefault();
                        e.target.value = keyToNote[event.key];
                    }
                });
            }
        });
    }


    // --- Инициализация ---
    function init() {
        console.log('App is ready.');
        createPatternGrid(state.patternSize);
        setupEventListeners();
    }

    init();
});
