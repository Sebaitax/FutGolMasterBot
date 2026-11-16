// Marcador del partido al bajar con el dedo: se fija arriba en versión compacta (escudos, goles y minuto).
// Deja un hueco del mismo alto donde estaba, así el resto de la página no salta al hacer scroll.
(() => {
  const m = document.querySelector('.marcador-vivo');
  if (!m) return;
  const hueco = document.createElement('div');
  hueco.className = 'mv-hueco';
  m.parentNode.insertBefore(hueco, m);
  hueco.appendChild(m);
  const barra = document.querySelector('.barra');
  let fijo = false;

  function medir() {
    if (!fijo) hueco.style.height = m.offsetHeight + 'px';
  }
  function ubicar() {
    const r = hueco.getBoundingClientRect();
    m.style.left = r.left + 'px';
    m.style.width = r.width + 'px';
    m.style.top = (barra ? Math.max(0, barra.getBoundingClientRect().bottom) : 0) + 'px';
  }
  function revisar() {
    const tope = barra ? barra.getBoundingClientRect().bottom : 0;
    // se fija cuando ya pasó la mitad del marcador (y se suelta un poco antes, para que no tiemble)
    const r = hueco.getBoundingClientRect();
    const debe = fijo ? r.top + r.height * 0.5 < tope + 8 : r.top + r.height * 0.5 < tope;
    if (debe !== fijo) {
      if (debe) medir();
      fijo = debe;
      m.classList.toggle('fijo', fijo);
      if (!fijo) m.style.left = m.style.width = m.style.top = '';
    }
    if (fijo) ubicar();
  }
  medir();
  addEventListener('scroll', revisar, {passive: true});
  addEventListener('resize', () => { medir(); revisar(); });
  // el marcador puede cambiar de alto al cargar (escudos, nombres largos)
  setTimeout(medir, 600);
  revisar();
})();
