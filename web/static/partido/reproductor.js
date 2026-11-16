// Partido contra la máquina (o repetición): va mostrando minuto a minuto lo que simuló el servidor,
// atiende las pausas y los pedidos (táctica, pausa para cambios) y al final carga el resumen.
// ctx: {D, S, estado, flags, T, dormir, cancha, pausas}
import {clave} from './estado.js';
import {crearJugadas} from './jugadas.js';

const {api, reanimar, confeti} = window.FGM;
const espera = ms => new Promise(r => setTimeout(r, ms));

export function crearReproductor(ctx) {
  const {D, S, estado, flags} = ctx;
  const VIVO = D.modo === 'vivo';
  const J = crearJugadas(ctx);
  let lineas = [], posesion = [], iLinea = 0, iMin = 0, eventos = 0;
  let pausa = null, final = false, generacion = 0, reanudar = -1, bloqueo = -1, ahora = [1, 0];
  let pedidos = [], decidiendo = false;
  const cancha = () => ctx.cancha, pausas = () => ctx.pausas;

  // ¿se pueden tocar las tácticas y la pausa? (no con una ventana abierta, ni antes de empezar, ni al final)
  function bloquear() {
    estado.set({bloqueado: pausas().abierta() || estado.get().terminado || iMin === 0 || (final && iMin >= posesion.length),
                pidiendoPausa: pedidos.some(p => p.tipo === 'pausa'),
                pendiente: (pedidos.find(p => p.tipo === 'tactica') || {}).valor || null});
  }
  ctx.alCambiarModal = bloquear;

  function agregar(r) {
    lineas.push(...r.lineas);
    posesion = r.posesion;
    eventos = r.eventos;
    pausa = r.pausa;
    final = r.final;
    if (VIVO) {
      const cambios = {};
      for (const k of ['tactica', 'pausas_restantes', 'cambios_restantes', 'ultima_tactica']) if (k in r) cambios[k] = r[k];
      estado.set(cambios);
      bloquear();
    }
  }

  async function reproducir() {
    const gen = ++generacion;
    while (gen === generacion) {
      if (pedidos.length && iMin > 0 && !flags.saltando && clave(...ahora) > bloqueo) {
        await atenderPedido();
        if (gen !== generacion) return;
        continue;
      }
      if (iMin >= posesion.length) break;
      const min = posesion[iMin];
      const k = clave(min[0], min[1]);
      const ls = [];
      while (iLinea < lineas.length && clave(lineas[iLinea].tiempo, lineas[iLinea].min) <= k
             && !['final', 'resumen'].includes(lineas[iLinea].tipo)) ls.push(lineas[iLinea++]);
      iMin++;
      ahora = [min[0], min[1]];
      const rapido = !flags.saltando && k <= reanudar;   // recargaste la página: se pasa rápido lo ya visto
      if (rapido) flags.saltando = true;
      await J.minuto(min, ls);
      if (rapido) flags.saltando = false;
      bloquear();
    }
    if (gen !== generacion) return;
    // líneas que quedan (descanso, final): se escriben antes de la pausa o el final
    while (iLinea < lineas.length && !(['final', 'resumen'].includes(lineas[iLinea].tipo) && !final)) {
      const l = lineas[iLinea++];
      if (flags.saltando) { J.plantel(l); J.escribir(l); } else await J.efecto(l);
    }
    if (flags.saltando) cancha().estadio.classList.remove('lento');
    flags.saltando = false;
    if (pausa) { pausas().mostrar(pausa); return; }
    if (VIVO && !final) return;
    finPartido();
  }

  // ---------- pedidos en vivo: cambiar la táctica o pausar para hacer cambios (en el minuto que estás viendo)
  function pedir(ped) {
    if (ped.tipo === 'tactica') pedidos = pedidos.filter(p => p.tipo !== 'tactica');
    else if (pedidos.some(p => p.tipo === 'pausa')) return;
    pedidos.push(ped);
    bloquear();
  }
  async function atenderPedido() {
    const ped = pedidos.shift();
    const [t, m] = ahora;
    try {
      const r = await api('/api/partido/intervenir', {tiempo: t, minuto: m, tipo: ped.tipo, valor: ped.valor});
      lineas = lineas.slice(0, iLinea);  // lo que venía después cambia
      agregar(r);
      bloqueo = clave(t, m);
      if (ped.tipo === 'tactica') cancha().aviso(`🧠 ${D.tacticas[ped.valor].nombre}`, 'tactica');
    } catch (e) { window.FGM.toast(e.message, {error: true}); }
    bloquear();
  }

  // ---------- decisión de una pausa (con reintentos si se corta la red, sin aplicarla dos veces)
  async function decidir(decision) {
    if (decidiendo) return;
    decidiendo = true;
    const pendiente = pausa;
    pausas().cerrar();
    pausa = null;
    bloqueo = clave(...ahora);
    for (let intento = 0; ; intento++) {
      try {
        let r;
        if (intento === 0) r = await api('/api/partido/avanzar', {decision, desde: eventos});
        else {
          r = await api('/api/partido/avanzar', {desde: eventos});
          const sigue = r.pausa && pendiente && r.pausa.tipo === pendiente.tipo
            && r.pausa.minuto === pendiente.minuto && r.pausa.tiempo === pendiente.tiempo;
          if (sigue) r = await api('/api/partido/avanzar', {decision, desde: eventos});
        }
        agregar(r);
        break;
      } catch (e) {
        if (intento >= 5) { location.reload(); return; }   // el servidor rearma el partido tal como iba
        if (intento === 1) window.FGM_LOG && FGM_LOG({mensaje: 'reconectando partido (decisión)', tipo: 'aviso'});
        window.FGM.toast('Reconectando…', {error: true});
        await espera(1500 * (intento + 1));
      }
    }
    decidiendo = false;
    bloquear();
    reproducir();
  }
  ctx.decidir = decidir;

  async function finPartido() {
    if (estado.get().terminado) return;
    estado.set({terminado: true});
    bloquear();
    S.silbato(3); S.ambiente(false);
    const goles = estado.get().goles;
    const mio = goles[D.lado], suyo = goles[1 - D.lado];
    const res = mio > suyo ? ['¡Victoria!', 'gana'] : mio === suyo ? ['Empate', 'empata'] : ['Derrota', 'pierde'];
    cancha().anunciar(`<b>${res[0]}</b><span>${goles[0]} - ${goles[1]}</span>`, 'final ' + res[1], 3500);
    if (mio > suyo && VIVO) confeti(120);
    if (VIVO) {
      try { await api('/api/partido/avanzar', {terminar: true}); }
      catch (e) { window.FGM.toast(e.message, {error: true}); }
    }
    const html = await (await fetch(`/partido/${D.id}/resumen`)).text();
    const post = document.getElementById('post');
    post.innerHTML = html; post.hidden = false;
    reanimar(post, 'entra');
  }

  async function iniciar() {
    cancha().formar(-1, 1, 0);
    if (D.modo === 'repeticion') {
      lineas = D.lineas; posesion = D.posesion; final = true;
      if (!posesion.length) flags.saltando = true;   // partidos antiguos sin línea de posesión
    } else {
      let r;
      try { r = await api('/api/partido/avanzar', {desde: 0}); }
      catch (e) { window.FGM.toast(e.message, {error: true}); return; }
      if (r.reanudar) reanudar = clave(...r.reanudar);
      agregar(r);
    }
    reproducir();
  }

  return {iniciar, pedir, saltar: () => { flags.saltando = true; }};
}
