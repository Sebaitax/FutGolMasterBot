// Pantalla "VS" al empezar un partido: los dos escudos frente a frente sobre el estadio, ~2 segundos.
// Sale una sola vez por partido (si recargas a mitad del partido, no vuelve a salir).
(() => {
  const clave = 'fgm_vs_' + location.pathname;
  try { if (sessionStorage.getItem(clave)) return; sessionStorage.setItem(clave, '1'); } catch { /* sin storage: igual se muestra */ }
  const equipos = [...document.querySelectorAll('.marcador-vivo .mv-equipo')];
  if (equipos.length !== 2) return;
  const lugar = document.querySelector('.marcador-vivo .mv-estadio');
  const lado = (el, cual) => {
    const img = el.querySelector('img, svg, .escudo');
    const nombre = el.querySelector('span') ? el.querySelector('span').textContent : '';
    const div = document.createElement('div');
    div.className = 'vs-equipo ' + cual;
    if (img) div.appendChild(img.cloneNode(true));
    const b = document.createElement('b'); b.textContent = nombre; div.appendChild(b);
    return div;
  };
  const capa = document.createElement('div');
  capa.className = 'vs-capa';
  capa.setAttribute('aria-hidden', 'true');
  const centro = document.createElement('div');
  centro.className = 'vs-centro';
  centro.innerHTML = '<i>VS</i>';
  const fila = document.createElement('div');
  fila.className = 'vs-fila';
  fila.append(lado(equipos[0], 'izq'), centro, lado(equipos[1], 'der'));
  capa.appendChild(fila);
  if (lugar) {
    const pie = document.createElement('p');
    pie.className = 'vs-lugar';
    pie.innerHTML = lugar.innerHTML;   // insignia, cancha y bandera (HTML propio de la página)
    pie.querySelectorAll('#apuesta, #conexion').forEach(n => n.remove());
    capa.appendChild(pie);
  }
  document.body.appendChild(capa);
  const cerrar = () => { capa.classList.add('fuera'); setTimeout(() => capa.remove(), 450); };
  capa.addEventListener('click', cerrar);
  setTimeout(cerrar, 2300);
})();
