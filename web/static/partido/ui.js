// Interfaz del partido con Preact (htm): lo que muestra datos y cambia con el estado.
// La cancha animada y los minijuegos siguen siendo código directo (cancha.js, pausas.js).
import {html, useState} from '../vendor/preact-htm.js';
import {usarEstado, absoluto} from './estado.js';

const {esc} = window.FGM;

// ---------- goles y reloj (dentro del marcador)
export function Numeros({estado}) {
  const e = usarEstado(estado);
  const {t, m} = e.reloj;
  const lim = t === 1 ? 45 : 90;
  return html`
    <div class="mv-goles">
      ${[0, 1].map(i => html`${i === 1 ? html`<i>-</i>` : ''}<b key=${'g' + i + '-' + e.golAnim[i]} class=${Date.now() - e.golAnim[i] < 1500 ? 'golazo' : ''}>${e.goles[i]}</b>`)}
    </div>
    <div class="mv-reloj"><span>${m > lim ? `${lim}+${m - lim}'` : `${m}'`}</span><small>${e.descanso ? 'ET' : t === 1 ? '1T' : '2T'}</small></div>`;
}

// ---------- controles: pausa para cambios, velocidad y saltar (solo repeticiones), sonido
export function Controles({estado, D, acciones}) {
  const e = usarEstado(estado);
  const vivo = D.modo === 'vivo', repeticion = D.modo === 'repeticion';
  const S = window.FGM_SONIDO;
  const [, refrescar] = useState(0);
  const sonido = !S.activo ? 'volume-x' : S.bloqueado() ? 'volume-1' : 'volume-2';
  const tocarSonido = () => {
    if (S.activo && S.bloqueado()) S.silbato(1, 0.15); else { S.alternar(); if (!S.activo) S.ambiente(false); }
    setTimeout(() => refrescar(x => x + 1), 150);
  };
  const sinCambios = e.cambios_restantes <= 0;
  return html`
    ${vivo && html`<button class="chico-btn" disabled=${e.bloqueado || e.pausas_restantes <= 0 || sinCambios || e.pidiendoPausa}
        onClick=${acciones.pedirPausa}>
        ${e.pidiendoPausa ? 'Pausando…' : sinCambios ? 'Sin cambios' : `Cambios (${e.pausas_restantes})`}</button>`}
    ${repeticion && html`<div class="velocidad">${[1, 2, 4].map(v => html`
        <button class=${e.velocidad === v ? 'activo' : ''} onClick=${() => acciones.velocidad(v)}>x${v}</button>`)}</div>`}
    <button class=${'chico-btn' + (S.activo && !S.bloqueado() ? ' activo' : '') + (S.activo && S.bloqueado() ? ' latiendo' : '')}
      title="Sonido" onClick=${tocarSonido} onPointerDown=${() => setTimeout(() => refrescar(x => x + 1), 150)}><span class="ico-envoltura" dangerouslySetInnerHTML=${{__html: FGM_ICO(sonido)}}></span>${S.activo && S.bloqueado() ? ' Toca para activar' : ''}</button>
    ${repeticion && !e.terminado && html`<button class="enlace" onClick=${acciones.saltar}>Saltar</button>`}`;
}

// ---------- tácticas en vivo (con la guía de qué le gana a qué)
export function Tacticas({estado, D, acciones}) {
  const e = usarEstado(estado);
  const [guia, setGuia] = useState(false);
  if (e.terminado) return null;
  const ahora = absoluto(e.reloj.t, e.reloj.m);
  const espera = e.ultima_tactica ? Math.max(0, absoluto(...e.ultima_tactica) + D.espera_tactica - ahora) : 0;
  const pierdeCon = k => Object.keys(D.vence).find(x => D.vence[x] === k);
  const leyendo = e.rival_desde != null && ahora - e.rival_desde < D.minutos_lectura;
  const rival = D.tacticas[e.tactica_rival];
  const leGanas = !leyendo && D.vence[e.tactica] === e.tactica_rival;
  const teGana = !leyendo && D.vence[e.tactica_rival] === e.tactica;
  const textoRival = leyendo ? 'Rival: cambió algo… leyéndolo'
    : rival && e.tactica_rival !== 'normal' ? `Rival: ${rival.nombre}${leGanas ? ' · ¡le ganas!' : teGana ? ' · te está ganando' : ''}` : '';
  return html`
    <div class="tacticas">
      <div class="t-cab"><b>Táctica</b>
        <small class="tenue">${espera ? `· podrás cambiarla en ${espera}'` : ''}</small>
        <small class=${'t-rival' + (leyendo ? ' leyendo' : '') + (leGanas ? ' contra' : '') + (teGana ? ' contrado' : '')}>${textoRival}</small>
        <button class="t-ayuda enlace" type="button" onClick=${() => setGuia(!guia)}>${guia ? 'Cerrar guía' : '¿Cuál le gana a cuál?'}</button>
      </div>
      ${guia && html`<div class="t-guia" dangerouslySetInnerHTML=${{__html: window.FGM.guiaTacticas(D.tacticas, D.vence)}}></div>`}
      <div class="t-chips">${Object.entries(D.tacticas).map(([k, t]) => {
        const vence = D.vence[k] && D.tacticas[D.vence[k]], pierde = pierdeCon(k) && D.tacticas[pierdeCon(k)];
        const ayuda = t.ayuda + (vence ? `\nLe gana a ${vence.nombre} · pierde con ${pierde.nombre}.` : '\nNeutra: no le gana ni pierde con nadie.');
        return html`<button class=${'t-chip' + (e.tactica === k ? ' activo' : '') + (e.pendiente === k ? ' pendiente' : '')}
            title=${ayuda} disabled=${e.bloqueado || espera || e.tactica === k} onClick=${() => acciones.pedirTactica(k)}>
            <span class="ico-envoltura" dangerouslySetInnerHTML=${{__html: FGM_ICOTXT(t.ico)}}></span>${t.nombre}${vence && html`<small class="t-vence">› <span class="ico-envoltura" dangerouslySetInnerHTML=${{__html: FGM_ICOTXT(vence.ico)}}></span></small>`}</button>`;
      })}</div>
    </div>`;
}

// ---------- probabilidad, dominio minuto a minuto y posesión
export function Indicadores({estado, D}) {
  const e = usarEstado(estado);
  const nombres = [D.local, D.visita], C = D.colores || ['#f4f6f8', '#e5534b'];
  const p = e.prob;
  const pv = p ? Math.max(0, 100 - p.pg - p.pe) : 0;
  return html`
    ${p && html`<div class="prob">
      <div class="prob-barra"><i style=${{width: p.pg + '%', background: C[0]}}></i><i style=${{width: p.pe + '%'}}></i><i style=${{width: pv + '%', background: C[1]}}></i></div>
      <div class="prob-txt"><span>${nombres[0]} ${p.pg}%</span><span>Empate ${p.pe}%</span><span>${pv}% ${nombres[1]}</span></div>
    </div>`}
    <div class="momentum-caja">
      <svg class="momentum" viewBox="0 0 100 40" preserveAspectRatio="none" aria-label="Dominio minuto a minuto">
        <line x1="0" y1="20" x2="100" y2="20" class="mo-eje"/>
        ${e.etX != null && html`<line x1=${e.etX} y1="0" x2=${e.etX} y2="40" class="mo-et"/>`}
        ${e.dominio.map((b, i) => html`<rect key=${i} x=${b.x} y=${b.y} width="0.8" height=${b.h} fill=${C[b.eq]} class=${'mo-b' + (b.gol ? ' gol' : '')}/>`)}
      </svg>
      <div class="mo-pie"><span>${e.pos[0]}%</span><small>posesión</small><span>${e.pos[1]}%</span></div>
    </div>`;
}

// ---------- relato: la última jugada arriba y el historial plegado
const formato = t => FGM_ICOTXT(esc(t)).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
export function RelatoActual({estado}) {
  const {actual} = usarEstado(estado);
  if (!actual) return html`<div class="relato-actual" aria-live="polite"></div>`;
  return html`<div key=${actual.n} class=${`relato-actual cambia ${actual.tipo}${actual.propio ? ' propio' : ''}`} aria-live="polite">
    ${actual.minuto && html`<b>${actual.minuto}</b>`}<span dangerouslySetInnerHTML=${{__html: formato(actual.texto)}}></span></div>`;
}
export function RelatoTodo({estado}) {
  const {relato} = usarEstado(estado);
  return html`<details class="relato-todo"><summary>Relato completo</summary>
    <ol class="relato">${relato.map(l => html`<li key=${l.n} class=${`linea entra ${l.tipo}${l.propio ? ' propio' : ''}`}>
      ${l.minuto && html`<b>${l.minuto}</b>`}<span dangerouslySetInnerHTML=${{__html: formato(l.texto)}}></span></li>`)}</ol></details>`;
}
