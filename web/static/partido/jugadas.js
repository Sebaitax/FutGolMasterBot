// Cómo se ve cada minuto y cada jugada (relato, cancha, sonidos, indicadores).
// Lo comparten el partido contra la máquina (reproductor.js) y el partido en vivo entre jugadores
// (vivo.js): así los dos van al mismo ritmo y con la misma animación.
import {absoluto} from './estado.js';
import {TIROS} from './cancha.js';

const {reanimar, esc} = window.FGM;

export function crearJugadas(ctx) {
  const {D, S, estado, flags} = ctx;
  const cancha = () => ctx.cancha;
  let nLinea = 0, sonando = false, tranquilos = 0, segundoTiempo = false, n = 0;
  const cuenta = [0, 0];

  function escribir(l) {
    if (l._escrita) return;
    l._escrita = true;
    const item = {n: ++nLinea, minuto: l.minuto, texto: l.texto, tipo: l.tipo, propio: l.equipo === D.lado};
    estado.set(e => ({relato: [item, ...e.relato].slice(0, 200), actual: item,
                      ...(l.marcador && l.tipo !== 'gol' ? {goles: [...l.marcador]} : {})}));
  }
  ctx.escribir = escribir;

  // cambios en la cancha y la táctica nueva del rival (también al saltar)
  function plantel(l) {
    if (l._plantel) return;
    cancha().plantel(l);
    if (l.tipo === 'tactica' && l.equipo !== D.lado) estado.set({tactica_rival: l.tactica, rival_desde: absoluto(l.tiempo, l.min)});
    else if (l.tipo === 'gol' && flags.saltando) estado.set({goles: [...l.marcador]});
  }

  async function efecto(l) {
    const c = cancha();
    plantel(l);
    if (TIROS.includes(l.tipo)) return c.jugadaTiro(l);
    if (l.tipo === 'momento') return c.jugadaMomento(l);
    if (l.tipo === 'perdida') return c.jugadaPerdida(l);
    escribir(l);
    if (flags.saltando) return;
    if (['falta', 'amarilla', 'roja', 'penal'].includes(l.tipo)) S.silbato(1, l.tipo === 'penal' ? 0.5 : 0.28);
    if (l.tipo === 'roja') S.abucheo();
    if (l.tipo === 'descanso') { S.silbato(2); S.ambiente(false); sonando = false; }
    if (l.tipo === 'penal') { c.anunciar('<b>¡PENAL!</b>', 'penal', 1500); return c.prepararPenal(l); }
    if (l.tipo === 'amarilla') c.anunciar(`<i class="tarjeta-ico amarilla"></i><span>${esc(l.jugador)}</span>`, 'tarjeta-a', 1400);
    else if (l.tipo === 'roja') { c.anunciar(`<i class="tarjeta-ico roja"></i><b>¡Roja!</b><span>${esc(l.jugador)}</span>`, 'tarjeta-r', 1900); reanimar(c.estadio, 'sacude'); }
    else if (l.tipo === 'cambio') c.aviso(`🔄 ${l.jugador} por ${l.sale}`);
    else if (l.tipo === 'lesion') c.aviso('🚑 Lesión');
    else if (l.tipo === 'tactica') c.aviso(`🧠 ${c.nombres[l.equipo]}: ${(D.tacticas[l.tactica] || {}).nombre || ''}`, 'tactica');
    else if (l.tipo === 'falta') { c.aLaPelota(c.buscar(l.equipo, l.jugador)); c.aviso('Falta'); }
    else if (l.tipo === 'descanso') { estado.set({descanso: true}); c.anunciar('<b>Descanso</b>', 'info', 1500); c.formar(-1, 1, 900); await c.pelotaA(50, 50, 400); }
    await ctx.dormir(l.tipo === 'relleno' ? 250 : l.tipo === 'falta' ? 450 : 650);
  }

  // Un minuto de partido. Para que dure ~3 min sin acelerar: los minutos tranquilos solo mueven el reloj
  // (la jugada de pases se ve cada 6 minutos) y los remates comunes tienen una preparación corta.
  async function minuto([t, m, eq, pg, pe], ls) {
    n++;
    cuenta[eq]++;
    indicadores(t, m, eq, pg, pe, ls);
    const c = cancha();
    if (flags.saltando) { for (const l of ls) { plantel(l); escribir(l); } return; }
    if (!sonando) { sonando = true; S.silbato(1, 0.45); }   // pitazo inicial (y al volver del descanso)
    S.ambiente(true);
    const peligro = ls.some(l => TIROS.includes(l.tipo) || ['momento', 'penal', 'perdida', 'peligro', 'quite', 'corner', 'tiro_libre', 'despeje', 'pulso'].includes(l.tipo));
    if (!ls.length) {
      tranquilos++;
      if (tranquilos % 6) { c.formar(eq, 1, 420); await ctx.dormir(140); return; }   // solo avanza el reloj
      return c.circular(eq);
    }
    if (!peligro) {
      c.formar(eq, 1, 550);
      await c.pasar(c.elegir(eq, ['DEF', 'MED']), 320);
      for (const l of ls) await efecto(l);
      return;
    }
    for (const l of ls) await efecto(l);
  }

  // posesión, dominio minuto a minuto (desde el punto de vista del local) y probabilidad
  function indicadores(t, m, eq, pg, pe, ls) {
    const pct = Math.round(100 * cuenta[0] / (cuenta[0] + cuenta[1]));
    const x = Math.min(99.2, (n - 1) * 0.98);
    const mios = ls.filter(l => (l.tipo === 'atajada' ? 1 - l.equipo : l.equipo) === eq);
    const peligro = mios.some(l => TIROS.includes(l.tipo) || l.tipo === 'momento');
    const gol = mios.some(l => l.tipo === 'gol');
    const h = 19 * Math.min(1, 0.22 + (peligro ? 0.5 : 0) + (gol ? 0.28 : 0));
    const cambios = {reloj: {t, m}, pos: [pct, 100 - pct], dominio: [...estado.get().dominio, {x, y: eq === 0 ? 20 - h : 20, h, eq, gol}]};
    if (t === 2) cambios.descanso = false;
    if (t === 2 && !segundoTiempo) { segundoTiempo = true; cambios.etX = x; }
    if (pg != null) cambios.prob = {pg, pe};
    estado.set(cambios);
  }

  return {escribir, plantel, efecto, minuto};
}
