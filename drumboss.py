<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>DRUMBOSS — Velocity, Choke Groups, 8th Swing</title>
<style>
  :root{
    --bg:#ebe7df; --ink:#111; --dim:#666; --line:#000;
    --panel:#f5f2ea; --win:#e9e5dd; --hilite:#cde; --hilite2:#8ad;
  }
  html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
    font:14px/1.3 system-ui,sans-serif;}
  .desktop{padding:10px;}
  .window{background:var(--win);border:2px solid #000;
    box-shadow:inset -2px -2px 0 #555, inset 2px 2px 0 #fff; margin:8px 0;}
  .titlebar{background:linear-gradient(#d7d3cb,#cfcac2);border-bottom:2px solid #000;
    padding:6px 10px;display:flex;align-items:center;gap:8px;justify-content:space-between;}
  .title{font-weight:bold;}
  .content{padding:10px;}
  .toolbar,.top-controls{
    display:flex;flex-wrap:wrap;gap:10px;align-items:center;
    background:var(--panel);padding:8px;border:1px solid #000;
    box-shadow:inset 1px 1px 0 #fff,inset -1px -1px 0 #555;
  }
  label{display:inline-flex;align-items:center;gap:6px;}
  input[type="number"], select, button, input[type="range"]{
    border:1px solid #000;background:#fff;color:#000;padding:2px 4px;
    box-shadow:inset 1px 1px 0 #fff, inset -1px -1px 0 #555;font-size:12px;}
  button{cursor:pointer;}
  .grid-wrap{display:flex;gap:12px;margin-top:10px;}
  .track{min-width:220px;background:var(--panel);border:1px solid #000;
    box-shadow:inset 1px 1px 0 #fff, inset -1px -1px 0 #555;}
  .track-head{padding:6px;border-bottom:1px solid #000;background:#eae6de;
    display:flex;flex-direction:column;gap:6px;}
  .track-name{font-weight:bold;}
  .row{display:grid;grid-template-columns:28px 20px 1fr 36px;align-items:center;
    border-bottom:1px dashed #999;padding:2px 4px;gap:6px;}
  .row:last-child{border-bottom:none;}
  .row .idx{font-size:11px;color:var(--dim);text-align:right;}
  .cell{height:18px;display:flex;align-items:center;}
  .vel{width:100%; height:16px;}
  .row.playing{background:var(--hilite);}
  .small{font-size:12px;color:var(--dim);}
  .footer{margin-top:8px;font-size:12px;color:var(--dim);}
  .top-controls{margin:8px 0;overflow:auto;}
  .strip{display:flex;gap:8px;overflow-x:auto;padding:2px;}
  .card{
    min-width:310px;background:#f7f4ec;border:1px solid #000;
    box-shadow:inset 1px 1px 0 #fff, inset -1px -1px 0 #555; padding:6px;
  }
  .card .name{font-weight:bold;margin-bottom:4px;}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
  .grid2 label{justify-content:space-between;}
  input[type="range"].wide{width:140px;}
</style>
</head>
<body>
<div class="desktop">
  <div class="window">
    <div class="titlebar">
      <div class="title">DRUMBOSS — Polyrhythmic Retro Tracker</div>
      <div class="small">Velocity • Choke Groups • 8th Swing</div>
    </div>
    <div class="content">
      <!-- Global transport and swing -->
      <div class="toolbar">
        <label>BPM <input id="bpm" type="number" min="40" max="300" value="120"></label>
        <label style="gap:4px;">Swing (8th)
          <input id="swing8" type="range" min="50" max="75" step="0.1" value="50" class="wide">
          <span id="swingVal" class="small">50% (50/50)</span>
        </label>
        <button id="play">Play</button>
        <button id="pause">Pause</button>
        <button id="restart">Restart</button>
        <span class="small">Первая/вторая 16‑я в паре суммарно = 100%.</span>
      </div>

      <!-- Per-track quick controls on top -->
      <div class="top-controls">
        <div id="topStrip" class="strip"></div>
      </div>

      <!-- Pattern grid -->
      <div id="grid" class="grid-wrap"></div>

      <div class="footer">Velocity задаёт акцент шага. Внутри одной choke‑группы звучит только один голос; новый «глушит» предыдущий.</div>
    </div>
  </div>
</div>

<script>
(() => {
  // Audio context and scheduler
  let audioCtx = null;
  let isPlaying = false;
  let lookahead = 0.1;      // seconds
  let tickInterval = 25;    // ms
  let timerID = null;

  // Swing (8th share: 50–75%)
  let swingPerc = 50;

  const chokeWindow = 0.02; // сек, окно «одновременности» для конфликтов в группе
  const activeByGroup = new Map(); // group -> [voices]

  // 16th duration
  const getStepDur = () => 60 / parseFloat(bpmInput.value) / 4;

  // Utility: white noise buffer
  function createNoiseBuffer(ctx, lengthSec=2){
    const length = Math.floor(ctx.sampleRate * lengthSec);
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i=0;i<length;i++) data[i] = Math.random()*2-1;
    return buffer;
  }

  // Tracks definition
  const defaultTracks = [
    { name:'Closed Hat', type:'hatC', chokeGroup:1 },
    { name:'Open Hat',   type:'hatO', chokeGroup:1 },
    { name:'Bell',       type:'bell', chokeGroup:0 },
    { name:'Snare',      type:'snare',chokeGroup:0 },
    { name:'Kick 1',     type:'kick', chokeGroup:0, kickTier:'Mid' },
    { name:'Kick 2',     type:'kick', chokeGroup:0, kickTier:'Low' },
  ];

  // App state per track
  const tracks = defaultTracks.map((t,i)=>({
    id:i,
    name:t.name,
    type:t.type,
    enabled:true,
    patternLen:16,
    loopMode:'forward',
    direction:1,
    stepIndex:0,
    nextTime:0,
    swingFirst:true, // первая 16‑я в паре
    // Pattern: velocity per step (0..1). 0 = off
    pattern:Array(32).fill(0),
    // Instrument params + channel params + choke group
    params: instrumentDefaults(t)
  }));

  // Lazy noise buffer
  let noiseBuffer = null;

  function instrumentDefaults(t){
    const generic = {
      // top controls
      pitchSemis: 0,
      cutoff: 20000, resonance: 0.7,
      fmDepthG: 0, fmRateG: 0, fmFeedback: 0,
      rmAmt: 0, rmRate: 30,
      chokeGroup: t.chokeGroup ?? 0
    };
    switch(t.type){
      case 'hatC': return Object.assign(generic, { decay:0.06, bpFreq:9000, bpQ:1.0, hpFreq:5000, tone:0.7 });
      case 'hatO': return Object.assign(generic, { decay:0.35, bpFreq:8000, bpQ:0.7, hpFreq:4000, tone:0.6 });
      case 'bell': return Object.assign(generic, { freq:600, ratio:2, modIndex:600, decay:3.5, maxLen:6.0 });
      case 'snare':return Object.assign(generic, { bodyFreq:180, bodyDecay:0.18, noiseLen:0.22,
                            bpFreq:2600, bpQ:1.0, hpFreq:1200,
                            filtEnvAmt:2200, filtEnvTime:0.06,
                            fmDepth:40, fmRate:120,
                            ringNoiseAmt:0.25 });
      case 'kick':
        return Object.assign(generic, { tier:(t.kickTier||'Mid'), startFreq:140, endFreq:48, decay:0.18,
                 fmDepth:60, fmRate:200, click:0.008, gain:0.9 });
      default: return generic;
    }
  }

  // Build UI refs
  const grid = document.getElementById('grid');
  const topStrip = document.getElementById('topStrip');
  const bpmInput = document.getElementById('bpm');
  const swingInput = document.getElementById('swing8');
  const swingVal = document.getElementById('swingVal');
  const playBtn = document.getElementById('play');
  const pauseBtn = document.getElementById('pause');
  const restartBtn = document.getElementById('restart');

  function updateSwingLabel(){
    const s = parseFloat(swingInput.value);
    swingPerc = s;
    const first = Math.round(s);
    const second = 100 - first;
    swingVal.textContent = `${first}% (${first}/${second})`;
  }
  swingInput.addEventListener('input', updateSwingLabel);
  updateSwingLabel();

  // Build top per-track quick controls (+ choke group)
  function buildTopCard(track){
    const card = document.createElement('div');
    card.className = 'card';
    const name = document.createElement('div'); name.className='name'; name.textContent = track.name;
    card.appendChild(name);
    const grid2 = document.createElement('div'); grid2.className = 'grid2';

    const addNum = (label, key, min, max, step, unit, conv=val=>val) => {
      const wrap = document.createElement('label'); wrap.textContent = label;
      const input = document.createElement('input'); input.type='number';
      input.min=min; input.max=max; input.step=step; input.value=track.params[key];
      input.style.width='70px';
      input.addEventListener('input', ()=> track.params[key]=conv(parseFloat(input.value)));
      wrap.appendChild(input);
      if (unit){ const u = document.createElement('span'); u.textContent = unit; wrap.appendChild(u); }
      grid2.appendChild(wrap);
      return input;
    };
    const addRange = (label, key, min, max, step, wide=false) => {
      const wrap = document.createElement('label'); wrap.textContent=label;
      const rng=document.createElement('input'); rng.type='range';
      rng.min=min; rng.max=max; rng.step=step; rng.value=track.params[key];
      if (wide) rng.classList.add('wide');
      rng.addEventListener('input', ()=> track.params[key]=parseFloat(rng.value));
      wrap.appendChild(rng); grid2.appendChild(wrap); return rng;
    };

    addNum('Pitch','pitchSemis',-24,24,1,'st');
    addNum('Cutoff','cutoff',200,20000,10,'Hz');
    addNum('Resonance','resonance',0.1,12,0.1,'Q');
    addNum('FM Depth','fmDepthG',0,800,1,'');
    addNum('FM Rate','fmRateG',0,2000,1,'Hz');
    addNum('FM Feedback','fmFeedback',0,800,1,'');
    addRange('Ring Amt','rmAmt',0,1,0.01,true);
    addNum('Ring Rate','rmRate',0.1,2000,0.1,'Hz');

    // Choke group 0..5
    const chokeWrap = document.createElement('label'); chokeWrap.textContent='Choke grp';
    const sel = document.createElement('select');
    [['0','None'],['1','1'],['2','2'],['3','3'],['4','4'],['5','5']].forEach(([v,t])=>{
      const opt=document.createElement('option'); opt.value=v; opt.textContent=t; sel.appendChild(opt);
    });
    sel.value = String(track.params.chokeGroup||0);
    sel.addEventListener('change', ()=> track.params.chokeGroup = parseInt(sel.value,10));
    chokeWrap.appendChild(sel); grid2.appendChild(chokeWrap);

    card.appendChild(grid2);
    return card;
  }

  tracks.forEach(t => topStrip.appendChild(buildTopCard(t)));

  // Build per-track pattern UI (velocity per step)
  function buildTrackUI(track){
    const el = document.createElement('div');
    el.className = 'track'; el.dataset.track = track.id;

    const head = document.createElement('div'); head.className = 'track-head';
    const title = document.createElement('div'); title.className = 'track-name'; title.textContent = track.name;
    head.appendChild(title);

    const ctlRow = document.createElement('div');
    ctlRow.style.display='flex'; ctlRow.style.gap='8px'; ctlRow.style.flexWrap='wrap';

    const lenLabel = document.createElement('label'); lenLabel.textContent = 'Len';
    const lenSel = document.createElement('select');
    for (let i=1;i<=32;i++){
      const opt = document.createElement('option'); opt.value=String(i); opt.textContent=String(i);
      if (i===track.patternLen) opt.selected=true; lenSel.appendChild(opt);
    }
    lenSel.addEventListener('change', () => {
      track.patternLen = parseInt(lenSel.value,10);
      if (track.stepIndex >= track.patternLen) track.stepIndex = 0;
      renderHighlight();
      updateDisabled();
    });
    lenLabel.appendChild(lenSel); ctlRow.appendChild(lenLabel);

    const loopLabel = document.createElement('label'); loopLabel.textContent = 'Loop';
    const loopSel = document.createElement('select');
    ['forward','pingpong'].forEach(m=>{ const opt=document.createElement('option');
      opt.value=m; opt.textContent=(m==='forward'?'Forward':'Ping‑Pong'); loopSel.appendChild(opt); });
    loopSel.value = track.loopMode;
    loopSel.addEventListener('change', ()=> track.loopMode = loopSel.value);
    loopLabel.appendChild(loopSel); ctlRow.appendChild(loopLabel);

    head.appendChild(ctlRow);
    el.appendChild(head);

    for (let r=0;r<32;r++){
      const row = document.createElement('div'); row.className='row'; row.dataset.row=r;
      const idx = document.createElement('div'); idx.className='idx'; idx.textContent=(r+1).toString().padStart(2,'0');
      const cellOn = document.createElement('div'); cellOn.className='cell';
      const cb = document.createElement('input'); cb.type='checkbox'; cb.checked = (track.pattern[r] > 0);
      cellOn.appendChild(cb);

      const velCell = document.createElement('div'); velCell.className='cell';
      const rng = document.createElement('input'); rng.type='range'; rng.min='0'; rng.max='1'; rng.step='0.01';
      rng.value = track.pattern[r] || 0;
      rng.className='vel';
      if (!cb.checked) rng.disabled = true;
      velCell.appendChild(rng);

      const velNum = document.createElement('div'); velNum.className='cell small';
      const lbl = document.createElement('span');
      lbl.textContent = Math.round((track.pattern[r]||0)*100).toString();
      velNum.appendChild(lbl);

      cb.addEventListener('change', ()=>{
        if (cb.checked){
          if (track.pattern[r] <= 0) { track.pattern[r] = 0.8; rng.value = 0.8; lbl.textContent='80'; }
          rng.disabled = false;
        } else {
          track.pattern[r] = 0; rng.value = 0; rng.disabled = true; lbl.textContent='0';
        }
      });
      rng.addEventListener('input', ()=>{
        const v = parseFloat(rng.value);
        track.pattern[r] = v;
        lbl.textContent = Math.round(v*100).toString();
        cb.checked = v > 0;
        if (v === 0) rng.disabled = true;
      });

      row.appendChild(idx); row.appendChild(cellOn); row.appendChild(velCell); row.appendChild(velNum);
      el.appendChild(row);
    }

    function updateDisabled(){
      const rows = el.querySelectorAll('.row');
      rows.forEach((row,idx)=>{
        const cb = row.querySelector('input[type="checkbox"]');
        const rng = row.querySelector('input[type="range"]');
        const dis = (idx>=track.patternLen);
        cb.disabled = dis;
        rng.disabled = dis || !(track.pattern[idx] > 0);
      });
    }
    updateDisabled();

    return el;
  }

  tracks.forEach(t => grid.appendChild(buildTrackUI(t)));

  // Highlight logic
  function renderHighlight(){
    tracks.forEach(track=>{
      const el = grid.querySelector(`.track[data-track="${track.id}"]`);
      if (!el) return;
      const rows = el.querySelectorAll('.row');
      rows.forEach((row,idx)=>{
        if (idx === track.stepIndex && idx < track.patternLen) row.classList.add('playing');
        else row.classList.remove('playing');
        const cb = row.querySelector('input[type="checkbox"]');
        const rng = row.querySelector('input[type="range"]');
        const dis = (idx>=track.patternLen);
        if (cb) cb.disabled = dis;
        if (rng) rng.disabled = dis || !(track.pattern[idx] > 0);
      });
    });
  }

  // Transport
  playBtn.addEventListener('click', async ()=>{
    if (!audioCtx){
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      noiseBuffer = createNoiseBuffer(audioCtx, 2.0);
    }
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    if (isPlaying) return;
    const now = audioCtx.currentTime + 0.05;
    tracks.forEach(t=>{
      t.stepIndex = 0; t.direction = 1; t.nextTime = now; t.swingFirst=true;
    });
    isPlaying = true;
    scheduler();
    timerID = setInterval(scheduler, tickInterval);
    rafLoop();
  });

  pauseBtn.addEventListener('click', async ()=>{
    if (!audioCtx) return;
    await audioCtx.suspend();
    isPlaying = false;
    if (timerID) clearInterval(timerID);
    timerID = null;
  });

  restartBtn.addEventListener('click', ()=>{
    if (!audioCtx) return;
    const now = audioCtx.currentTime + 0.05;
    tracks.forEach(t=>{
      t.stepIndex = 0; t.direction = 1; t.nextTime = now; t.swingFirst=true;
    });
    renderHighlight();
  });

  // Scheduler with look-ahead + 8th swing + choke resolution
  function scheduler(){
    if (!audioCtx) return;
    const baseStep = getStepDur();
    const now = audioCtx.currentTime;
    const horizon = now + lookahead;

    // Collect events first
    const events = []; // {when, track, vel, group}
    tracks.forEach(track=>{
      while (track.nextTime <= horizon){
        const idx = track.stepIndex;
        if (idx < track.patternLen){
          const vel = Math.max(0, Math.min(1, track.pattern[idx]||0));
          if (vel > 0){
            events.push({ when: track.nextTime, track, vel, group: track.params.chokeGroup||0 });
          }
        }
        advanceStep(track);
        // 8th swing: pair of 16ths sums to 2*baseStep
        let inc = baseStep;
        if (swingPerc !== 50){
          if (track.swingFirst){
            inc = baseStep * (swingPerc/50); // first of pair
          } else {
            inc = baseStep * ((100 - swingPerc)/50); // second of pair
          }
          track.swingFirst = !track.swingFirst;
        }
        track.nextTime += inc;
      }
    });

    if (events.length === 0) return;

    // Sort by time, then by velocity desc (so при конфликте первым идёт сильнейший)
    events.sort((a,b)=> (a.when===b.when ? (b.vel - a.vel) : (a.when - b.when)));

    // Choke conflict resolution within time window
    const accepted = [];
    const lastByGroup = new Map(); // group -> {when, vel, idxInAccepted}
    events.forEach(e=>{
      const g = e.group|0;
      if (g===0){
        accepted.push(e);
        return;
      }
      const last = lastByGroup.get(g);
      if (!last || Math.abs(e.when - last.when) >= chokeWindow){
        accepted.push(e);
        lastByGroup.set(g, {when:e.when, vel:e.vel, idxInAccepted:accepted.length-1});
      } else {
        // Conflict: keep the higher-velocity one
        if (e.vel > last.vel + 1e-6){
          // Replace previous accepted event
          accepted[last.idxInAccepted] = e;
          lastByGroup.set(g, {when:e.when, vel:e.vel, idxInAccepted:last.idxInAccepted});
        } // else drop current
      }
    });

    // Schedule accepted events with real-time choke of active tails
    accepted.forEach(e=>{
      if (e.group>0) chokeActive(e.group, e.when);
      const voice = trigger(e.track, e.when, e.vel);
      if (e.group>0 && voice){
        voice.group = e.group;
        let arr = activeByGroup.get(e.group) || [];
        arr.push(voice);
        activeByGroup.set(e.group, arr);
      }
    });
  }

  function advanceStep(track){
    if (track.loopMode === 'forward'){
      track.stepIndex = (track.stepIndex + 1) % track.patternLen;
      if (swingPerc === 50) track.swingFirst = !track.swingFirst;
    } else {
      let next = track.stepIndex + track.direction;
      if (next >= track.patternLen){ track.direction = -1; next = track.patternLen-2; }
      if (next < 0){ track.direction = 1; next = 1; }
      track.stepIndex = Math.max(0, Math.min(track.patternLen-1, next));
      if (swingPerc === 50) track.swingFirst = !track.swingFirst;
    }
  }

  function rafLoop(){
    if (!isPlaying && (!audioCtx || audioCtx.state!=='running')) return;
    renderHighlight();
    requestAnimationFrame(rafLoop);
  }

  // Stop all active voices in group
  function chokeActive(group, when){
    const arr = activeByGroup.get(group) || [];
    const still = [];
    arr.forEach(v=>{
      if (v.stopAt > when){
        v.stop(when);
        // не возвращаем в still — голос завершён
      }
    });
    activeByGroup.set(group, still);
  }

  // Create a voice gate and stopper
  function createVoiceGate(when, stopAt){
    const gate = audioCtx.createGain();
    gate.gain.setValueAtTime(1, when);
    const voice = {
      gate, stopAt,
      stop: (t)=> {
        const tt = Math.max(t, audioCtx.currentTime);
        try{
          gate.gain.cancelScheduledValues(tt);
          gate.gain.setValueAtTime(gate.gain.value, tt);
          gate.gain.exponentialRampToValueAtTime(0.0001, tt + 0.015);
        }catch(e){}
      }
    };
    return voice;
  }

  // Trigger router: returns voice object (with gate + stopAt) for choke
  function trigger(track, when, velocity=1){
    switch(track.type){
      case 'hatC': return playHat(track, when, false, velocity);
      case 'hatO': return playHat(track, when, true,  velocity);
      case 'bell': return playBell(track, when, velocity);
      case 'snare':return playSnare(track, when, velocity);
      case 'kick': return playKick(track, when, velocity);
    }
  }

  // Channel FX: post lowpass + optional ring mod to out gain
  function channelFX(track, when, stopAt){
    const p = track.params;
    const lpf = audioCtx.createBiquadFilter();
    lpf.type='lowpass';
    lpf.frequency.setValueAtTime(Math.max(50, p.cutoff||20000), when);
    lpf.Q.setValueAtTime(Math.max(0.1, p.resonance||0.7), when);

    const out = audioCtx.createGain();
    out.gain.setValueAtTime(1, when);

    // Ring modulation on final gain
    const amt = Math.max(0, Math.min(1, p.rmAmt||0));
    if (amt > 0){
      const ring = audioCtx.createOscillator(); ring.type='sine';
      ring.frequency.setValueAtTime(Math.max(0.1, p.rmRate||30), when);
      const modGain = audioCtx.createGain(); modGain.gain.setValueAtTime(amt, when);
      const bias = audioCtx.createConstantSource(); bias.offset.setValueAtTime(1 - amt, when);
      ring.connect(modGain).connect(out.gain);
      bias.connect(out.gain);
      ring.start(when); bias.start(when);
      ring.stop(stopAt); bias.stop(stopAt);
    }

    lpf.connect(out).connect(audioCtx.destination);
    return { in:lpf, out };
  }

  function pitchMul(track){
    const semis = track.params.pitchSemis||0;
    return Math.pow(2, semis/12);
  }

  function effectiveFM(track, fallbackDepth=0, fallbackRate=0){
    const p = track.params;
    const depth = (p.fmDepthG && p.fmDepthG>0) ? p.fmDepthG : (p.fmDepth || fallbackDepth);
    const rate  = (p.fmRateG  && p.fmRateG>0)  ? p.fmRateG  : (p.fmRate  || fallbackRate);
    const feedback = p.fmFeedback || 0;
    return {depth, rate, feedback};
  }

  function playHat(track, when, isOpen, vel){
    const p = track.params;
    const bus = audioCtx.createGain();

    const src = audioCtx.createBufferSource();
    src.buffer = noiseBuffer;

    const bp = audioCtx.createBiquadFilter(); bp.type='bandpass'; bp.frequency.value=p.bpFreq; bp.Q.value=p.bpQ;
    const hp = audioCtx.createBiquadFilter(); hp.type='highpass'; hp.frequency.value=p.hpFreq; hp.Q.value=0.707;

    const amp = audioCtx.createGain();
    const decay = Math.max(0.01, p.decay);
    amp.gain.setValueAtTime(0.0001, when);
    amp.gain.linearRampToValueAtTime(0.9*p.tone*vel, when + 0.001);
    amp.gain.exponentialRampToValueAtTime(0.0001, when + decay);

    src.connect(bp).connect(hp).connect(amp).connect(bus);

    const stopAt = when + decay + 0.1;
    const fx = channelFX(track, when, stopAt);
    const voice = createVoiceGate(when, stopAt);
    bus.connect(voice.gate).connect(fx.in);

    src.start(when); src.stop(stopAt);

    return voice;
  }

  function playBell(track, when, vel){
    const p = track.params;
    const mul = pitchMul(track);
    const dur = Math.min(p.decay, 6.0);
    const bus = audioCtx.createGain();

    const car = audioCtx.createOscillator();
    const mod = audioCtx.createOscillator();
    const modGain = audioCtx.createGain();

    car.type='sine';
    car.frequency.setValueAtTime(p.freq*mul, when);

    const {depth, rate, feedback} = effectiveFM(track, p.modIndex, p.freq * p.ratio);
    mod.type='sine';
    const modFreq = (p.freq*mul) * p.ratio;
    mod.frequency.setValueAtTime(rate>0 ? rate : modFreq, when);
    modGain.gain.setValueAtTime(depth>0 ? depth : p.modIndex, when);
    modGain.gain.exponentialRampToValueAtTime(1.0, when + dur);

    if (feedback>0){
      const fb = audioCtx.createGain(); fb.gain.setValueAtTime(feedback, when);
      mod.connect(fb).connect(mod.frequency);
    }

    const out = audioCtx.createGain();
    out.gain.setValueAtTime(0.0001, when);
    out.gain.linearRampToValueAtTime(0.8*vel, when + 0.005);
    out.gain.exponentialRampToValueAtTime(0.0001, when + dur);

    mod.connect(modGain).connect(car.frequency);
    car.connect(out).connect(bus);

    const stopAt = when + dur + 0.05;
    const fx = channelFX(track, when, stopAt);
    const voice = createVoiceGate(when, stopAt);
    bus.connect(voice.gate).connect(fx.in);

    car.start(when); mod.start(when);
    car.stop(stopAt); mod.stop(stopAt);

    return voice;
  }

  function playSnare(track, when, vel){
    const p = track.params;
    const mul = pitchMul(track);
    const bus = audioCtx.createGain();

    const body = audioCtx.createOscillator();
    body.type='triangle';
    body.frequency.setValueAtTime(p.bodyFreq*mul, when);

    const fm = audioCtx.createOscillator();
    const fmGain = audioCtx.createGain();
    const eff = effectiveFM(track, p.fmDepth, p.fmRate);
    fm.type = 'sine';
    fm.frequency.setValueAtTime(Math.max(1, eff.rate), when);
    fmGain.gain.setValueAtTime(Math.max(0, eff.depth), when);
    fm.connect(fmGain).connect(body.frequency);
    if (eff.feedback>0){
      const fb = audioCtx.createGain(); fb.gain.setValueAtTime(eff.feedback, when);
      fm.connect(fb).connect(fm.frequency);
    }

    const ringNoise = audioCtx.createBufferSource(); ringNoise.buffer = noiseBuffer;
    const ringGain = audioCtx.createGain(); ringGain.gain.setValueAtTime(p.ringNoiseAmt*vel, when);
    const bodyAmp = audioCtx.createGain();
    bodyAmp.gain.setValueAtTime(0.0001, when);
    bodyAmp.gain.linearRampToValueAtTime(0.8*vel, when + 0.002);
    bodyAmp.gain.exponentialRampToValueAtTime(0.0001, when + p.bodyDecay);
    const bias = audioCtx.createConstantSource(); bias.offset.setValueAtTime(0.7, when);
    bias.connect(bodyAmp.gain);
    ringNoise.connect(ringGain).connect(bodyAmp.gain);

    const ns = audioCtx.createBufferSource(); ns.buffer = noiseBuffer;
    const bp = audioCtx.createBiquadFilter(); bp.type='bandpass'; bp.frequency.setValueAtTime(p.bpFreq, when); bp.Q.value=p.bpQ;
    const hp = audioCtx.createBiquadFilter(); hp.type='highpass'; hp.frequency.setValueAtTime(p.hpFreq, when); hp.Q.value=0.707;
    const nsGain = audioCtx.createGain();
    nsGain.gain.setValueAtTime(0.0001, when);
    nsGain.gain.linearRampToValueAtTime(0.9*vel, when + 0.001);
    nsGain.gain.exponentialRampToValueAtTime(0.0001, when + p.noiseLen);
    bp.frequency.cancelScheduledValues(when);
    bp.frequency.setValueAtTime(p.bpFreq, when);
    bp.frequency.linearRampToValueAtTime(p.bpFreq + p.filtEnvAmt, when + p.filtEnvTime);

    body.connect(bodyAmp).connect(bus);
    ns.connect(bp).connect(hp).connect(nsGain).connect(bus);

    const stopAt = when + Math.max(p.bodyDecay, p.noiseLen) + 0.1;
    const fx = channelFX(track, when, stopAt);
    const voice = createVoiceGate(when, stopAt);
    bus.connect(voice.gate).connect(fx.in);

    body.start(when); fm.start(when); bias.start(when); ringNoise.start(when);
    body.stop(stopAt); fm.stop(stopAt); bias.stop(stopAt); ringNoise.stop(stopAt);
    ns.start(when); ns.stop(stopAt);

    return voice;
  }

  function playKick(track, when, vel){
    const p = track.params;
    const mul = pitchMul(track);
    const bus = audioCtx.createGain();

    const osc = audioCtx.createOscillator(); osc.type='sine';
    const amp = audioCtx.createGain();
    const out = audioCtx.createGain(); out.gain.value = p.gain * vel;

    const startF = p.startFreq*mul, endF = p.endFreq*mul, decay = p.decay;
    osc.frequency.setValueAtTime(Math.max(20, startF), when);
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, endF), when + decay);

    const eff = effectiveFM(track, p.fmDepth, p.fmRate);
    const fm = audioCtx.createOscillator(); fm.type='sine';
    fm.frequency.setValueAtTime(Math.max(1, eff.rate), when);
    const fmGain = audioCtx.createGain();
    fmGain.gain.setValueAtTime(Math.max(0, eff.depth), when);
    fmGain.gain.exponentialRampToValueAtTime(1.0, when + 0.08);
    fm.connect(fmGain).connect(osc.frequency);
    if (eff.feedback>0){
      const fb = audioCtx.createGain(); fb.gain.setValueAtTime(eff.feedback, when);
      fm.connect(fb).connect(fm.frequency);
    }

    amp.gain.setValueAtTime(0.0001, when);
    amp.gain.linearRampToValueAtTime(1.0, when + 0.002);
    amp.gain.exponentialRampToValueAtTime(0.0001, when + Math.max(0.08, decay));

    if (p.click > 0){
      const click = audioCtx.createBufferSource(); click.buffer = noiseBuffer;
      const hp = audioCtx.createBiquadFilter(); hp.type='highpass'; hp.frequency.value=3000;
      const cGain = audioCtx.createGain();
      cGain.gain.setValueAtTime(0.5*vel, when);
      cGain.gain.exponentialRampToValueAtTime(0.0001, when + p.click);
      click.connect(hp).connect(cGain).connect(bus);
      click.start(when); click.stop(when + p.click + 0.02);
    }

    osc.connect(amp).connect(out).connect(bus);

    const stopAt = when + Math.max(0.25, decay) + 0.05;
    const fx = channelFX(track, when, stopAt);
    const voice = createVoiceGate(when, stopAt);
    bus.connect(voice.gate).connect(fx.in);

    osc.start(when); fm.start(when);
    osc.stop(stopAt); fm.stop(stopAt);

    return voice;
  }

  // Resume on visibility regain (mobile Safari)
  document.addEventListener('visibilitychange', async ()=>{
    if (audioCtx && document.visibilityState==='visible' && audioCtx.state==='suspended'){
      await audioCtx.resume();
    }
  });

})();
</script>
</body>
</html>
