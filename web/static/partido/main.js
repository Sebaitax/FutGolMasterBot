// Pantalla del partido (contra la máquina, en vivo o repetición). Junta los módulos:
//   estado.js      estado compartido (lo que se ve) + hook para Preact
//   ui.js          componentes Preact: marcador, controles, tácticas, indicadores, relato
//   cancha.js      cancha animada (fichas y pelota)
//   pausas.js      jugadas clave, penal, expulsión, entretiempo
//   reproductor.js reproducción minuto a minuto y comunicación con el servidor
import {html, render} from '../vendor/preact-htm.js';
import {crearEstado} from './estado.js';
import {Numeros, Controles, Tacticas, Indicadores, RelatoActual, RelatoTodo} from './ui.js';
import {crearCancha} from './cancha.js';
import {crearPausas} from './pausas.js';
import {crearReproductor} from './reproductor.js';

const D = JSON.parse(document.getElementById('datos').textContent);
const S = window.FGM_SONIDO;
const RITMO = 1.8;   // x1 = ritmo cómodo de ver (x2 y x4 solo en repeticiones)

const flags = {saltando: false, velocidad: 1, enJugada: false};
const T = ms => ms * RITMO / flags.velocidad;
const ctx = {
  D, S, flags, T,
  dormir: ms => flags.saltando ? Promise.resolve() : new Promise(r => setTimeout(r, T(ms))),
  estado: crearEstado({
    goles: [0, 0], golAnim: [0, 0], reloj: {t: 1, m: 0}, descanso: false, pos: [50, 50], prob: null,
    dominio: [], etX: null, relato: [], actual: null, velocidad: 1, terminado: false, bloqueado: true,
    tactica: 'normal', tactica_rival: 'normal', rival_desde: null, pendiente: null, pidiendoPausa: false,
    pausas_restantes: D.pausas_max || 0, cambios_restantes: 5, ultima_tactica: null,
  }),
};
ctx.cancha = crearCancha(ctx);
ctx.pausas = crearPausas(ctx);
const reproductor = crearReproductor(ctx);

const acciones = {
  pedirTactica: valor => reproductor.pedir({tipo: 'tactica', valor}),
  pedirPausa: () => reproductor.pedir({tipo: 'pausa'}),
  velocidad: v => { flags.velocidad = v; ctx.estado.set({velocidad: v}); },
  saltar: () => reproductor.saltar(),
};
const montar = (id, vista) => { const el = document.getElementById(id); if (el) render(vista, el); };
montar('ui-numeros', html`<${Numeros} estado=${ctx.estado}/>`);
montar('ui-controles', html`<${Controles} estado=${ctx.estado} D=${D} acciones=${acciones}/>`);
montar('ui-relato-actual', html`<${RelatoActual} estado=${ctx.estado}/>`);
if (D.modo === 'vivo') montar('ui-tacticas', html`<${Tacticas} estado=${ctx.estado} D=${D} acciones=${acciones}/>`);
montar('ui-indicadores', html`<${Indicadores} estado=${ctx.estado} D=${D}/>`);
montar('ui-relato', html`<${RelatoTodo} estado=${ctx.estado}/>`);

reproductor.iniciar();
