// Partido en vivo entre dos jugadores (PvP). Misma cancha, mismo ritmo y misma animación que el
// partido contra la máquina (jugadas.js); cambia de dónde salen los datos (la sala del servidor) y
// las jugadas clave (los dos eligen a ciegas y se define en un pulso con los toques de ambos).
import {html, render} from '../vendor/preact-htm.js';
import {crearEstado, absoluto, clave} from './estado.js';
import {Numeros, Controles, Tacticas, Indicadores, RelatoActual, RelatoTodo} from './ui.js';
import {crearCancha} from './cancha.js';
import {crearJugadas} from './jugadas.js';

const D = JSON.parse(document.getElementById('datos').textContent);
const {esc, api, toast, carta, confeti, reanimar} = window.FGM;
const {pulso} = window.FGM_PULSO;
const S = window.FGM_SONIDO;
const $ = id => document.getElementById(id);
const espera = ms => new Promise(r => setTimeout(r, ms));
const RITMO = 1.8;   // el mismo del partido contra la máquina

const flags = {saltando: false, velocidad: 1, enJugada: false};
const ctx = {
  D, S, flags, T: ms => ms * RITMO,
  dormir: ms => flags.saltando ? Promise.resolve() : new Promise(r => setTimeout(r, ms * RITMO)),
  estado: crearEstado({
    goles: [0, 0], golAnim: [0, 0], reloj: {t: 1, m: 0}, descanso: false, pos: [50, 50], prob: null,
    dominio: [], etX: null, relato: [], actual: null, velocidad: 1, terminado: false, bloqueado: true,
    tactica: 'normal', tactica_rival: 'normal', rival_desde: null, pendiente: null, pidiendoPausa: false,
    pausas_restantes: 0, cambios_restantes: 0, ultima_tactica: null,
  }),
};
ctx.cancha = crearCancha(ctx);
const J = crearJugadas(ctx);
const estado = ctx.estado;

// ---------- lo que manda el servidor
let lineas = [], posesion = [], eventos = 0, version = 0, iMin = 0, iLinea = 0, ahora = [1, 0];
let ult = null, final = false, terminado = false, vistasReac = 0;

// ---------- conexión con el servidor: abierta (WebSocket) y, si falla, pedidos HTTP como respaldo
let ws = null, wsListo = false, intentosWs = 0, esperandoEstado = [], idAccion = 0;
const respuestas = new Map();
function conectar() {
  try {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/vivo/${D.id}`);
  } catch { ws = null; return; }
  ws.onopen = () => { wsListo = true; intentosWs = 0; ws.send(JSON.stringify({tipo: 'estado', desde: eventos, t: ahora[0], m: ahora[1]})); };
  ws.onmessage = ev => {
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.tipo === 'estado') { procesar(msg); esperandoEstado.splice(0).forEach(f => f()); }
    else if (msg.tipo === 'respuesta' && respuestas.has(msg.id)) { respuestas.get(msg.id)(msg); respuestas.delete(msg.id); }
  };
  ws.onclose = () => {
    wsListo = false; ws = null;
    esperandoEstado.splice(0).forEach(f => f());
    if (terminado) return;
    if (intentosWs === 2) window.FGM_LOG && FGM_LOG({mensaje: 'reconectando conexión en vivo', tipo: 'aviso'});
    if (++intentosWs <= 8) setTimeout(conectar, Math.min(8000, 800 * intentosWs));   // se reconecta solo
  };
}

// pide el estado: por la conexión abierta (y espera el próximo estado) o por HTTP
let pidiendo = null;
function pedir() {
  if (pidiendo) return pidiendo;
  pidiendo = (async () => {
    try {
      if (wsListo) {
        await new Promise(ok => {
          esperandoEstado.push(ok);
          ws.send(JSON.stringify({tipo: 'estado', desde: eventos, t: ahora[0], m: ahora[1]}));
          setTimeout(ok, 4000);   // si no responde, sigue (y se reintenta)
        });
      } else {
        const r = await (await fetch(`/api/vivo/${D.id}/estado?desde=${eventos}&t=${ahora[0]}&m=${ahora[1]}`)).json();
        procesar(r);
      }
    } catch {
      $('conexion').innerHTML = '· reconectando… ' + FGM_ICO('punto-amarillo');
    } finally { pidiendo = null; }
  })();
  return pidiendo;
}
// el minuto que estoy viendo (para que el servidor sepa cuándo llegué a una jugada clave)
function avisarVista() { if (wsListo) ws.send(JSON.stringify({tipo: 'vista', t: ahora[0], m: ahora[1]})); }

// una acción del jugador (elegir, toque, táctica, reacción, revancha)
function accion(nombre, cuerpo = {}) {
  if (wsListo) {
    return new Promise((ok, mal) => {
      const id = ++idAccion;
      respuestas.set(id, r => r.error ? mal(new Error(r.error)) : ok(r));
      ws.send(JSON.stringify({tipo: 'accion', id, accion: nombre, ...cuerpo}));
      setTimeout(() => { if (respuestas.delete(id)) api(`/api/vivo/${D.id}/${nombre}`, cuerpo).then(ok, mal); }, 4000);
    });
  }
  return api(`/api/vivo/${D.id}/${nombre}`, cuerpo);
}

function procesar(r) {
  if (r.error) { toast(r.error, {error: true}); if (/ya no existe/.test(r.error)) setTimeout(() => location.href = '/', 2500); return; }
  if (r.version !== version) {   // alguien cambió la táctica: desde ahí el partido es otro
    version = r.version;
    lineas = lineas.slice(0, iLinea);
    eventos = Math.min(eventos, r.corte);
    ult = r;
    setTimeout(pedir, 0);
    return;
  }
  lineas.push(...r.lineas);
  eventos = r.eventos;
  posesion = r.posesion;
  final = r.final;
  ult = r;
  estado.set({tactica: r.tactica});   // la del rival se conoce por el relato (y tarda unos minutos en leerse)
  $('conexion').innerHTML = (r.rival_conectado ? '· rival conectado ' + FGM_ICO('punto-verde') : '· rival desconectado ' + FGM_ICO('punto-rojo')) + (wsListo ? '' : ' ·');
  $('apuesta').innerHTML = r.apuesta ? `· ${FGM_ICO('moneda')} ${(2 * r.apuesta).toLocaleString('es-CL')} en juego` : '';
  for (const x of r.reacciones || []) if (x.n > vistasReac) { vistasReac = x.n; lluvia(x.emoji, false); }
  if (r.revancha && r.revancha.partido) location.href = `/vivo/${r.revancha.partido}`;
  pintarRevancha();
}

// ---------- reproducción: el mismo minuto a minuto que contra la máquina
async function reproducir() {
  while (true) {
    try {
      if (iMin < posesion.length) {
        const min = posesion[iMin++];
        ahora = [min[0], min[1]];
        const k = clave(min[0], min[1]), ls = [];
        while (iLinea < lineas.length && clave(lineas[iLinea].tiempo, lineas[iLinea].min) <= k
               && !['final', 'resumen'].includes(lineas[iLinea].tipo)) ls.push(lineas[iLinea++]);
        await J.minuto(min, ls);
        estado.set({bloqueado: !$('modal').hidden || terminado});
        avisarVista();
        if (!wsListo && iMin % 3 === 0) pedir();   // sin conexión abierta: se va pidiendo de a poco
        continue;
      }
      // al día con lo simulado: ¿jugada clave, final o seguir pidiendo?
      while (iLinea < lineas.length && !['final', 'resumen'].includes(lineas[iLinea].tipo)) await J.efecto(lineas[iLinea++]);
      if (ult && ult.pausa) { await atenderPausa(ult.pausa); await pedir(); continue; }
      if (final) { while (iLinea < lineas.length) J.escribir(lineas[iLinea++]); return terminar(); }
      await espera(700);
      await pedir();
    } catch (e) {   // nunca se queda pegado: se cierra la jugada abierta y se reintenta
      $('modal').hidden = true;
      $('conexion').innerHTML = '· reconectando… ' + FGM_ICO('punto-amarillo');
      await espera(1500);
    }
  }
}

// ---------- jugada clave: eliges a ciegas, esperas al rival y pulso
const NOMBRE = {tirar: 'Rematar', pasar: 'Pasarla', gambetear: 'Encarar', barrer: 'Ir al piso',
  achicar: 'Salir a achicar', cerrar: 'Cerrar el ángulo', izq: 'Izquierda', centro: 'Al medio', der: 'Derecha'};
const modal = $('modal'), caja = $('modal-caja');
// espera hasta que se cumpla `cond` en la jugada actual. Si esa jugada ya se resolvió (p. ej. un penal,
// que se define apenas eligen los dos) y el servidor ya tiene la siguiente, vuelve de inmediato: antes se
// quedaba esperando la siguiente jugada, que no empieza hasta que los dos lleguen a ese minuto (se pegaba).
async function esperarHasta(cond, actual) {
  const t0 = Date.now();
  let avisado = false;
  while (true) {
    if (!avisado && Date.now() - t0 > 25000) {   // más de 25 s esperando: queda en la bitácora para revisarlo
      avisado = true;
      window.FGM_LOG && FGM_LOG({mensaje: 'posible pegado en jugada clave (en vivo)', tipo: 'aviso',
        datos: JSON.stringify({actual, pausa: ult && ult.pausa && {tipo: ult.pausa.tipo, minuto: ult.pausa.minuto, prep: !!ult.pausa.prep}, ws: wsListo})});
    }
    await pedir();
    const p = ult && ult.pausa;
    if (!p || cond(p)) return p;
    if (actual && (p.minuto !== actual.minuto || p.tiempo !== actual.tiempo || p.tipo !== actual.tipo)) return p;
    await espera(400);
  }
}
async function atenderPausa(p) {
  modal.hidden = false;
  estado.set({bloqueado: true});
  reanimar(caja, 'aparece');
  const ataco = p.rol === 'ataque', penal = p.tipo === 'penal';
  const clase = p.clase || 'jugada';
  const titulo = penal ? (ataco ? `¡Penal a favor! Patea ${esc(p.pateador)}` : `¡Penal en contra! Ataja ${esc(p.arquero)}`)
    : clase === 'corner' ? (ataco ? `¡Córner a favor! Va ${esc(p.jugador)}` : `Córner en contra: va ${esc(p.jugador)}`)
    : clase === 'tiro_libre' ? (ataco ? `¡Tiro libre a favor! Patea ${esc(p.jugador)}` : `Tiro libre en contra: patea ${esc(p.jugador)}`)
    : ataco ? `¡Jugada clave! ${esc(p.jugador)} queda de frente al arco` : `¡Te atacan! ${esc(p.jugador)} se escapa`;
  const opciones = penal ? ['izq', 'centro', 'der'].map(l => ({clave: l, titulo: NOMBRE[l], detalle: ''})) : p.opciones;
  caja.className = 'modal-caja momento' + (ataco ? '' : ' defensa-caja');
  caja.innerHTML = `<h2>${titulo} <small class="tenue">${p.minuto}'</small></h2>
    ${p.tirador ? `<div class="mo-cab">${carta(p.tirador)}<p class="tenue">` : '<p class="tenue">'}${ataco ? 'Tu rival elige cómo defender' : 'Tu rival elige cómo atacar'}, sin ver lo tuyo.${penal ? ' Si el arquero no adivina el lado, es gol.' : ' Después: pulso.'}</p>
    ${p.tirador ? '</div>' : ''}
    ${p.decisivo ? '<p class="pu-decisivo">MOMENTO DECISIVO</p>' : ''}
    <div class="m-opciones">${opciones.map(o => `<button class="m-op" data-c="${o.clave}">${o.ico ? `<span class="m-ico">${FGM_ICOTXT(o.ico)}</span>` : ''}<b>${esc(o.titulo)}${o.stat ? ` <small class="m-stat">${esc(o.stat[0])} ${o.stat[1]}</small>` : ''}</b><small>${esc(o.detalle || '')}</small>${o.leida ? '<em class="m-leida">' + FGM_ICO('eye') + ' Ya la usaste</em>' : ''}</button>`).join('')}</div>
    <div class="m-ejecucion"></div>`;
  S.silbato(1, 0.2);
  let elegida = p.mi_eleccion;
  if (!elegida) {
    elegida = await new Promise(ok => {
      const t = setTimeout(() => ok(penal ? (ataco ? 'izq' : 'centro') : opciones[ataco ? 0 : opciones.length - 1].clave), 14000);
      caja.querySelectorAll('.m-op').forEach(b => b.onclick = () => { clearTimeout(t); ok(b.dataset.c); });
    });
    try { await accion('elegir', {eleccion: elegida}); } catch {}
  }
  caja.classList.add('revelado');
  caja.querySelectorAll('.m-op').forEach(x => x.classList.toggle('elegida', x.dataset.c === elegida));
  const cont = caja.querySelector('.m-ejecucion');
  cont.innerHTML = '<p class="m-revela">Esperando que tu rival elija…</p>';
  const q = await esperarHasta(x => x.prep, p);
  if (!q || q.minuto !== p.minuto || q.tiempo !== p.tiempo || !q.prep) {   // ya se resolvió (penal): sigue el partido
    if (penal) { cont.innerHTML = '<p class="m-revela">¡Se patea!</p>'; await espera(900); }
    cerrarModal(); return;
  }
  const prep = q.prep;
  const mia = ataco ? prep.nombre_ataque : prep.nombre_defensa, suya = ataco ? prep.nombre_defensa : prep.nombre_ataque;
  cont.innerHTML = `<p class="m-revela">Tú: <b>${esc(mia || NOMBRE[elegida] || elegida)}</b> · Rival: <b>${esc(suya || '')}</b></p><div class="m-pulso"></div>`;
  if (prep.pulso === false) {   // penal: gana el lado
    const bien = ataco ? prep.gol !== false : prep.gol === false;
    const txt = ataco ? (bien ? '¡Lo mandaste al otro lado!' : '¡Te la atajó!') : (bien ? '¡La atajaste!' : 'Te tiraste al otro lado…');
    cont.insertAdjacentHTML('beforeend', `<p class="pu-fin ${bien ? 'ok' : 'mal'}">${txt}</p>`);
    await espera(1300);
    cerrarModal(); return;
  }
  await espera(600);
  await pulso(cont.querySelector('.m-pulso'), prep, async (r, mia) => {
    try { await accion('toque', {ronda: r, precision: mia}); } catch {}
    const x = await esperarHasta(z => !z.prep || (z.toques_rival || []).length > r, p);
    return x && x.toques_rival && x.toques_rival.length > r ? x.toques_rival[r] : 0.1;
  }, {esperando: 'Esperando el toque de tu rival…'});
  cerrarModal();
}
function cerrarModal() { modal.hidden = true; caja.className = 'modal-caja'; estado.set({bloqueado: terminado}); }

// ---------- reacciones (emojis que le llegan al rival)
const EMOJIS = ['😂', '🔥', '😱', '👏', '😤', '🫡'];
$('reacciones').innerHTML = EMOJIS.map(e => `<button data-e="${e}">${e}</button>`).join('');
$('reacciones').onclick = async ev => {
  const b = ev.target.closest('[data-e]'); if (!b) return;
  lluvia(b.dataset.e, true);
  try { await accion('reaccion', {emoji: b.dataset.e}); } catch {}
};
function lluvia(emoji, mia) {
  const el = document.createElement('span');
  el.className = 'gota' + (mia ? ' mia' : '');
  el.textContent = emoji;
  el.style.left = (mia ? 8 + Math.random() * 30 : 62 + Math.random() * 30) + '%';
  $('lluvia').appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

// ---------- final: copas (partido por copas) o revancha (amistoso)
function pintarRevancha() {
  const r = ult && ult.revancha, b = $('revancha');
  if (!r || !b) return;
  if (r.yo) { b.disabled = true; b.textContent = r.rival ? 'Armando…' : 'Esperando que acepte…'; }
  else if (r.rival) { b.textContent = '¡Te pide revancha! Aceptar'; b.classList.add('latiendo'); }
}
function terminar() {
  if (terminado) return;
  terminado = true;
  estado.set({terminado: true, bloqueado: true, goles: [...ult.marcador]});
  S.silbato(3); S.ambiente(false);
  const mio = ult.marcador[D.lado], suyo = ult.marcador[1 - D.lado];
  ctx.cancha.anunciar(`<b>${mio > suyo ? '¡Ganaste!' : mio === suyo ? 'Empate' : 'Perdiste'}</b><span>${ult.marcador[0]} - ${ult.marcador[1]}</span>`,
    'final ' + (mio > suyo ? 'gana' : mio === suyo ? 'empata' : 'pierde'), 3500);
  if (mio > suyo) confeti(120);
  const post = $('post');
  post.hidden = false;
  if (ult.escalera) {
    const e = ult.escalera;
    post.innerHTML = `<p class="vv-copas"><b>${e.delta >= 0 ? '+' : ''}${e.delta} ${FGM_ICO('copa')}</b> · ${e.copas} copas · ${FGM_ICO('moneda')} +${e.monedas}${e.sube ? ' · ¡Subiste de cancha!' : ''}${e.sobre ? ' · ganaste un sobre' : ''}</p>
      <a class="boton primario" href="/escalera/buscar">${FGM_ICO('swords')} Otro partido</a><a class="boton" href="/">Inicio</a>`;
    return;
  }
  post.innerHTML = `<button class="primario" id="revancha">${FGM_ICO('repeat-2')} Revancha</button><a class="boton" href="/amistosos">Salir</a>`;
  $('revancha').onclick = async () => {
    try { const r = await accion('revancha'); if (r.partido) location.href = `/vivo/${r.partido}`; } catch (e) { toast(e.message, {error: true}); }
    $('revancha').disabled = true;
  };
  setInterval(pedir, 1500);   // por si el rival pide revancha
}

// ---------- interfaz (Preact)
const acciones = {
  pedirTactica: async valor => {
    try { await accion('tactica', {valor}); toast(`Táctica: ${D.tacticas[valor].nombre}`); pedir(); }
    catch (e) { toast(e.message, {error: true}); }
  },
  pedirPausa: () => {}, velocidad: () => {}, saltar: () => {},
};
const montar = (id, vista) => { const el = $(id); if (el) render(vista, el); };
montar('ui-numeros', html`<${Numeros} estado=${estado}/>`);
montar('ui-controles', html`<${Controles} estado=${estado} D=${{...D, modo: 'pvp'}} acciones=${acciones}/>`);
montar('ui-relato-actual', html`<${RelatoActual} estado=${estado}/>`);
montar('ui-tacticas', html`<${Tacticas} estado=${estado} D=${{...D, espera_tactica: 0}} acciones=${acciones}/>`);
montar('ui-indicadores', html`<${Indicadores} estado=${estado} D=${D}/>`);
montar('ui-relato', html`<${RelatoTodo} estado=${estado}/>`);

ctx.cancha.formar(-1, 1, 0);
conectar();
(async () => { await espera(300); await pedir(); estado.set({bloqueado: false}); reproducir(); })();
