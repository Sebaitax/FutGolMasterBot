// Sonidos del partido, sintetizados con Web Audio (sin archivos de audio).
// FGM_SONIDO.silbato(n), .patada(), .gol(propio), .uy(), .ambiente(on), .activo / .alternar()
window.FGM_SONIDO = (() => {
  let ctx = null, maestro = null, ruido = null, fondo = null;
  let activo = true;
  try { activo = localStorage.getItem('fgm_sonido') !== '0'; } catch {}

  function iniciar() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return ctx; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    maestro = ctx.createGain(); maestro.gain.value = activo ? 0.8 : 0; maestro.connect(ctx.destination);
    // 2 s de ruido rosado aproximado, reutilizable (público, festejos)
    const largo = ctx.sampleRate * 2, buf = ctx.createBuffer(1, largo, ctx.sampleRate), d = buf.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < largo; i++) {
      const w = Math.random() * 2 - 1;
      b0 = 0.997 * b0 + w * 0.029; b1 = 0.985 * b1 + w * 0.032; b2 = 0.95 * b2 + w * 0.048;
      d[i] = (b0 + b1 + b2 + w * 0.02) * 2.2;
    }
    ruido = buf;
    return ctx;
  }
  // los navegadores (sobre todo en el celular) solo dejan sonar después de un toque
  ['pointerdown', 'keydown', 'touchstart'].forEach(ev => addEventListener(ev, iniciar, {passive: true}));

  const listo = () => activo && iniciar() && ctx.state === 'running';

  function fuenteRuido(frec, q, destino) {
    const s = ctx.createBufferSource(); s.buffer = ruido; s.loop = true;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = frec; f.Q.value = q;
    s.connect(f); f.connect(destino);
    return s;
  }

  function silbato(veces = 1, largo = 0.28) {
    if (!listo()) return;
    let t = ctx.currentTime + 0.02;
    for (let i = 0; i < veces; i++) {
      const dur = i === veces - 1 && veces > 1 ? largo * 2.2 : largo;
      const o = ctx.createOscillator(), g = ctx.createGain(), lfo = ctx.createOscillator(), lg = ctx.createGain();
      o.type = 'sine'; o.frequency.value = 2900;
      lfo.frequency.value = 38; lg.gain.value = 140;           // el "trino" de la bolita del silbato
      lfo.connect(lg); lg.connect(o.frequency);
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.16, t + 0.02);
      g.gain.setValueAtTime(0.16, t + dur - 0.04);
      g.gain.linearRampToValueAtTime(0, t + dur);
      o.connect(g); g.connect(maestro);
      o.start(t); lfo.start(t); o.stop(t + dur + 0.02); lfo.stop(t + dur + 0.02);
      t += dur + 0.12;
    }
  }

  let ultimaPatada = 0;
  function patada(fuerte = false) {
    if (!listo()) return;
    const ahora = ctx.currentTime;
    if (ahora - ultimaPatada < 0.12) return;
    ultimaPatada = ahora;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(fuerte ? 170 : 140, ahora);
    o.frequency.exponentialRampToValueAtTime(45, ahora + 0.12);
    g.gain.setValueAtTime(fuerte ? 0.5 : 0.22, ahora);
    g.gain.exponentialRampToValueAtTime(0.001, ahora + 0.14);
    o.connect(g); g.connect(maestro);
    o.start(ahora); o.stop(ahora + 0.16);
  }

  // el público: sube, se sostiene y baja
  function publico(pico, subida, sostiene, baja, frec = 900) {
    if (!listo()) return;
    const t = ctx.currentTime, g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(pico, t + subida);
    g.gain.setValueAtTime(pico, t + subida + sostiene);
    g.gain.exponentialRampToValueAtTime(0.0001, t + subida + sostiene + baja);
    g.connect(maestro);
    const fin = t + subida + sostiene + baja + 0.05;
    [fuenteRuido(frec, 0.6, g), fuenteRuido(frec * 2.4, 0.9, g)].forEach(s => { s.start(t, Math.random()); s.stop(fin); });
  }

  function gol(propio = true) {
    try { navigator.vibrate && navigator.vibrate(propio ? [120, 60, 120, 60, 260] : 200); } catch {}
    if (!listo()) return;
    patada(true);
    // bocina de estadio: ta-ta-taaa (la del rival más corta y grave)
    const notas = propio ? [[392, 0.05, 0.18], [392, 0.27, 0.18], [523, 0.49, 0.7]] : [[262, 0.05, 0.5]];
    for (const [f, t0, d] of notas) { tono(f, t0, d, {tipo: 'sawtooth', vol: 0.11}); tono(f * 1.5, t0, d, {tipo: 'square', vol: 0.04}); }
    publico(propio ? 0.9 : 0.45, 0.25, propio ? 2.2 : 1.0, 1.6, propio ? 1000 : 700);
    if (propio) setTimeout(() => publico(0.5, 0.3, 1.2, 1.5, 1400), 900);
  }
  const uy = () => publico(0.45, 0.15, 0.25, 0.9, 800);           // ocasión que no entra
  const abucheo = () => publico(0.3, 0.3, 0.6, 0.9, 380);         // tarjeta, falta fuerte

  // murmullo de fondo durante el partido
  function ambiente(on = true) {
    if (!on) {
      if (fondo) { const f = fondo; fondo = null; f.g.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.4); setTimeout(() => f.s.forEach(s => s.stop()), 1500); }
      return;
    }
    if (fondo || !listo()) return;
    const g = ctx.createGain(); g.gain.value = 0.0001; g.connect(maestro);
    const s = [fuenteRuido(600, 0.5, g), fuenteRuido(1500, 0.8, g)];
    s.forEach(x => x.start(0, Math.random()));
    g.gain.setTargetAtTime(0.09, ctx.currentTime, 0.8);
    fondo = {g, s};
  }

  // ---------- sobres
  function tono(frec, t0, dur, {tipo = 'triangle', vol = 0.18, hasta = null} = {}) {
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + t0;
    o.type = tipo; o.frequency.setValueAtTime(frec, t);
    if (hasta) o.frequency.exponentialRampToValueAtTime(hasta, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(maestro);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function soplo(t0, dur, desde, hasta, vol = 0.35, q = 1.2) {
    const t = ctx.currentTime + t0, s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = ruido; f.type = 'bandpass'; f.Q.value = q;
    f.frequency.setValueAtTime(desde, t); f.frequency.exponentialRampToValueAtTime(hasta, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + dur * 0.3);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f); f.connect(g); g.connect(maestro);
    s.start(t, Math.random()); s.stop(t + dur + 0.05);
  }
  const sobre = {
    agitar() { if (!listo()) return; [0, 0.12, 0.24].forEach(t => soplo(t, 0.09, 2500, 1800, 0.12, 3)); },
    rasgar() {                                   // papel que se rompe + "pop"
      if (!listo()) return;
      for (let i = 0; i < 6; i++) soplo(i * 0.045, 0.07, 4000 + Math.random() * 2000, 1500, 0.3, 2);
      tono(220, 0.3, 0.25, {tipo: 'sine', vol: 0.3, hasta: 80});
      soplo(0.3, 0.5, 600, 5000, 0.25);
    },
    voltear() { if (listo()) soplo(0, 0.18, 1200, 4000, 0.22, 1.5); },
    deslizar() { if (listo()) soplo(0, 0.25, 3000, 900, 0.15, 1); },
    // la carta dada vuelta: más brillo cuanto mejor la rareza
    revelar(nivel) {
      if (!listo()) return;
      if (nivel === 'oro') {
        [523, 659, 784, 1047].forEach((f, i) => tono(f, i * 0.09, 0.5, {vol: 0.16}));
        [1047, 1319, 1568].forEach(f => tono(f, 0.4, 1.2, {tipo: 'sine', vol: 0.08}));
        publico(0.5, 0.2, 0.8, 1.4, 1100);
      } else if (nivel === 'plata') {
        [659, 880].forEach((f, i) => tono(f, i * 0.1, 0.45, {vol: 0.14}));
        tono(1760, 0.2, 0.6, {tipo: 'sine', vol: 0.05});
      } else {
        tono(440, 0, 0.25, {vol: 0.12});
      }
    },
    final() { if (listo()) [392, 523, 659].forEach((f, i) => tono(f, i * 0.07, 0.35, {vol: 0.1})); },
  };

  function alternar() {
    activo = !activo;
    try { localStorage.setItem('fgm_sonido', activo ? '1' : '0'); } catch {}
    if (activo) iniciar();
    if (maestro) maestro.gain.setTargetAtTime(activo ? 0.8 : 0, ctx.currentTime, 0.05);
    return activo;
  }

  // true si el navegador todavía no deja sonar (falta tocar la pantalla)
  const bloqueado = () => activo && (!ctx || ctx.state !== 'running');
  return {bloqueado, silbato, patada, gol, uy, abucheo, ambiente, sobre, alternar, get activo() { return activo; }};
})();
