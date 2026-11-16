// Música de fondo del menú (una playlist de YouTube, bajita).
// Para que la canción no se corte al cambiar de página, la música vive en un "marco"
// (/static/marco.html) que nunca se recarga, y el juego corre adentro en un iframe.
// - Si la música está prendida y no estamos en el marco, se pasa al marco una vez.
// - Adentro del marco: el botón 🎵 la prende/apaga y cada página avisa si es un partido
//   (en los partidos se pausa: ahí está el sonido del estadio).
(() => {
  const leer = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  let marco = null;
  try { marco = window.parent !== window && window.parent.FGM_MARCO; } catch { marco = null; }
  const enPartido = document.body.classList.contains('pantalla-partido');
  const aqui = location.pathname + location.search;

  let activa = marco ? marco.activa : leer('fgm_musica', ios ? '0' : '1') === '1';
  if (!marco && activa && window.parent === window) {
    // primera vez: el juego pasa a correr dentro del marco de la música
    location.replace('/static/marco.html#' + encodeURIComponent(aqui));
    return;
  }

  const boton = document.createElement('button');
  boton.className = 'musica-btn';
  boton.type = 'button';
  const pintar = () => {
    boton.textContent = activa ? '🎵' : '🔇';
    boton.title = activa ? 'Música: prendida (toca para apagar)' : 'Música: apagada (toca para prender)';
    boton.classList.toggle('apagada', !activa);
  };
  pintar();
  (document.querySelector('.barra') || document.body).appendChild(boton);
  boton.onclick = e => {
    e.stopPropagation();
    if (marco) { activa = marco.alternar(); pintar(); return; }
    // fuera del marco (estaba apagada): se prende y se pasa al marco
    try { localStorage.setItem('fgm_musica', '1'); } catch {}
    location.replace('/static/marco.html#' + encodeURIComponent(aqui));
  };

  if (marco) {
    marco.pagina({partido: enPartido, url: aqui, titulo: document.title});
    ['pointerdown', 'keydown', 'touchstart'].forEach(ev => addEventListener(ev, () => marco.toque(), {passive: true}));
  }
})();
