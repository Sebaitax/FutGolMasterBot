// Componentes compartidos: cartas HTML, escudos, utilidades de animación.
window.FGM = (() => {
  const LINEA = {GK:'POR', CB:'DEF', LB:'DEF', RB:'DEF', LWB:'DEF', RWB:'DEF', CDM:'MED', CM:'MED', CAM:'MED', LM:'MED', RM:'MED', LW:'DEL', RW:'DEL', ST:'DEL', CF:'DEL'};
  const ORDEN = ['POR', 'DEF', 'MED', 'DEL'];
  const ETQ = {PAC:'VEL', SHO:'TIR', PAS:'PAS', DRI:'REG', DEF:'DEF', PHY:'FIS'};
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const linea = p => LINEA[p] || 'MED';
  const pos = p => (window.FGM_POS || {})[p] || p;  // código en inglés -> abreviatura en español
  const nivel = ovr => ovr >= 75 ? 'oro' : ovr >= 65 ? 'plata' : 'bronce';
  function afinidad(nat, puesto) {
    if (nat === puesto) return 1;
    const a = linea(nat), b = linea(puesto);
    if (a === 'POR' || b === 'POR') return 0.25;
    if (a === b) return 0.92;
    return Math.abs(ORDEN.indexOf(a) - ORDEN.indexOf(b)) === 1 ? 0.8 : 0.65;
  }
  function slug(n) {
    return String(n).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }
  const ALIAS = window.FGM_ESCUDO_ALIAS || {};  // viene del servidor (web/app.py)
  // url del escudo (el servidor dice cuáles existen en window.FGM_ESCUDOS)
  function escudoUrl(club) {
    const s = ALIAS[slug(club)] || slug(club);
    return (window.FGM_ESCUDOS || []).includes(s) ? `/escudos/${s}.png` : null;
  }
  function escudo(club, clase = '') {
    const url = escudoUrl(club);
    if (url) return `<img class="escudo ${clase}" src="${url}" alt="">`;
    const ini = (String(club).match(/\p{L}{3,}/gu) || [club]).slice(0, 3).map(w => w[0]).join('').toUpperCase();
    const tono = [...String(club)].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
    return `<span class="escudo propio ${clase}" style="--tono:${tono}">${esc(ini)}</span>`;
  }

  // Bandera del país del jugador (imagen de flagcdn; los emoji de banderas no se ven en Windows)
  const ISO = {'Angola':'ao','Argentina':'ar','Armenia':'am','Brasil':'br','Bélgica':'be','Cabo Verde':'cv','Camerún':'cm',
    'Chile':'cl','Colombia':'co','Dinamarca':'dk','Ecuador':'ec','Eslovenia':'si','España':'es','Estados Unidos':'us',
    'Guinea':'gn','Guinea-Bisáu':'gw','Inglaterra':'gb-eng','Italia':'it','Japón':'jp','Marruecos':'ma','México':'mx',
    'Panamá':'pa','Paraguay':'py','Países Bajos':'nl','Perú':'pe','Portugal':'pt','Puerto Rico':'pr','RD del Congo':'cd',
    'Siria':'sy','Suiza':'ch','Uruguay':'uy','Venezuela':'ve','Francia':'fr','Alemania':'de','Bolivia':'bo','Costa Rica':'cr',
    'Honduras':'hn','Haití':'ht','Nigeria':'ng','Ghana':'gh','Senegal':'sn','Croacia':'hr','Serbia':'rs','Grecia':'gr'};
  const nacionTitulo = n => String(n || '').toLowerCase().replace(/(^|[\s-])\p{L}/gu, m => m.toUpperCase());
  function bandera(nacion, clase = '') {
    const iso = ISO[nacion] || ISO[nacionTitulo(nacion)];
    return iso ? `<img class="bandera ${clase}" src="https://flagcdn.com/w40/${iso}.png" alt="${esc(nacion)}" title="${esc(nacion)}" loading="lazy" onerror="this.remove()">` : '';
  }

  // Carta HTML. f: {pid?, nombre, pos, ovr, nivel?, club, estado?, lesion?}
  // opts: {puesto, quimica (0..1), grande, extra (html), atrib}
  function carta(f, opts = {}) {
    const nv = f.nivel || nivel(f.ovr);
    const af = opts.puesto ? afinidad(f.pos, opts.puesto) : 1;
    const fuera = f.estado && f.estado !== 'disponible';
    let marca = '';
    if (fuera) marca = `<i class="marca mal" title="${f.estado}">${f.lesion ? '🚑' : '🟥'}</i>`;
    else if (af < 1) marca = `<i class="marca ${af < 0.9 ? 'mal' : 'medio'}" title="Rinde ${Math.round(af * 100)}% en este puesto">${Math.round(af * 100)}%</i>`;
    const q = opts.quimica;
    const anillo = q === undefined ? '' : `<i class="quim q${q >= 0.75 ? 3 : q >= 0.4 ? 2 : q > 0 ? 1 : 0}" title="Química ${Math.round(q * 100)}">${'◆'.repeat(q >= 0.75 ? 3 : q >= 0.4 ? 2 : q > 0 ? 1 : 0) || '◇'}</i>`;
    const esc_ = (f.club ? `<span class="m-club" title="${esc(f.club)}">${escudo(f.club)}</span>` : '')
      + (f.nacion && !opts.sinBandera ? `<span class="m-nac">${bandera(f.nacion)}</span>` : '');
    return `<div class="mini ${nv}${fuera ? ' fuera' : ''}${opts.grande ? ' grande' : ''}" ${f.pid ? `data-pid="${f.pid}"` : ''} ${opts.atrib || ''}>
      <b class="m-ovr">${f.ovr}${f.mejora > 1 ? `<i class="m-plus" title="Mejorada: +${f.mejora - 1} sobre su media base">+${f.mejora - 1}</i>` : ''}</b><span class="m-pos">${esc(pos(f.pos))}</span>${f.mejora > 1 ? `<i class="m-mejora" title="Nivel ${f.mejora}: +${f.mejora - 1} de media">${'★'.repeat(f.mejora - 1)}</i>` : ''}${esc_}
      ${f.render ? `<img class="m-render" src="${f.render}" alt="" loading="lazy">` : '<span class="m-silueta"></span>'}
      <span class="m-nombre">${esc(f.nombre)}</span>${marca}${anillo}${opts.extra || ''}</div>`;
  }

  // Objeto de colección (escudo o estadio). grande = versión para la apertura de sobres
  function objeto(o, grande = false) {
    const img = o.imagen ? `<img src="${o.imagen}" alt="" loading="lazy">` : `<span class="obj-sin">${o.tipo === 'escudo' ? '🛡️' : '🏟️'}</span>`;
    return `<div class="objeto tipo-${o.tipo} ${o.nivel} ${grande ? 'grande' : ''} ${o.tengo === false ? 'falta' : ''}" data-oid="${o.id}">
      <div class="obj-img">${img}</div>
      <span class="obj-tipo">${o.tipo === 'escudo' ? 'ESCUDO' : 'ESTADIO'}</span>
      <span class="obj-nombre">${esc(o.tipo === 'escudo' ? o.club : o.nombre)}</span>
      ${o.en_uso ? '<i class="obj-uso">EN USO</i>' : ''}${o.nuevo ? '<i class="obj-nuevo">NUEVO</i>' : ''}</div>`;
  }

  function reanimar(el, clase) { el.classList.remove(clase); void el.offsetWidth; el.classList.add(clase); }

  // Cuenta animada de un número (monedas, puntos)
  function contar(el, hasta, ms = 1200, desde = 0) {
    const t0 = performance.now();
    const paso = t => {
      const k = Math.min(1, (t - t0) / ms), v = Math.round(desde + (hasta - desde) * (1 - Math.pow(1 - k, 3)));
      el.textContent = v.toLocaleString('es-CL');
      if (k < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
  }

  // Confeti simple con divs
  function confeti(n = 80) {
    const caja = document.createElement('div');
    caja.className = 'confeti';
    const colores = ['#2fbf71', '#e3b947', '#e5534b', '#4aa3df', '#ffffff'];
    for (let i = 0; i < n; i++) {
      const c = document.createElement('i');
      c.style.left = Math.random() * 100 + 'vw';
      c.style.background = colores[i % colores.length];
      c.style.animationDelay = Math.random() * 0.8 + 's';
      c.style.animationDuration = 2 + Math.random() * 1.5 + 's';
      c.style.transform = `rotate(${Math.random() * 360}deg)`;
      caja.appendChild(c);
    }
    document.body.appendChild(caja);
    setTimeout(() => caja.remove(), 4500);
  }

  function toast(msg, opts = {}) {
    let t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
    t.innerHTML = esc(msg) + (opts.accion ? ` <button class="toast-btn">${esc(opts.accion)}</button>` : '');
    t.className = 'toast visible' + (opts.error ? ' error' : '');
    if (opts.accion) t.querySelector('.toast-btn').onclick = () => { t.className = 'toast'; opts.alHacer(); };
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.className = 'toast', opts.ms || 1800);
  }

  async function api(url, cuerpo) {
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo || {})});
    const j = await r.json().catch(() => ({error: 'Error del servidor'}));
    if (!r.ok) throw new Error(j.error || 'Error');
    return j;
  }

  function monedas(n) {
    const el = document.getElementById('monedas');
    if (!el) return;
    const antes = +el.dataset.valor || 0;
    el.dataset.valor = n;
    contar(el.querySelector('b'), n, 700, antes);
    document.querySelectorAll('.menu-monedas b').forEach(b => contar(b, n, 700, antes));
    reanimar(el, 'pulso');
  }

  return {objeto, LINEA, ETQ, esc, linea, pos, nivel, afinidad, escudo, escudoUrl, bandera, carta, reanimar, contar, confeti, toast, api, monedas};
})();
