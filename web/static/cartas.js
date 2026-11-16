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
    if (fuera) marca = `<i class="marca mal" title="${f.estado}">${FGM_ICO(f.lesion ? 'ambulance' : 'tarjeta-roja')}</i>`;
    else if (af < 1) marca = `<i class="marca ${af < 0.9 ? 'mal' : 'medio'}" title="Rinde ${Math.round(af * 100)}% en este puesto">${Math.round(af * 100)}%</i>`;
    const q = opts.quimica;
    const anillo = q === undefined ? '' : `<i class="quim q${q >= 0.75 ? 3 : q >= 0.4 ? 2 : q > 0 ? 1 : 0}" title="Química ${Math.round(q * 100)}">${'◆'.repeat(q >= 0.75 ? 3 : q >= 0.4 ? 2 : q > 0 ? 1 : 0) || '◇'}</i>`;
    const esc_ = (f.club ? `<span class="m-club" title="${esc(f.club)}">${escudo(f.club)}</span>` : '')
      + (f.nacion && !opts.sinBandera ? `<span class="m-nac">${bandera(f.nacion)}</span>` : '');
    return `<div class="mini ${nv}${f.mejora > 1 ? ' mej' + Math.min(f.mejora, 5) : ''}${fuera ? ' fuera' : ''}${opts.grande ? ' grande' : ''}" ${f.pid ? `data-pid="${f.pid}"` : ''} ${opts.atrib || ''}>
      <b class="m-ovr">${f.ovr}${f.mejora > 1 ? `<i class="m-plus" title="Mejorada: +${f.mejora - 1} sobre su media base">+${f.mejora - 1}</i>` : ''}</b><span class="m-pos">${esc(pos(f.pos))}</span>${f.mejora > 1 ? `<i class="m-mejora" title="Nivel ${f.mejora}: +${f.mejora - 1} de media">${'★'.repeat(f.mejora - 1)}</i>` : ''}${esc_}
      ${f.render ? `<img class="m-render" src="${f.render}" alt="" loading="lazy">` : '<span class="m-silueta"></span>'}
      <span class="m-nombre">${esc(f.nombre)}</span>${f.mejora > 1 ? '<i class="m-aura"></i>' : ''}${marca}${anillo}${opts.extra || ''}</div>`;
  }

  // Objeto de colección (escudo o estadio). grande = versión para la apertura de sobres
  function objeto(o, grande = false) {
    const img = o.imagen ? `<img src="${o.imagen}" alt="" loading="lazy">` : `<span class="obj-sin">${FGM_ICO(o.tipo === 'escudo' ? 'shield' : 'estadio')}</span>`;
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
    if (r.status >= 500 && window.FGM_LOG) FGM_LOG({tipo: 'api', mensaje: j.error || 'Error del servidor', url, estado: r.status});
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

  // Filtros de liga / país / club (+ búsqueda opcional). Las opciones se cruzan entre sí y muestran cuántas cartas hay.
  function filtroCartas(cont, fichas, alCambiar, {buscar = true} = {}) {
    const CAMPOS = [['liga', 'Liga'], ['nacion', 'País'], ['club', 'Club']];
    const sel = {liga: '', nacion: '', club: ''};
    cont.classList.add('filtro-cartas');
    cont.innerHTML = (buscar ? '<input type="search" class="fc-buscar" placeholder="Buscar jugador…">' : '') +
      CAMPOS.map(([k]) => `<select data-k="${k}"></select>`).join('') +
      '<button type="button" class="fc-limpiar enlace" hidden>Limpiar</button>';
    const input = cont.querySelector('.fc-buscar'), limpiar = cont.querySelector('.fc-limpiar');
    const norm = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const pasa = (f, salvo) => CAMPOS.every(([k]) => k === salvo || !sel[k] || f[k] === sel[k]) &&
      (!input || !input.value.trim() || norm(`${f.completo || f.nombre} ${f.club} ${f.nacion}`).includes(norm(input.value.trim())));
    function refrescar() {
      const todas = fichas();
      for (const [k, etq] of CAMPOS) {
        const cuenta = {};
        for (const f of todas) if (f[k] && pasa(f, k)) cuenta[f[k]] = (cuenta[f[k]] || 0) + 1;
        if (sel[k] && !cuenta[sel[k]]) cuenta[sel[k]] = 0;
        const s = cont.querySelector(`[data-k="${k}"]`);
        s.innerHTML = `<option value="">${etq}: todas</option>` + Object.keys(cuenta).sort((a, b) => a.localeCompare(b, 'es'))
          .map(v => `<option value="${esc(v)}" ${v === sel[k] ? 'selected' : ''}>${esc(v)} (${cuenta[v]})</option>`).join('');
        s.classList.toggle('activo', !!sel[k]);
      }
      limpiar.hidden = !CAMPOS.some(([k]) => sel[k]) && !(input && input.value);
    }
    cont.addEventListener('change', e => { const k = e.target.dataset.k; if (!k) return; sel[k] = e.target.value; refrescar(); alCambiar(); });
    if (input) input.addEventListener('input', () => { refrescar(); alCambiar(); });
    limpiar.onclick = () => { for (const [k] of CAMPOS) sel[k] = ''; if (input) input.value = ''; refrescar(); alCambiar(); };
    refrescar();
    return {pasa: f => pasa(f), refrescar};
  }

  // Guía de tácticas: el ciclo de quién le gana a quién, con el porqué (partido y en vivo)
  const PORQUE = {
    presion: 'los aprietas arriba y no alcanzan a tirar el centro',
    centros: 'aunque se cierren atrás, igual les llueven centros y cabezazos',
    cuidar: 'cerrado atrás, el contragolpe no encuentra espacios',
    contragolpe: 'el rival adelantado deja la espalda libre para la contra',
  };
  function guiaTacticas(tacticas, vence) {
    const inicio = Object.keys(vence)[0];
    const ciclo = [];
    for (let k = inicio; k && !ciclo.includes(k); k = vence[k]) ciclo.push(k);
    const t = k => `<b>${FGM_ICOTXT(tacticas[k].ico)} ${esc(tacticas[k].nombre)}</b>`;
    return `<p class="tg-titulo">Cada táctica le gana a una y pierde con otra (como piedra, papel o tijera):</p>
      <ol class="tg-ciclo">${ciclo.map(k => `<li>${t(k)} <span>le gana a</span> ${t(vence[k])}
        ${PORQUE[k] ? `<small>${esc(PORQUE[k])}</small>` : ''}</li>`).join('')}</ol>
      <ul class="tg-notas">
        <li>Si le ganas a la del rival, llegas <b>+25%</b> más al arco y él <b>-15%</b>.</li>
        <li>${tacticas.normal ? t('normal') : 'Normal'} no le gana ni pierde con nadie: es la segura.</li>
        <li>Cuando el rival cambia, tardas unos minutos en "leer" su táctica nueva. Ahí es cuando conviene cambiar la tuya.</li>
        <li>En la etiqueta del rival ves si <b>le ganas</b> o si <b>te está ganando</b>.</li>
      </ul>`;
  }

  // Celebración al sacar una carta especial de un sobre: estrella (dorado) o crack (arcoíris, más grande)
  const RANGO_CALIDAD = {normal: 0, buena: 1, estrella: 2, crack: 3};
  function celebrar(calidad, nombre = '') {
    if (calidad !== 'estrella' && calidad !== 'crack') return;
    const crack = calidad === 'crack';
    const el = document.createElement('div');
    el.className = 'celebra ' + calidad;
    el.innerHTML = `<div class="celebra-luz"></div><b>${crack ? '¡CRACK!' : '¡ESTRELLA!'}</b>${nombre ? `<span>${esc(nombre)}</span>` : ''}`;
    document.body.appendChild(el);
    confeti(crack ? 220 : 90);
    if (crack) setTimeout(() => confeti(160), 500);
    const S = window.FGM_SONIDO;
    if (S) { try { S.gol(true); if (crack) setTimeout(() => S.gol(true), 700); } catch {} }
    try { navigator.vibrate && navigator.vibrate(crack ? [80, 40, 80, 40, 200] : 120); } catch {}
    setTimeout(() => el.remove(), crack ? 2600 : 1900);
  }

  return {celebrar, RANGO_CALIDAD, guiaTacticas, objeto, LINEA, ETQ, esc, linea, pos, nivel, afinidad, escudo, escudoUrl, bandera, carta, reanimar, contar, confeti, toast, api, monedas, filtroCartas};
})();
