// --- DOM Elements ---
const masterVolume = document.getElementById('master-volume');
const globalAttack = document.getElementById('global-attack');
const globalDecay = document.getElementById('global-decay');
const globalSustain = document.getElementById('global-sustain');
const globalRelease = document.getElementById('global-release');

const vco1Waveform = document.getElementById('vco1-waveform');
const vco1Pitch = document.getElementById('vco1-pitch');
const vco1Attack = document.getElementById('vco1-attack');
const vco1Decay = document.getElementById('vco1-decay');
const vco1Sustain = document.getElementById('vco1-sustain');
const vco1Release = document.getElementById('vco1-release');

const vco2Waveform = document.getElementById('vco2-waveform');
const fmAmount = document.getElementById('fm-amount');

const addDetuneOscButton = document.getElementById('add-detune-osc');
const detuneOscsContainer = document.getElementById('detune-oscillators-container');
const addFmOscButton = document.getElementById('add-fm-osc');
const fmOscsContainer = document.getElementById('fm-oscillators-container');

const keyboardKeys = document.querySelectorAll('.key');

// --- Audio Context ---
const audioContext = new (window.AudioContext || window.webkitAudioContext)();
const masterGain = audioContext.createGain();
masterGain.connect(audioContext.destination);

// --- State ---
let activeNotes = {};
let detuneOscillators = [];
let fmOscillators = [];
let detuneOscCounter = 0;
let fmOscCounter = 0;


// --- Key Mappings ---
const keyToNote = {
    'q': 48, 'w': 50, 'e': 52, 'r': 53, 't': 55, 'y': 57, 'u': 59,
    'a': 60, 's': 62, 'd': 64, 'f': 65, 'g': 67, 'h': 69, 'j': 71,
    'z': 72, 'x': 74, 'c': 76, 'v': 77, 'b': 79, 'n': 81, 'm': 83
};


function midiToFreq(midi) {
    return Math.pow(2, (midi - 69) / 12) * 440;
}

// --- ADSR Envelope ---
function applyAdsr(gainNode, adsr) {
    const now = audioContext.currentTime;
    gainNode.gain.cancelScheduledValues(now);
    gainNode.gain.setValueAtTime(0, now);
    gainNode.gain.linearRampToValueAtTime(1, now + parseFloat(adsr.attack));
    gainNode.gain.linearRampToValueAtTime(parseFloat(adsr.sustain), now + parseFloat(adsr.attack) + parseFloat(adsr.decay));
}

function releaseAdsr(gainNode, adsr) {
    const now = audioContext.currentTime;
    gainNode.gain.cancelScheduledValues(now);
    gainNode.gain.setValueAtTime(gainNode.gain.value, now);
    gainNode.gain.linearRampToValueAtTime(0, now + parseFloat(adsr.release));
}


// --- Note On/Off ---
function noteOn(midiNote) {
    if (activeNotes[midiNote]) return;

    const freq = midiToFreq(midiNote + parseInt(vco1Pitch.value));

    const noteGain = audioContext.createGain();
    noteGain.connect(masterGain);
    const globalAdsr = {
        attack: globalAttack.value, decay: globalDecay.value,
        sustain: globalSustain.value, release: globalRelease.value
    };
    applyAdsr(noteGain, globalAdsr);

    const vco1 = audioContext.createOscillator();
    vco1.type = vco1Waveform.value;
    vco1.frequency.setValueAtTime(freq, audioContext.currentTime);

    const vco1Gain = audioContext.createGain();
    const vco1Adsr = {
        attack: vco1Attack.value, decay: vco1Decay.value,
        sustain: vco1Sustain.value, release: vco1Release.value
    };
    applyAdsr(vco1Gain, vco1Adsr);
    vco1.connect(vco1Gain);
    vco1Gain.connect(noteGain);
    vco1.start();

    const vco2 = audioContext.createOscillator();
    vco2.type = vco2Waveform.value;
    vco2.frequency.setValueAtTime(freq, audioContext.currentTime);

    const fmGain = audioContext.createGain();
    fmGain.gain.setValueAtTime(parseFloat(fmAmount.value), audioContext.currentTime);

    vco2.connect(fmGain);
    fmGain.connect(vco1.frequency);
    vco2.start();

    const activeDetuneOscs = [];
    detuneOscillators.forEach((oscState, index) => {
        const detuneOsc = audioContext.createOscillator();
        detuneOsc.type = vco1Waveform.value; // Same wave as VCO1 for simplicity
        const detuneFreq = freq * Math.pow(2, oscState.detune.value / 1200);
        detuneOsc.frequency.setValueAtTime(detuneFreq, audioContext.currentTime);

        const detuneGain = audioContext.createGain();
        const detuneAdsr = {
            attack: oscState.attack.value, decay: oscState.decay.value,
            sustain: oscState.sustain.value, release: oscState.release.value
        };
        applyAdsr(detuneGain, detuneAdsr);
        detuneOsc.connect(detuneGain);
        detuneGain.connect(noteGain);
        detuneOsc.start();

        // Check if there's a corresponding FM oscillator
        if (fmOscillators[index]) {
            const fmOsc = audioContext.createOscillator();
            fmOsc.type = vco2Waveform.value; // Same wave as VCO2
            fmOsc.frequency.setValueAtTime(freq, audioContext.currentTime); // Base freq, can be changed

            const fmOscGain = audioContext.createGain();
            fmOscGain.gain.setValueAtTime(parseFloat(fmOscillators[index].amount.value), audioContext.currentTime);

            fmOsc.connect(fmOscGain);
            fmOscGain.connect(detuneOsc.frequency);
            fmOsc.start();
            activeDetuneOscs.push({ detuneOsc, detuneGain, detuneAdsr, fmOsc });
        } else {
            activeDetuneOscs.push({ detuneOsc, detuneGain, detuneAdsr });
        }
    });


    activeNotes[midiNote] = {
        noteGain, globalAdsr, vco1, vco1Gain, vco1Adsr, vco2, activeDetuneOscs
    };
}

function noteOff(midiNote) {
    const note = activeNotes[midiNote];
    if (!note) return;

    releaseAdsr(note.noteGain, note.globalAdsr);
    releaseAdsr(note.vco1Gain, note.vco1Adsr);

    let maxRelease = Math.max(parseFloat(note.globalAdsr.release), parseFloat(note.vco1Adsr.release));

    note.activeDetuneOscs.forEach(osc => {
        releaseAdsr(osc.detuneGain, osc.detuneAdsr);
        maxRelease = Math.max(maxRelease, parseFloat(osc.detuneAdsr.release));
        osc.detuneOsc.stop(audioContext.currentTime + maxRelease);
        if (osc.fmOsc) {
            osc.fmOsc.stop(audioContext.currentTime + maxRelease);
        }
    });

    note.vco1.stop(audioContext.currentTime + maxRelease);
    note.vco2.stop(audioContext.currentTime + maxRelease);

    delete activeNotes[midiNote];
}

// --- Event Listeners ---
window.addEventListener('keydown', (e) => {
    if (keyToNote[e.key] && !e.repeat) {
        noteOn(keyToNote[e.key]);
        document.querySelector(`.key[data-key="${e.key}"]`).classList.add('active');
    }
});
window.addEventListener('keyup', (e) => {
    if (keyToNote[e.key]) {
        noteOff(keyToNote[e.key]);
        document.querySelector(`.key[data-key="${e.key}"]`).classList.remove('active');
    }
});
keyboardKeys.forEach(key => {
    key.addEventListener('mousedown', () => { noteOn(keyToNote[key.dataset.key]); key.classList.add('active'); });
    key.addEventListener('mouseup', () => { noteOff(keyToNote[key.dataset.key]); key.classList.remove('active'); });
    key.addEventListener('mouseleave', () => { if (key.classList.contains('active')) { noteOff(keyToNote[key.dataset.key]); key.classList.remove('active'); }});
});

masterGain.gain.value = masterVolume.value;
masterVolume.addEventListener('input', (e) => { masterGain.gain.value = e.target.value; });


// --- Dynamic Oscillator Management ---
function addDetuneOsc() {
    if (detuneOscillators.length >= 16) return;
    detuneOscCounter++;
    const id = detuneOscCounter;

    const oscDiv = document.createElement('div');
    oscDiv.classList.add('detune-osc-control');
    oscDiv.id = `detune-osc-${id}`;
    oscDiv.innerHTML = `
        <h4>Detune Osc ${id}</h4>
        <div class="control"><label>Detune</label><input type="range" min="-100" max="100" value="7" step="1" class="detune-amount"></div>
        <div class="adsr-group">
            <div class="control"><label>A</label><input type="range" min="0" max="2" value="0.1" step="0.01" class="detune-attack"></div>
            <div class="control"><label>D</label><input type="range" min="0" max="2" value="0.1" step="0.01" class="detune-decay"></div>
            <div class="control"><label>S</label><input type="range" min="0" max="1" value="0.8" step="0.01" class="detune-sustain"></div>
            <div class="control"><label>R</label><input type="range" min="0" max="2" value="0.1" step="0.01" class="detune-release"></div>
        </div>
        <button class="remove-detune-osc" data-id="${id}">X</button>
    `;
    detuneOscsContainer.appendChild(oscDiv);

    const newOscState = {
        id: id,
        detune: oscDiv.querySelector('.detune-amount'),
        attack: oscDiv.querySelector('.detune-attack'),
        decay: oscDiv.querySelector('.detune-decay'),
        sustain: oscDiv.querySelector('.detune-sustain'),
        release: oscDiv.querySelector('.detune-release'),
        element: oscDiv
    };
    detuneOscillators.push(newOscState);

    oscDiv.querySelector('.remove-detune-osc').addEventListener('click', (e) => {
        const idToRemove = parseInt(e.target.dataset.id);
        const indexToRemove = detuneOscillators.findIndex(osc => osc.id === idToRemove);

        if (indexToRemove > -1) {
            // Remove the detune oscillator
            detuneOscillators.splice(indexToRemove, 1);
            document.getElementById(`detune-osc-${idToRemove}`).remove();

            // If a corresponding FM oscillator exists, remove it too
            const fmOscToRemove = fmOscillators[indexToRemove];
            if (fmOscToRemove) {
                fmOscillators.splice(indexToRemove, 1);
                document.getElementById(`fm-osc-${fmOscToRemove.id}`).remove();
            }
        }
    });
}

function addFmOsc() {
    if (fmOscillators.length >= 16 || fmOscillators.length >= detuneOscillators.length) {
         console.warn("Add a corresponding Detune oscillator first.");
        return;
    }
    fmOscCounter++;
    const id = fmOscCounter;

    const oscDiv = document.createElement('div');
    oscDiv.classList.add('fm-osc-control');
    oscDiv.id = `fm-osc-${id}`;
    oscDiv.innerHTML = `
        <h4>FM Osc ${id} (for Detune ${id})</h4>
        <div class="control"><label>FM Amount</label><input type="range" min="0" max="1000" value="100" step="1" class="fm-osc-amount"></div>
        <button class="remove-fm-osc" data-id="${id}">X</button>
    `;
    fmOscsContainer.appendChild(oscDiv);

    const newFmState = {
        id: id,
        amount: oscDiv.querySelector('.fm-osc-amount'),
        element: oscDiv
    };
    fmOscillators.push(newFmState);

     oscDiv.querySelector('.remove-fm-osc').addEventListener('click', (e) => {
        const idToRemove = parseInt(e.target.dataset.id);
        const indexToRemove = fmOscillators.findIndex(osc => osc.id === idToRemove);
        if (indexToRemove > -1) {
            fmOscillators.splice(indexToRemove, 1);
            document.getElementById(`fm-osc-${idToRemove}`).remove();
        }
    });
}

addDetuneOscButton.addEventListener('click', addDetuneOsc);
addFmOscButton.addEventListener('click', addFmOsc);
