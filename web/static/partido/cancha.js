// La cancha animada: fichas de los jugadores, la pelota y cómo se ve cada jugada.
// Código directo sobre el DOM (las animaciones no ganan nada con un framework).
// ctx: {D, S, estado, flags: {saltando, velocidad, enJugada}, T(ms), dormir(ms), escribir(l)}
const {esc, reanimar, confeti} = window.FGM;
const rnd = (a, b) => a + Math.random() * (b - a);
const tope = (v, a, b) => Math.max(a, Math.min(b, v));
export const TIROS = ['gol', 'atajada', 'desviado', 'palo'];

export function apellido(n) {
  const p = String(n).trim().split(/\s+/);
  return p.length > 1 && p[0].length <= 3 ? p.slice(1).join(' ') : p[p.length - 1];
}

export function crearCancha(ctx) {
  const {D, S, flags, T, dormir} = ctx;
  const $ = id => document.getElementById(id);
  const estadio = $('estadio'), pelota = $('pelota'), anuncio = $('anuncio'), capa = $('fichas');
  const COLORES = D.colores || ['#f4f6f8', '#e5534b'];
  const nombres = [D.local, D.visita];

  // ---------- jugadores (horizontal: el local ataca hacia la derecha)
  const fichas = [[], []];
  function ubicar(f, x, y, ms = 600) {
    if (!f) return;
    f.x = x; f.y = y;
    f.el.style.transitionDuration = flags.saltando ? '0s' : T(ms) + 'ms';
    f.el.style.left = x + '%'; f.el.style.top = y + '%';
  }
  // colores: camiseta de cada equipo, número legible encima y el arquero de un color que no se confunda
  const rgb = h => { const n = parseInt(String(h).replace('#', '').padEnd(6, '0').slice(0, 6), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
  const claro = h => { const [r, g, b] = rgb(h); return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6; };
  const distancia = (a, b) => rgb(a).reduce((s, x, i) => s + Math.abs(x - rgb(b)[i]), 0);
  const ARQUEROS = ['#f2c94c', '#8e44ad', '#16a085', '#ff7f2a', '#111111'];
  const colorArquero = [];
  ARQUEROS.slice().sort((a, b) => Math.min(...COLORES.map(c => distancia(b, c))) - Math.min(...COLORES.map(c => distancia(a, c))))
    .slice(0, 2).forEach((c, i) => colorArquero[i] = c);
  (D.equipos || []).forEach((e, eq) => {
    const puestos = D.formaciones[e.formacion], coords = D.coordenadas[e.formacion];
    if (!puestos || !coords) return;
    e.jugadores.forEach((nombre, slot) => {
      const el = document.createElement('div');
      el.className = 'ficha' + (puestos[slot] === 'GK' ? ' arquero' : '') + (eq === D.lado ? ' mia' : '');
      const color = puestos[slot] === 'GK' ? colorArquero[eq] : COLORES[eq];
      el.style.setProperty('--c', color);
      el.style.setProperty('--t', claro(color) ? '#1b1b1b' : '#fff');
      el.innerHTML = `<i><b>${slot + 1}</b></i><span>${esc(apellido(nombre))}</span>`;
      el.title = nombre;
      capa.appendChild(el);
      const [cx, cy] = coords[slot];
      const prof = 7 + (100 - cy) * 0.46;     // profundidad desde el propio arco
      const base = eq === 0 ? [prof, cx] : [100 - prof, 100 - cx];
      const f = {el, nombre, eq, puesto: puestos[slot], linea: window.FGM.linea(puestos[slot]), base, x: 0, y: 0, activo: true};
      fichas[eq].push(f);
      ubicar(f, base[0], base[1], 0);
    });
  });
  const activas = eq => fichas[eq].filter(f => f.activo);
  const buscar = (eq, nombre) => nombre ? activas(eq).find(f => f.nombre === nombre) : null;
  const arquero = eq => activas(eq).find(f => f.puesto === 'GK');
  function elegir(eq, lineasOk) {
    const c = activas(eq).filter(f => f.puesto !== 'GK' && lineasOk.includes(f.linea));
    const todos = c.length ? c : activas(eq).filter(f => f.puesto !== 'GK');
    return todos[Math.floor(Math.random() * todos.length)];
  }
  // los dos bloques se mueven según quién tiene la pelota
  function formar(eqBalon, empuje = 1, ms = 650) {
    for (const eq of [0, 1]) for (const f of activas(eq)) {
      const dir = eq === 0 ? 1 : -1;
      let [x, y] = f.base;
      if (eqBalon === eq) x += dir * (f.puesto === 'GK' ? 5 : (f.linea === 'DEF' ? 11 : 17) * empuje);
      else if (eqBalon >= 0 && f.puesto !== 'GK') { x -= dir * (f.linea === 'DEL' ? 9 : 3) * empuje; y = 50 + (y - 50) * 0.86; }
      if (f.puesto !== 'GK' && eqBalon >= 0) { x += rnd(-2.5, 2.5); y += rnd(-4, 4); }
      ubicar(f, tope(x, 3, 97), tope(y, 6, 94), ms);
    }
  }

  // ---------- la pelota
  let bx = 50, by = 50, conPelota = null;
  pelota.style.left = '50%'; pelota.style.top = '50%';
  function pelotaA(x, y, ms, {alto = 0} = {}) {
    const ini = {left: bx + '%', top: by + '%', transform: 'translate(-50%,-50%) scale(1)'};
    const fin = {left: x + '%', top: y + '%', transform: 'translate(-50%,-50%) scale(1)'};
    const [x0, y0] = [bx, by];
    bx = x; by = y;
    pelota.style.left = x + '%'; pelota.style.top = y + '%';
    if (flags.saltando) return Promise.resolve();
    const frames = alto ? [ini, {left: (x0 + x) / 2 + '%', top: (y0 + y) / 2 + '%',
                                 transform: `translate(-50%,-50%) scale(${1 + alto})`, offset: .5}, fin] : [ini, fin];
    const anim = pelota.animate(frames, {duration: T(ms), easing: 'ease-in-out'});
    // tope de tiempo: si el navegador congela la animación (pestaña oculta), el partido sigue igual
    return Promise.race([anim.finished.catch(() => {}), new Promise(r => setTimeout(r, T(ms) + 60))]);
  }
  function portador(f) {
    if (conPelota) conPelota.el.classList.remove('con-pelota');
    conPelota = f || null;
    if (f) f.el.classList.add('con-pelota');
  }
  async function pasar(f, ms = 380, opts) {
    if (!f) return;
    if (!flags.saltando) S.patada();
    portador(f);
    await pelotaA(f.x + (f.eq === 0 ? 1.3 : -1.3), f.y + 1.6, ms, opts);
  }
  function aviso(texto, clase = '') {
    if (flags.saltando) return;
    const a = $('aviso-jugada');
    a.innerHTML = FGM_ICOTXT(String(texto).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]))); a.className = 'aviso-jugada visible ' + clase;
    clearTimeout(aviso.t); aviso.t = setTimeout(() => a.className = 'aviso-jugada', T(1300));
  }
  function anunciar(html, clase, ms = 1600) {
    if (flags.saltando) return;
    anuncio.innerHTML = html; anuncio.className = 'anuncio visible ' + (clase || '');
    clearTimeout(anunciar.t); anunciar.t = setTimeout(() => anuncio.className = 'anuncio', ms / Math.min(flags.velocidad, 2));
  }

  // ---------- cambios, rojas y amarillas en la cancha (también al saltar)
  function plantel(l) {
    if (l._plantel) return;
    l._plantel = true;
    if (l.tipo === 'cambio') {
      const f = buscar(l.equipo, l.sale);
      if (f) {
        f.nombre = l.jugador; f.el.title = l.jugador;
        f.el.querySelector('span').textContent = apellido(l.jugador);
        f.el.classList.remove('amonestado');
        if (!flags.saltando) reanimar(f.el, 'entra-jug');
      }
    } else if (l.tipo === 'roja') {
      const f = buscar(l.equipo, l.jugador);
      if (f) { f.activo = false; f.el.classList.add('fuera'); }
    } else if (l.tipo === 'amarilla') {
      const f = buscar(l.equipo, l.jugador);
      if (f) f.el.classList.add('amonestado');
    }
  }

  // ---------- jugadas
  function marcarGol(l) {
    const eq = l.equipo;
    ctx.estado.set(e => ({goles: [...l.marcador], golAnim: e.golAnim.map((v, i) => i === eq ? Date.now() : v)}));
    reanimar(estadio, 'sacude');
    reanimar($(eq === 0 ? 'arco-der' : 'arco-izq'), 'red');
    anunciar(`<b>¡GOL!</b><span>${esc(l.jugador)} · ${esc(nombres[eq])}</span>`, 'gol', 2200);
    if (eq === D.lado) confeti(60);
  }
  const ladoY = (lado, eqT) => 50 + ({izq: -1, centro: 0, der: 1}[lado] || 0) * (eqT === 0 ? 1 : -1) * 4.2;

  async function jugadaTiro(l) {
    const eqT = l.tipo === 'atajada' ? 1 - l.equipo : l.equipo;   // quién remata
    const dir = eqT === 0 ? 1 : -1;
    const tir = buscar(eqT, l.tipo === 'atajada' ? l.tirador : l.jugador) || elegir(eqT, ['DEL']);
    const asis = l.asistente ? buscar(eqT, l.asistente) : null;
    const arq = arquero(1 - eqT);
    if (l.penal) {
      if (!flags.enJugada) await prepararPenal({equipo: eqT, jugador: tir && tir.nombre});
      await dormir(350);
    } else if (flags.enJugada) {
      if (tir && conPelota !== tir) await pasar(tir, 420);   // pasaste la pelota en el momento clave
    } else if (l.tipo === 'desviado' || l.tipo === 'atajada') {
      // remate común: un pase y al arco (misma velocidad, menos preparación)
      formar(eqT, 1.2, 600);
      if (tir) ubicar(tir, eqT === 0 ? rnd(76, 84) : rnd(16, 24), rnd(32, 68), 600);
      await pasar(tir, 520, {alto: /centro/.test(l.jugada || '') ? .9 : .15});
      await dormir(150);
    } else {
      aviso('¡Se viene!');
      formar(eqT, 1.35, 700);
      if (tir) ubicar(tir, eqT === 0 ? rnd(78, 86) : rnd(14, 22), rnd(32, 68), 700);
      await pasar(asis && asis !== tir ? asis : elegir(eqT, ['MED']), 460);
      await dormir(120);
      await pasar(tir, 520, {alto: /centro/.test(l.jugada || '') ? .9 : .15});
      await dormir(200);
    }
    flags.enJugada = false;
    estadio.classList.remove('lento');
    // remate
    let ty = l.lado ? ladoY(l.lado, eqT) : rnd(45.5, 54.5);
    if (l.tipo === 'desviado') ty = l.lado && l.lado !== 'centro' ? 50 + Math.sign(ty - 50) * 10 : (Math.random() < .5 ? rnd(31, 41) : rnd(59, 69));
    if (l.tipo === 'palo') ty = Math.random() < .5 ? 44.2 : 55.8;
    if (arq) {
      const ay = l.tipo === 'atajada' ? ty : l.adivina ? ladoY(l.adivina, eqT) : 50 + (ty < 50 ? 3.5 : -3.5);
      ubicar(arq, eqT === 0 ? 96.6 : 3.4, ay, 240);
      if (!flags.saltando) { arq.el.classList.add('vuela'); setTimeout(() => arq.el.classList.remove('vuela'), T(800)); }
    }
    portador(null);
    const destinoX = l.tipo === 'atajada' ? (eqT === 0 ? 96 : 4) : (eqT === 0 ? 99.3 : 0.7) + (l.tipo === 'desviado' ? dir * 2 : 0);
    if (!flags.saltando) S.patada(true);
    await pelotaA(destinoX, ty, l.penal ? 360 : 320, {alto: .3});
    if (l.tipo === 'gol') {
      if (!flags.saltando) S.gol(eqT === D.lado);
      marcarGol(l); ctx.escribir(l);
      // festejo: los compañeros van hacia el goleador
      if (tir && !flags.saltando) activas(eqT).filter(f => f.puesto !== 'GK').forEach(f => ubicar(f, tir.x - dir * rnd(2, 8), tir.y + rnd(-8, 8), 900));
      await dormir(2300);
      formar(-1, 1, 800);
      await pelotaA(50, 50, 500);
    } else {
      if (!flags.saltando) S.uy();
      ctx.escribir(l);
      if (l.tipo === 'atajada') { anunciar(`<b>${FGM_ICO('hand')} ¡Atajada!</b>`, 'atajada', 1100); await pelotaA(eqT === 0 ? 87 : 13, tope(ty + rnd(-20, 20), 10, 90), 320); }
      else if (l.tipo === 'palo') { anunciar('<b>¡PALO!</b>', 'palo'); reanimar(estadio, 'sacude'); await pelotaA(eqT === 0 ? 85 : 15, rnd(30, 70), 380); }
      else aviso(l.corner ? 'Córner' : 'Afuera');
      await dormir(l.tipo === 'desviado' ? 380 : 600);
    }
  }

  async function jugadaMomento(l) {
    const eqT = l.equipo, tir = buscar(eqT, l.jugador), asis = l.asistente ? buscar(eqT, l.asistente) : null;
    aviso('¡Momento clave!', 'clave');
    formar(eqT, 1.35, 700);
    if (tir) ubicar(tir, eqT === 0 ? rnd(76, 82) : rnd(18, 24), rnd(36, 64), 700);
    await pasar(asis || elegir(eqT, ['MED']), 460);
    await pasar(tir, 520);
    ctx.escribir(l);
    flags.enJugada = true;
    if (!flags.saltando) estadio.classList.add('lento');
  }

  async function prepararPenal(l) {
    const eqT = l.equipo, tir = buscar(eqT, l.jugador), arq = arquero(1 - eqT);
    for (const eq of [0, 1]) for (const f of activas(eq)) {
      if (f === tir || f === arq) continue;
      ubicar(f, eqT === 0 ? rnd(64, 74) : rnd(26, 36), rnd(18, 82), 600);
    }
    if (tir) ubicar(tir, eqT === 0 ? 84.5 : 15.5, 50, 600);
    if (arq) ubicar(arq, eqT === 0 ? 97 : 3, 50, 600);
    portador(tir);
    await pelotaA(eqT === 0 ? 88.6 : 11.4, 50, 500);
    flags.enJugada = true;
  }

  async function jugadaPerdida(l) {
    const quita = l.como === 'gambeta' ? buscar(1 - l.equipo, l.otro) : elegir(1 - l.equipo, ['DEF']);
    if (l.como === 'pase') {
      const rec = buscar(l.equipo, l.otro);
      if (rec) await pelotaA((bx + rec.x) / 2, (by + rec.y) / 2, 300);
    }
    if (quita) { ubicar(quita, bx, by, 260); await dormir(260); await pasar(quita, 300); }
    ctx.escribir(l);
    aviso('La perdiste');
    flags.enJugada = false;
    estadio.classList.remove('lento');
    await dormir(700);
  }

  // el que hizo la falta va a donde está la pelota
  function aLaPelota(f) { if (f) ubicar(f, bx, by + 2, 300); }

  // jugada de pases de un minuto tranquilo
  async function circular(eq) {
    formar(eq, 1, 420);
    await pasar(elegir(eq, ['DEF', 'MED']), 340);
    await dormir(120);
    await pasar(elegir(eq, ['MED', 'DEL']), 340);
    await dormir(120);
  }

  return {estadio, formar, ubicar, pelotaA, pasar, elegir, buscar, aviso, anunciar, plantel, marcarGol,
          jugadaTiro, jugadaMomento, prepararPenal, jugadaPerdida, circular, aLaPelota, nombres};
}
