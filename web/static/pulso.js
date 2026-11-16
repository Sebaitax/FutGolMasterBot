// El pulso: una barra al medio que parte según los atributos del duelo y se empuja ronda a ronda.
// Cada jugada tiene su gesto (apuntar, buscar al compañero, secuencia de gambeta, reflejos…) y
// todos devuelven una precisión de 0 a 1. Lo usan el partido contra la máquina y el en vivo.
window.FGM_PULSO = (() => {
  const esc = s => FGM.esc(s);
  const S = window.FGM_SONIDO;
  const espera = ms => new Promise(r => setTimeout(r, ms));   // pausas reales (no dependen de la velocidad)
  const limitar = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));

  // cierre común de un gesto: texto de calificación, sonido y aviso con la precisión
  function calificar(cont, prec, alListo, estado, texto) {
    const [txt, cls] = texto ? [texto, prec >= 0.65 ? 'ok' : prec >= 0.35 ? 'medio' : 'mal']
      : prec >= 0.9 ? ['¡Perfecto!', 'ok'] : prec >= 0.65 ? ['¡Bien!', 'ok'] : prec >= 0.35 ? ['Justo…', 'medio'] : ['¡Mal!', 'mal'];
    cont.querySelector('.g-caja').insertAdjacentHTML('beforeend', `<p class="bt-res ${cls}">${txt}</p>`);
    if (prec >= 0.9) S.patada(true);
    setTimeout(() => { if (!estado.anulado) alListo(Math.round(prec * 100) / 100); }, 450);
  }
  // teclado para todos los gestos
  function teclas(estado, fn) {
    const h = e => { if (estado.hecho) return; if (fn(e) !== false) e.preventDefault(); };
    document.addEventListener('keydown', h);
    estado.limpiar.push(() => document.removeEventListener('keydown', h));
  }
  function nuevoEstado() {
    const e = {hecho: false, anulado: false, limpiar: []};
    e.fin = () => { e.hecho = true; e.limpiar.forEach(f => f()); };
    e.cancelar = () => { e.anulado = true; if (!e.hecho) e.fin(); };
    return e;
  }

  // --- barra: la aguja va y viene; tócala en el verde (opts.vel: más rápida para la barrida)
  function barraTiempo(cont, zona, alListo, limite = 4, opts = {}) {
    const ancho = limitar(zona || 0.12, 0.07, 0.28);
    const centro = ancho / 2 + 0.08 + Math.random() * (0.84 - ancho);
    cont.innerHTML = `<div class="g-caja bt">
        <p class="g-ayuda">${opts.ayuda || 'Toca cuando la aguja pase por el verde'}</p>
        <div class="bt-pista"><i class="bt-zona" style="left:${(centro - ancho / 2) * 100}%;width:${ancho * 100}%"><b></b></i><i class="bt-aguja"></i></div>
        <button class="primario bt-ya">¡Ahora!</button></div>`;
    const aguja = cont.querySelector('.bt-aguja'), st = nuevoEstado();
    const vel = (opts.vel || 1.25) * (0.95 + Math.random() * 0.25);
    const t0 = performance.now();
    let pos = 0, raf;
    const mover = ahora => {
      if (st.hecho) return;
      const f = ((ahora - t0) / 1000 * vel) % 2;
      pos = f < 1 ? f : 2 - f;
      aguja.style.left = (pos * 100) + '%';
      if ((ahora - t0) / 1000 > limite) return parar(true);
      raf = requestAnimationFrame(mover);
    };
    raf = requestAnimationFrame(mover);
    st.limpiar.push(() => cancelAnimationFrame(raf));
    function parar(tarde = false) {
      if (st.hecho) return;
      st.fin();
      const d = Math.abs(pos - centro), m = ancho / 2;
      const prec = tarde ? 0.1 : d <= m ? 1 - 0.3 * (d / m) : Math.max(0, 0.7 * (1 - (d - m) / 0.3));
      cont.querySelector('.bt-ya').disabled = true;
      calificar(cont, prec, alListo, st, tarde ? '¡Tarde!' : null);
    }
    teclas(st, e => (e.code === 'Space' || e.key === 'Enter') ? parar() : false);
    cont.querySelector('.bt-ya').onclick = () => parar();
    cont.querySelector('.bt-pista').onclick = () => parar();
    return st.cancelar;
  }

  // --- apuntar: la mira se mueve por el arco; tócala cuando esté sobre el objetivo
  function apuntar(cont, zona, alListo, limite = 4.5) {
    const r = 0.06 + limitar(zona || 0.12, 0.07, 0.28) * 0.45;           // radio del objetivo (fracción del ancho)
    const esquinas = [[0.12, 0.25], [0.88, 0.25], [0.12, 0.72], [0.88, 0.72], [0.5, 0.22]];
    const [ox, oy] = esquinas[Math.floor(Math.random() * esquinas.length)];
    cont.innerHTML = `<div class="g-caja">
        <p class="g-ayuda">🎯 Toca cuando la mira esté sobre el objetivo</p>
        <div class="g-arco"><i class="g-obj" style="left:${ox * 100}%;top:${oy * 100}%;width:${r * 200}%;"></i><i class="g-mira">+</i></div>
        <button class="primario bt-ya">¡Patea!</button></div>`;
    const mira = cont.querySelector('.g-mira'), st = nuevoEstado();
    const fx = 0.9 + Math.random() * 0.5, fy = 1.3 + Math.random() * 0.6, fase = Math.random() * 6;
    const t0 = performance.now();
    let x = 0.5, y = 0.5, raf;
    const mover = ahora => {
      if (st.hecho) return;
      const t = (ahora - t0) / 1000;
      x = 0.5 + 0.44 * Math.sin(t * fx * Math.PI + fase);
      y = 0.5 + 0.36 * Math.sin(t * fy * Math.PI);
      mira.style.left = (x * 100) + '%'; mira.style.top = (y * 100) + '%';
      if (t > limite) return parar(true);
      raf = requestAnimationFrame(mover);
    };
    raf = requestAnimationFrame(mover);
    st.limpiar.push(() => cancelAnimationFrame(raf));
    function parar(tarde = false) {
      if (st.hecho) return;
      st.fin();
      // el arco es 2:1 (ancho:alto): la distancia vertical cuenta la mitad
      const d = Math.hypot(x - ox, (y - oy) / 2);
      const prec = tarde ? 0.1 : d <= r ? 1 - 0.3 * (d / r) : Math.max(0, 0.7 * (1 - (d - r) / 0.25));
      cont.querySelector('.bt-ya').disabled = true;
      calificar(cont, prec, alListo, st, tarde ? '¡Tarde!' : null);
    }
    teclas(st, e => (e.code === 'Space' || e.key === 'Enter') ? parar() : false);
    cont.querySelector('.bt-ya').onclick = () => parar();
    cont.querySelector('.g-arco').onclick = () => parar();
    return st.cancelar;
  }

  // --- compañero: se van desmarcando; toca al que queda libre (verde) antes de que lo tapen
  function companero(cont, zona, alListo, limite = 5) {
    const ventana = 420 + limitar(zona || 0.12, 0.07, 0.28) * 1600;   // ms que queda libre
    cont.innerHTML = `<div class="g-caja">
        <p class="g-ayuda">🤝 Toca al compañero cuando quede libre (verde)</p>
        <div class="g-companeros">${[0, 1, 2, 3].map(i => `<button class="g-comp" data-i="${i}">${i + 1}</button>`).join('')}</div></div>`;
    const st = nuevoEstado(), botones = [...cont.querySelectorAll('.g-comp')];
    let libre = -1, desde = 0, timers = [];
    const t0 = performance.now();
    st.limpiar.push(() => timers.forEach(clearTimeout));
    function soltar() {
      if (st.hecho) return;
      botones.forEach(b => b.classList.remove('libre'));
      libre = -1;
      timers.push(setTimeout(() => {
        if (st.hecho) return;
        libre = Math.floor(Math.random() * 4); desde = performance.now();
        botones[libre].classList.add('libre');
        timers.push(setTimeout(soltar, ventana));
      }, 350 + Math.random() * 500));
      if (performance.now() - t0 > limite * 1000) parar(-1, true);
    }
    soltar();
    function parar(i, tarde = false) {
      if (st.hecho) return;
      st.fin();
      let prec, texto = null;
      if (tarde) { prec = 0.1; texto = '¡Lo taparon!'; }
      else if (i !== libre || libre < 0) { prec = 0.15; texto = '¡Estaba marcado!'; }
      else prec = limitar(1 - 0.5 * ((performance.now() - desde) / ventana), 0.5, 1);
      botones.forEach(b => b.disabled = true);
      calificar(cont, prec, alListo, st, texto);
    }
    botones.forEach(b => b.onclick = () => parar(+b.dataset.i));
    teclas(st, e => ['1', '2', '3', '4'].includes(e.key) ? parar(+e.key - 1) : false);
    return st.cancelar;
  }

  // --- secuencia: el amague; repite las flechas en orden y rápido
  function secuencia(cont, zona, alListo) {
    const FL = {izq: '⬅', arr: '⬆', der: '➡'};
    const pasos = Array.from({length: 3}, () => ['izq', 'arr', 'der'][Math.floor(Math.random() * 3)]);
    const limite = 2.4 + limitar(zona || 0.12, 0.07, 0.28) * 8;        // segundos (3 a 4,6)
    cont.innerHTML = `<div class="g-caja">
        <p class="g-ayuda">🪄 Repite el amague: ${pasos.map(p => `<b class="g-paso">${FL[p]}</b>`).join(' ')}</p>
        <div class="g-tiempo"><i></i></div>
        <div class="g-flechas">${Object.entries(FL).map(([k, f]) => `<button data-f="${k}">${f}</button>`).join('')}</div></div>`;
    const st = nuevoEstado(), marcas = [...cont.querySelectorAll('.g-paso')];
    const barra = cont.querySelector('.g-tiempo i');
    barra.style.transition = `width ${limite}s linear`;
    requestAnimationFrame(() => barra.style.width = '0%');
    const t0 = performance.now();
    let i = 0, bien = 0;
    const timer = setTimeout(() => parar(), limite * 1000);
    st.limpiar.push(() => clearTimeout(timer));
    function tocar(f) {
      if (st.hecho) return;
      const ok = f === pasos[i];
      marcas[i].classList.add(ok ? 'ok' : 'mal');
      bien += ok; i++;
      if (i >= pasos.length) parar();
    }
    function parar() {
      if (st.hecho) return;
      st.fin();
      const usado = Math.min(1, (performance.now() - t0) / (limite * 1000));
      const prec = (bien / pasos.length) * (1 - 0.35 * usado);
      cont.querySelectorAll('.g-flechas button').forEach(b => b.disabled = true);
      calificar(cont, prec, alListo, st, i < pasos.length ? '¡Se acabó el tiempo!' : null);
    }
    cont.querySelectorAll('.g-flechas button').forEach(b => b.onclick = () => tocar(b.dataset.f));
    teclas(st, e => ({ArrowLeft: 'izq', ArrowUp: 'arr', ArrowRight: 'der'}[e.key] ? tocar({ArrowLeft: 'izq', ArrowUp: 'arr', ArrowRight: 'der'}[e.key]) : false));
    return st.cancelar;
  }

  // --- reacción: espera la señal y tírate hacia ese lado lo más rápido posible
  function reaccion(cont, zona, alListo) {
    const ventana = 380 + limitar(zona || 0.12, 0.07, 0.28) * 1700;   // ms para reaccionar bien
    const lado = Math.random() < 0.5 ? 'izq' : 'der';
    cont.innerHTML = `<div class="g-caja">
        <p class="g-ayuda">🧤 Espera la señal y lánzate hacia ese lado</p>
        <div class="g-senal">…</div>
        <div class="g-lados"><button data-l="izq">⬅ Izquierda</button><button data-l="der">Derecha ➡</button></div></div>`;
    const st = nuevoEstado(), senal = cont.querySelector('.g-senal');
    let desde = 0;
    const t1 = setTimeout(() => { if (st.hecho) return; desde = performance.now(); senal.textContent = lado === 'izq' ? '⬅' : '➡'; senal.classList.add('ya'); }, 700 + Math.random() * 1300);
    const t2 = setTimeout(() => parar(null, true), 5000);
    st.limpiar.push(() => { clearTimeout(t1); clearTimeout(t2); });
    function parar(l, tarde = false) {
      if (st.hecho) return;
      st.fin();
      let prec, texto = null;
      if (tarde) { prec = 0.1; texto = '¡Tarde!'; }
      else if (!desde) { prec = 0.1; texto = '¡Te adelantaste!'; }
      else if (l !== lado) { prec = 0.1; texto = '¡Al otro lado!'; }
      else prec = limitar(1 - 0.6 * Math.max(0, performance.now() - desde - 180) / ventana, 0.3, 1);
      cont.querySelectorAll('.g-lados button').forEach(b => b.disabled = true);
      calificar(cont, prec, alListo, st, texto);
    }
    cont.querySelectorAll('.g-lados button').forEach(b => b.onclick = () => parar(b.dataset.l));
    teclas(st, e => e.key === 'ArrowLeft' ? parar('izq') : e.key === 'ArrowRight' ? parar('der') : false);
    return st.cancelar;
  }

  const GESTOS = {
    barra: (c, z, ok) => barraTiempo(c, z, ok),
    rapida: (c, z, ok) => barraTiempo(c, z, ok, 3.2, {vel: 2.1, ayuda: '🦵 ¡Rápido! Toca en el verde'}),
    apuntar, companero, secuencia, reaccion,
  };
  function gesto(nombre, cont, zona, alListo) {
    return (GESTOS[nombre] || GESTOS.barra)(cont, zona, alListo);
  }

  // --- el pulso. prep: {inicio (del que ataca), rol: 'ataque'|'defensa', zona_ataque, zona_defensa, rondas,
  // empuje, atacante, defensor, gesto_ataque, gesto_defensa, decisivo}. rivalToque(r, mia): promesa con la
  // precisión del rival en la ronda r. Devuelve la promesa de tus toques.
  function pulso(cont, prep, rivalToque, textos = {}) {
    const mio = prep.rol === 'ataque';
    let barra = mio ? prep.inicio : 1 - prep.inicio;       // tu parte de la barra
    const yo = mio ? prep.atacante : prep.defensor, el = mio ? prep.defensor : prep.atacante;
    const miGesto = mio ? prep.gesto_ataque : prep.gesto_defensa;
    cont.innerHTML = `
      <div class="pulso${prep.decisivo ? ' decisivo' : ''}">
        ${prep.decisivo ? '<p class="pu-decisivo">🔥 MOMENTO DECISIVO · cada toque pesa más</p>' : ''}
        <div class="pu-duelo"><span class="pu-yo">${esc(yo.nombre)} <b>${esc(yo.stat)} ${yo.valor}</b></span><i>vs</i><span class="pu-el"><b>${esc(el.stat)} ${el.valor}</b> ${esc(el.nombre)}</span></div>
        <div class="pu-barra"><i class="pu-mia"></i><b class="pu-medio"></b><em class="pu-pct"></em></div>
        <p class="pu-ronda tenue"></p>
        <div class="pu-toque"></div>
      </div>`;
    const pintar = (delta = null) => {
      cont.querySelector('.pu-mia').style.width = (barra * 100) + '%';
      cont.querySelector('.pu-pct').textContent = Math.round(barra * 100) + '%';
      cont.querySelector('.pulso').classList.toggle('ganando', barra >= 0.5);
      if (delta !== null) {
        cont.querySelector('.pu-barra').insertAdjacentHTML('beforeend',
          `<span class="pu-delta ${delta >= 0 ? 'ok' : 'mal'}">${delta >= 0 ? '+' : ''}${Math.round(delta * 100)}</span>`);
      }
    };
    pintar();
    if (prep.decisivo) S.silbato(2, 0.15);
    const misToques = [];
    return new Promise(async resolver => {
      for (let r = 0; r < prep.rondas; r++) {
        cont.querySelector('.pu-ronda').textContent = `Ronda ${r + 1} de ${prep.rondas}`;
        // tope de seguridad: si el navegador congela las animaciones (pantalla apagada, app en segundo plano)
        // el gesto no termina nunca; a los 8 s la ronda cuenta como fallo y el partido sigue
        const p = await new Promise(ok => {
          let listo = false;
          const fin = v => { if (!listo) { listo = true; clearTimeout(tope); ok(v); } };
          const cancelar = gesto(miGesto, cont.querySelector('.pu-toque'), mio ? prep.zona_ataque : prep.zona_defensa, fin);
          const tope = setTimeout(() => { if (typeof cancelar === 'function') cancelar(); fin(0.1); }, 8000);
        });
        misToques.push(p);
        cont.querySelector('.pu-ronda').textContent = textos.esperando || 'El rival…';
        const q = await rivalToque(r, p);
        const delta = prep.empuje * (p - q);
        barra = limitar(barra + delta);
        pintar(delta);
        cont.querySelector('.pu-ronda').textContent = `Tú ${Math.round(p * 100)} · rival ${Math.round(q * 100)}`;
        await espera(650);
      }
      const gane = barra >= 0.5;
      cont.querySelector('.pu-toque').innerHTML = `<p class="pu-fin ${gane ? 'ok' : 'mal'}">${gane ? '💪 ¡Ganaste el pulso!' : '😖 Perdiste el pulso'}</p>`;
      if (gane) S.uy(); else S.abucheo();
      await espera(900);
      resolver(misToques);
    });
  }

  return {barraTiempo, gesto, pulso, espera};
})();
