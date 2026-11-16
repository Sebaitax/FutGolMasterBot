// Pausas del partido (ventana modal): jugadas clave con pulso, penal, expulsión y entretiempo/cambios.
// ctx: {D, S, estado, decidir(decision), alCambiarModal()}
const {esc, carta, api, reanimar} = window.FGM;
const {pulso} = window.FGM_PULSO;
const espera = ms => new Promise(r => setTimeout(r, ms));   // pausas reales (no dependen de la velocidad)

const NOMBRE_JUGADA = {tirar: 'Rematar', pasar: 'Pasarla', gambetear: 'Encarar', barrer: 'Ir al piso',
  achicar: 'Salir a achicar', cerrar: 'Cerrar el ángulo', izq: 'Izquierda', centro: 'Al medio', der: 'Derecha'};
const ICONO = {tirar: '🥅', pasar: '🤝', gambetear: '🪄'};
const ICONO_DEF = {barrer: '🦵', achicar: '🧤', cerrar: '🧱'};

export function crearPausas(ctx) {
  const {D, S} = ctx;
  const $ = id => document.getElementById(id);
  const modal = $('modal'), caja = $('modal-caja');
  const goles = () => ctx.estado.get().goles;
  let cronometro = null;

  function temporizador(segundos, alTerminar) {
    const fin = Date.now() + segundos * 1000;
    const circ = 2 * Math.PI * 26;
    caja.insertAdjacentHTML('afterbegin', `<div class="crono"><svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="26" class="c-fondo"/><circle cx="30" cy="30" r="26" class="c-arco" id="c-arco" stroke-dasharray="${circ}"/></svg><b id="c-num">${segundos}</b></div>`);
    clearInterval(cronometro);
    cronometro = setInterval(() => {
      const resta = Math.max(0, fin - Date.now());
      $('c-num').textContent = Math.ceil(resta / 1000);
      $('c-arco').style.strokeDashoffset = circ * (1 - resta / (segundos * 1000));
      if (resta < Math.min(10000, segundos * 400)) caja.classList.add('urgente');
      if (resta <= 0) { clearInterval(cronometro); alTerminar(); }
    }, 150);
  }
  function cerrar() {
    clearInterval(cronometro); modal.hidden = true; caja.className = 'modal-caja'; caja.onclick = null;
    ctx.alCambiarModal();
  }
  function mostrar(p) {
    modal.hidden = false;
    reanimar(caja, 'aparece');
    if (p.tipo === 'roja') pausaRoja(p);
    else if (p.tipo === 'ocasion') pausaOcasion(p);
    else if (p.tipo === 'penal') pausaPenal(p);
    else if (p.tipo === 'defensa') pausaDefensa(p);
    else if (p.tipo === 'corner' || p.tipo === 'tiro_libre') pausaParada(p);
    else pausaCambios(p);
    ctx.alCambiarModal();
  }

  // tarjetas de opción (sin porcentajes): el atributo de tu jugador y si ya te la conocen
  function opcionesMomento(p, iconos) {
    return `
      ${p.pista ? `<p class="m-pista">${FGM_ICO('search')} ${esc(p.pista)}</p>` : ''}
      <div class="m-opciones">${p.opciones.map((o, i) => `
        <button class="m-op${o.leida ? ' leida' : ''}" data-c="${o.clave}" style="animation-delay:${i * 90}ms">
          <span class="m-ico">${FGM_ICOTXT(o.ico || iconos[o.clave] || '⚽')}</span>
          <b>${esc(o.titulo)} <small class="m-stat">${esc(o.stat[0])} ${o.stat[1]}</small></b><small>${esc(o.detalle)}</small>
          ${o.riesgo ? `<em class="tenue">${esc(o.riesgo)}</em>` : ''}
          ${o.leida ? '<em class="m-leida">' + FGM_ICO('eye') + ' Ya la usaste: te la pueden estar esperando</em>' : ''}
        </button>`).join('')}</div>
      <div class="m-ejecucion"></div>`;
  }

  // elegir (a ciegas) → se revela lo del rival → pulso (o, en el penal, gana el lado) → decisión
  function jugarMomento(p, seleccion, alTiempo, armarDecision) {
    let elegida = null;
    temporizador(p.segundos || 12, () => { if (!elegida) elegir(alTiempo, true); });
    caja.querySelectorAll(seleccion).forEach(b => b.onclick = () => elegir(b.dataset.c || b.dataset.l));
    async function elegir(eleccion, porTiempo = false) {
      if (elegida) return;
      elegida = eleccion;
      clearInterval(cronometro);
      caja.querySelector('.crono')?.remove();
      caja.querySelectorAll(seleccion).forEach(x => x.classList.toggle('elegida', (x.dataset.c || x.dataset.l) === eleccion));
      let prep;
      try { prep = await api('/api/partido/elegir', {eleccion}); }
      catch (e) { window.FGM.toast(e.message, {error: true}); ctx.decidir(armarDecision(eleccion, [])); return; }
      const cont = caja.querySelector('.m-ejecucion');
      // la que quedó fija en el servidor (si recargaste la página, vale la primera que elegiste)
      const fija = prep.clase === 'penal' ? (prep.rol === 'ataque' ? prep.lado : prep.adivina) : (prep.rol === 'ataque' ? prep.ataque : prep.defensa);
      if (fija && fija !== eleccion) {
        eleccion = fija;
        caja.querySelectorAll(seleccion).forEach(x => x.classList.toggle('elegida', (x.dataset.c || x.dataset.l) === eleccion));
      }
      const mia = prep.rol === 'ataque' ? prep.nombre_ataque : prep.nombre_defensa;
      const suya = prep.rol === 'ataque' ? prep.nombre_defensa : prep.nombre_ataque;
      caja.classList.add('revelado');
      cont.innerHTML = `<p class="m-revela">${porTiempo ? 'Se acabó el tiempo. ' : ''}Tú: <b>${esc(mia || NOMBRE_JUGADA[eleccion] || eleccion)}</b> · Rival: <b>${esc(suya || '')}</b></p><div class="m-pulso"></div>`;
      if (prep.pulso === false) {   // penal: si el arquero no adivina el lado es gol; si adivina, la ataja
        const bien = prep.rol === 'ataque' ? prep.gol !== false : prep.gol === false;
        const txt = prep.rol === 'ataque' ? (bien ? '¡Lo mandaste al otro lado!' : '¡Te la atajó!') : (bien ? '¡La atajaste!' : 'Te tiraste al otro lado…');
        cont.insertAdjacentHTML('beforeend', `<p class="pu-fin ${bien ? 'ok' : 'mal'}">${txt}</p>`);
        await espera(1100);
        ctx.decidir(armarDecision(eleccion, []));
        return;
      }
      await espera(700);
      const toques = await pulso(cont.querySelector('.m-pulso'), prep, async r => { await espera(250); return prep.toques_rival[r]; });
      ctx.decidir(armarDecision(eleccion, toques));
    }
  }

  function pausaOcasion(p) {
    caja.classList.add('momento');
    caja.innerHTML = `
      <h2>¡Momento clave! <small class="tenue">${p.minuto}'</small></h2>
      <div class="mo-cab">${p.tirador ? carta(p.tirador) : ''}
        <p><b>${esc(p.jugador)}</b> queda de frente al arco${p.arquero ? ` de <b>${esc(p.arquero)}</b>` : ''}. ¿Qué hace? El rival también elige cómo defender.</p></div>
      ${opcionesMomento(p, ICONO)}
      <p class="tenue m-pie">Después se define en un pulso de 3 toques. Si se acaba el tiempo, remata.</p>`;
    jugarMomento(p, '.m-op', 'tirar', (eleccion, precisiones) => ({eleccion, precisiones}));
  }

  function pausaDefensa(p) {
    caja.classList.add('momento', 'defensa-caja');
    S.abucheo();
    caja.innerHTML = `
      <h2>¡Te atacan! <small class="tenue">${p.minuto}'</small></h2>
      <div class="mo-cab">${p.tirador ? carta(p.tirador) : ''}
        <p><b>${esc(p.jugador)}</b> se escapa hacia tu arco. ¿Cómo lo frenas? No sabes qué va a intentar.</p></div>
      ${opcionesMomento(p, ICONO_DEF)}
      <p class="tenue m-pie">Después se define en un pulso. Si se acaba el tiempo, cierras el ángulo.</p>`;
    jugarMomento(p, '.m-op', 'cerrar', (eleccion, precisiones) => ({eleccion, precisiones}));
  }

  function pausaParada(p) {
    const ataco = p.rol === 'ataque', corner = p.tipo === 'corner';
    caja.classList.add('momento');
    if (!ataco) caja.classList.add('defensa-caja');
    const titulo = corner ? (ataco ? '¡Córner a favor!' : 'Córner en contra') : (ataco ? '¡Tiro libre a favor!' : 'Tiro libre en contra');
    const sub = ataco ? `<b>${esc(p.jugador)}</b> va a la pelota${p.receptor ? `; ${esc(p.receptor)} espera en el área` : ''}. ¿Qué jugada hacen? El rival también elige cómo defender.`
      : `<b>${esc(p.jugador)}</b> va a la pelota. ¿Cómo defiendes? No sabes qué van a intentar.`;
    caja.innerHTML = `
      <h2>${titulo} <small class="tenue">${p.minuto}'</small></h2>
      <div class="mo-cab">${p.tirador ? carta(p.tirador) : ''}<p>${sub}</p></div>
      ${opcionesMomento(p, {})}
      <p class="tenue m-pie">Después se define en un pulso. Si se acaba el tiempo, se elige lo más simple.</p>`;
    jugarMomento(p, '.m-op', ataco ? p.opciones[0].clave : p.opciones[p.opciones.length - 1].clave,
      (eleccion, precisiones) => ({eleccion, precisiones}));
  }

  // penal simple: eliges el lado; si el arquero no adivina es gol, si adivina la ataja
  function pausaPenal(p) {
    caja.classList.add('momento', 'penal-caja');
    const titulo = p.patea ? `¡Penal a favor! Patea ${esc(p.pateador)}` : `¡Penal en contra! Ataja ${esc(p.arquero)}`;
    const sub = p.patea ? 'Elige dónde patear. Si el arquero no adivina, es gol.' : `Patea ${esc(p.pateador)}. Elige hacia dónde te tiras: si adivinas, la atajas.`;
    caja.innerHTML = `
      <h2>${titulo}</h2><p class="tenue">${sub} <small>(visto desde quien patea)</small></p>
      <div class="arco-penal">
        <button data-l="izq"><span>↖</span>Izquierda</button>
        <button data-l="centro"><span>${FGM_ICO('arrow-up')}</span>Al medio</button>
        <button data-l="der"><span>↗</span>Derecha</button>
      </div>
      <div class="m-ejecucion"></div>
      <p class="tenue m-pie">${p.patea ? 'Al medio: si el arquero se tira, es gol; si se queda, la ataja.' : 'Los pateadores van más a los costados que al medio.'}</p>`;
    jugarMomento(p, '[data-l]', p.patea ? 'izq' : 'centro', (lado, precisiones) => ({lado, precisiones}));
  }

  // --- cancha de la pausa: tus jugadores en su lugar, con su estado
  function marcas(j) {
    const m = [];
    if (j.goles) m.push(`<i class="pm gol">${FGM_ICO('pelota').repeat(Math.min(j.goles, 3))}</i>`);
    if (j.amarillas) m.push(`<i class="pm tarjeta-ico amarilla" title="Amonestado en este partido: otra amarilla y se va expulsado"></i>`);
    if (j.riesgo) m.push(`<i class="pm riesgo" title="${j.acumuladas} amarillas en la temporada: con una más queda suspendido">${FGM_ICO('tarjeta-amarilla')}${j.acumuladas}</i>`);
    return m.length ? `<span class="p-marcas">${m.join('')}</span>` : '';
  }
  const barraEnergia = e => `<i class="energia"><em style="width:${e}%" class="${e < 45 ? 'muy-baja' : e < 65 ? 'baja' : ''}"></em></i>`;
  function canchaPausa(est, cambios, selSale, vacio) {
    const coords = D.coordenadas[est.formacion], puestos = D.formaciones[est.formacion];
    const porSlot = {};
    est.cancha.forEach(j => porSlot[j.slot] = j);
    let html = '';
    for (let i = 0; i < coords.length; i++) {
      const [x, y] = coords[i];
      const j = porSlot[i];
      if (!j) {
        const f = est.fuera.filter(x => x.slot === i).pop();
        const entra = vacio && vacio.slot === i ? vacio.entra : null;
        html += `<div class="slot p-slot ${entra ? 'cubre' : 'hueco'}" style="left:${x}%;top:${y}%">
          ${entra ? carta(entra, {puesto: puestos[i], extra: '<i class="p-flecha">▲</i>'}) : `<div class="mini vacio hueco-roja"><span>${f && f.motivo === 'roja' ? FGM_ICO('tarjeta-roja') : '—'}</span></div>`}
          <small class="s-puesto">${entra ? window.FGM.pos(puestos[i]) : (f ? esc(f.nombre) : window.FGM.pos(puestos[i]))}</small></div>`;
        continue;
      }
      const c = cambios.find(x => x.sale === j.id);
      const entra = c ? est.banca.find(b => b.id === c.entra) : null;
      const mostrar = entra || j;
      const af = Math.round(100 * window.FGM.afinidad(mostrar.pos, j.puesto));
      const seVa = vacio && vacio.sale === j.id && vacio.entra;
      html += `<div class="slot p-slot${selSale === j.id ? ' sel' : ''}${entra ? ' cambiado' : ''}${seVa ? ' se-va' : ''}${j.energia < 45 && !entra ? ' agotado' : ''}"
                   data-sale="${j.id}" style="left:${x}%;top:${y}%">
        ${carta(mostrar, {puesto: j.puesto, extra: entra ? '<i class="p-flecha">▲</i>' : barraEnergia(j.energia) + marcas(j)})}
        <small class="s-puesto">${seVa ? '▼ sale' : window.FGM.pos(j.puesto)}${af < 100 && !seVa ? ` <em class="${af < 85 ? 'mal' : 'medio'}">${af}%</em>` : ''}</small></div>`;
    }
    return `<div class="cancha p-cancha">
      <div class="lineas"><div class="medio"></div><div class="circulo"></div><div class="area arriba"></div><div class="area abajo"></div><div class="chica arriba"></div><div class="chica abajo"></div></div>
      ${html}</div>`;
  }
  const leyendaPausa = est => `<p class="p-leyenda tenue"><span><i class="energia demo"><em style="width:70%"></em></i> energía</span>
      <span><i class="tarjeta-ico amarilla"></i> amonestado</span>
      ${D.tipo !== 'amistoso' ? `<span><i class="pm riesgo">${FGM_ICO('tarjeta-amarilla')}${est.limite_amarillas - 1}</i> 1 amarilla más = suspendido</span>` : ''}
      <span><em class="mal">80%</em> fuera de posición</span></p>`;

  function pausaRoja(p) {
    const ops = p.opciones || [], est = p.estado;
    let elegida = ops.length ? 0 : -1;
    caja.classList.add('pausa-cancha');
    caja.innerHTML = `
      <div class="roja-cab"><i class="tarjeta-ico roja gira"></i><div><h2>¡Expulsado ${esc(p.jugador)}!</h2>
      <p class="tenue">Te quedas con 10. Elige quién entra a cubrir el puesto y quién sale para dejarle lugar.</p></div></div>
      <div class="p-grid">
        <div class="p-izq"></div>
        <div class="p-der">
          <div class="opciones">${ops.map((o, i) => `
            <button class="opcion" data-i="${i}" style="animation-delay:${i * 120}ms">
              ${carta({nombre: o.entra_nombre, pos: o.entra_pos, ovr: o.entra_ovr, nivel: o.entra_nivel, club: o.entra_club, render: o.entra_render}, {puesto: o.puesto})}
              <span><b>Entra ${esc(o.entra_nombre)}</b> de ${esc(window.FGM.pos(o.puesto))} (${o.afinidad}%)<br><small class="tenue">Sale ${esc(o.sale_nombre)} (${esc(window.FGM.pos(o.sale_puesto))})</small></span>
            </button>`).join('')}
            <button class="opcion sin" data-i="-1"><span><b>Seguir con 10</b><br><small class="tenue">Sin cambios</small></span></button>
          </div>
          <button class="primario p-ok">Confirmar</button>
        </div>
      </div>`;
    function pintar() {
      const o = ops[elegida];
      const entra = o ? est.banca.find(b => b.id === o.entra) : null;
      caja.querySelector('.p-izq').innerHTML = canchaPausa(est, [], null, {slot: p.slot, sale: o ? o.sale : null, entra}) + leyendaPausa(est);
      caja.querySelectorAll('.opcion').forEach(b => b.classList.toggle('activa', +b.dataset.i === elegida));
    }
    caja.querySelectorAll('.opcion').forEach(b => { b.onclick = () => { elegida = +b.dataset.i; pintar(); }; });
    const confirmar = () => { const o = ops[elegida]; ctx.decidir(o ? {entra: o.entra, sale: o.sale} : {}); };
    caja.querySelector('.p-ok').onclick = confirmar;
    pintar();
    temporizador(p.segundos || 25, confirmar);
  }

  // entretiempo y pausa táctica: cambios, mentalidad y táctica (25 s: el partido dura ~3 min)
  function pausaCambios(p) {
    const est = p.estado, entretiempo = p.tipo === 'descanso';
    let cambios = [], selSale = null, mentalidad = est.mentalidad, tactica = est.tactica || 'normal';
    const [g0, g1] = goles();
    caja.classList.add('pausa-cancha');
    caja.innerHTML = `
      <h2>${entretiempo ? `Entretiempo · ${g0} - ${g1}` : `Pausa táctica · ${p.minuto}' · ${g0} - ${g1}`}</h2>
      <p class="tenue">Toca un jugador en la cancha y después uno de la banca. Tócalo de nuevo para deshacer.</p>
      <div class="p-grid">
        <div class="p-izq"></div>
        <div class="p-der">
          <h3>Táctica</h3>
          <div class="t-chips d-tact">${Object.entries(D.tacticas).map(([k, t]) => `<button class="t-chip" data-tc="${k}" title="${esc(t.ayuda)}"><span>${FGM_ICOTXT(t.ico)}</span>${esc(t.nombre)}</button>`).join('')}</div>
          <p class="tenue d-ayuda"></p>
          <h3>Banca <small class="tenue d-rest"></small></h3>
          <div class="d-banca"></div>
          <ul class="d-lista"></ul>
          <button class="primario d-ok">${entretiempo ? '▶ Empezar el segundo tiempo' : '▶ Seguir jugando'}</button>
        </div>
      </div>`;
    function pintar() {
      const usados = new Set(cambios.map(c => c.entra));
      const restantes = est.cambios - cambios.length;
      const sel = est.cancha.find(j => j.id === selSale);
      caja.querySelector('.p-izq').innerHTML = canchaPausa(est, cambios, selSale) + leyendaPausa(est);
      caja.querySelector('.d-banca').innerHTML = est.banca.map(j => {
        const af = sel ? Math.round(100 * window.FGM.afinidad(j.pos, sel.puesto)) : null;
        const usado = usados.has(j.id);
        return `<div class="d-jug${usado ? ' entra' : ''}${sel && !usado ? ' elegible' : ''}" data-entra="${j.id}">
          ${carta(j, {extra: marcas(j)})}
          <small>${af !== null && !usado ? `<em class="${af < 85 ? 'mal' : af < 100 ? 'medio' : 'ok'}">${af}% de ${window.FGM.pos(sel.puesto)}</em>` : window.FGM.pos(j.pos)}</small></div>`;
      }).join('') || '<p class="tenue">Sin suplentes.</p>';
      caja.querySelector('.d-lista').innerHTML = cambios.map((c, i) => {
        const s = est.cancha.find(j => j.id === c.sale), e = est.banca.find(j => j.id === c.entra);
        return `<li><span class="sube">▲ ${esc(e.nombre)}</span><span class="baja">▼ ${esc(s.nombre)}</span><button data-q="${i}" class="enlace" aria-label="Quitar">${FGM_ICO('x')}</button></li>`;
      }).join('');
      caja.querySelector('.d-rest').textContent = sel ? `· ¿quién entra por ${sel.nombre}?` : `· ${restantes} cambio${restantes === 1 ? '' : 's'} disponible${restantes === 1 ? '' : 's'}`;
      caja.querySelectorAll('.d-ment button').forEach(b => b.classList.toggle('activo', b.dataset.m === mentalidad));
      caja.querySelectorAll('[data-tc]').forEach(b => b.classList.toggle('activo', b.dataset.tc === tactica));
      caja.querySelector('.d-ayuda').textContent = D.tacticas[tactica].ayuda;
    }
    caja.onclick = e => {
      const s = e.target.closest('[data-sale]'), en = e.target.closest('[data-entra]'), q = e.target.closest('[data-q]'),
            m = e.target.closest('[data-m]'), tc = e.target.closest('[data-tc]');
      if (m) mentalidad = m.dataset.m;
      else if (tc) tactica = tc.dataset.tc;
      else if (q) cambios.splice(+q.dataset.q, 1);
      else if (s) {
        const id = +s.dataset.sale, ya = cambios.findIndex(c => c.sale === id);
        if (ya >= 0) { cambios.splice(ya, 1); selSale = null; }
        else if (cambios.length >= est.cambios) { window.FGM.toast('No te quedan cambios'); return; }
        else selSale = selSale === id ? null : id;
      } else if (en && selSale) {
        const id = +en.dataset.entra;
        if (!cambios.some(c => c.entra === id)) { cambios.push({sale: selSale, entra: id}); selSale = null; }
      } else return;
      pintar();
    };
    const listo = () => ctx.decidir({cambios, mentalidad, tactica});
    caja.querySelector('.d-ok').onclick = listo;
    pintar();
    temporizador(p.segundos || 25, listo);
  }

  return {mostrar, cerrar, abierta: () => !modal.hidden};
}
