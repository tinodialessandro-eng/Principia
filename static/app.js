/* Principia · lógica del cliente */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);

  const body = document.body;
  const root = document.documentElement;
  const moon = $('#moon');
  const chat = $('#chat');
  const messages = $('#messages');
  const form = $('#composer');
  const input = $('#input');
  const sendBtn = $('#send');
  const fileInput = $('#file');
  const fileChip = $('#file-chip');
  const fileThumb = $('#file-thumb');
  const fileIcon = $('#file-icon');
  const fileName = $('#file-name');

  const MAX_BYTES = 15 * 1024 * 1024;
  const ALLOWED = ['image/png', 'image/jpeg', 'image/webp', 'application/pdf'];
  let selectedFile = null;
  let busy = false;

  /* ------------------------------------------------------------------ *
   * Fórmulas a tiza flotando en el fondo del chat
   * ------------------------------------------------------------------ */
  const FORMULAS = [
    'F = m·a', 'E = ½mv²', 'v = v₀ + at', 'x = x₀ + v₀t + ½at²', 'p = m·v',
    'W = F·d·cosθ', 'T² ∝ a³', 'ω = 2π/T', 'x(t) = A cos(ωt + φ)', 'F = G m₁m₂ / r²',
    'e^{iπ} + 1 = 0', 'PV = nRT', 'a = v²/r', 'E = mc²', 'λ = h/p', 'f = μN',
    '∫₀³ x² dx = 9', 'sin(π/2) = 1', 'd/dx (2x) = 2', 'Σ n = 10', '√(7² + 24²) = 25',
    'x = (−b ± √(b² − 4ac)) / 2a', 'τ = r × F', 'U = mgh', 'I = V/R'
  ];

  function spawnFormulas() {
    const bg = $('#formulas-bg');
    const count = window.innerWidth < 600 ? 18 : 30;
    for (let i = 0; i < count; i++) {
      const el = document.createElement('span');
      el.className = 'formula';
      el.textContent = FORMULAS[i % FORMULAS.length];
      el.style.left = Math.random() * 88 + '%';
      el.style.top = Math.random() * 92 + '%';
      el.style.fontSize = (1.2 + Math.random() * 1.2).toFixed(2) + 'rem';
      el.style.setProperty('--o', (0.08 + Math.random() * 0.14).toFixed(2));
      el.style.animationDuration = (10 + Math.random() * 12).toFixed(1) + 's';
      el.style.animationDelay = (-Math.random() * 14).toFixed(1) + 's';
      bg.appendChild(el);
    }
  }

  /* ------------------------------------------------------------------ *
   * Tocar la luna -> abrir el chat
   * ------------------------------------------------------------------ */
  function openChat() {
    if (body.classList.contains('is-open')) return;
    // Tanto el zoom de la portada como el círculo del chat parten del centro exacto de la luna
    const r = moon.getBoundingClientRect();
    root.style.setProperty('--ox', r.left + r.width / 2 + 'px');
    root.style.setProperty('--oy', r.top + r.height / 2 + 'px');
    chat.hidden = false;
    chat.removeAttribute('aria-hidden');
    void chat.offsetWidth; // fuerza reflow para que la transición arranque
    body.classList.add('is-open');
    setTimeout(() => {
      if (body.classList.contains('is-open')) body.classList.add('chat-ready');
      input.focus({ preventScroll: true });
    }, 950);
  }

  function closeChat() {
    body.classList.remove('chat-ready');
    void chat.offsetWidth; // restablece el clip-path antes de animar el cierre
    body.classList.remove('is-open');
    chat.setAttribute('aria-hidden', 'true');
    setTimeout(() => { if (!body.classList.contains('is-open')) chat.hidden = true; }, 950);
  }

  moon.addEventListener('click', openChat);
  $('#back').addEventListener('click', closeChat);

  /* ------------------------------------------------------------------ *
   * Archivos adjuntos
   * ------------------------------------------------------------------ */
  $('#attach').addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    if (f) setFile(f);
  });

  function setFile(f) {
    if (!ALLOWED.includes(f.type)) {
      addError('Formato no admitido. Usa PNG, JPG, WEBP o PDF.');
      return clearFile();
    }
    if (f.size > MAX_BYTES) {
      addError('El archivo supera el límite de 15 MB.');
      return clearFile();
    }
    selectedFile = f;
    fileName.textContent = f.name;
    const isImg = f.type.startsWith('image/');
    fileThumb.hidden = !isImg;
    fileIcon.hidden = isImg;
    if (isImg) fileThumb.src = URL.createObjectURL(f);
    fileChip.hidden = false;
    input.focus();
  }

  function clearFile() {
    if (fileThumb.src) URL.revokeObjectURL(fileThumb.src);
    selectedFile = null;
    fileInput.value = '';
    fileThumb.removeAttribute('src');
    fileChip.hidden = true;
  }
  $('#file-remove').addEventListener('click', clearFile);

  // Pegar una captura desde el portapapeles
  input.addEventListener('paste', (e) => {
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith('image/'));
    if (item) setFile(item.getAsFile());
  });

  /* ------------------------------------------------------------------ *
   * Entrada de texto
   * ------------------------------------------------------------------ */
  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  }
  input.addEventListener('input', autoGrow);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && window.innerWidth >= 720) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll('.chip').forEach((chip) =>
    chip.addEventListener('click', () => {
      input.value = chip.dataset.ejemplo;
      autoGrow();
      input.focus();
    })
  );

  /* ------------------------------------------------------------------ *
   * Mensajes
   * ------------------------------------------------------------------ */
  // Siempre se desplaza el contenedor del chat (nunca la página), una sola vez y sin animación
  // para que no pelee con el dedo del usuario.
  function scrollDown() {
    requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; });
  }

  // Deja la parte superior de una tarjeta larga a la vista (con un pequeño margen)
  function scrollToCard(card) {
    requestAnimationFrame(() => {
      const top = card.getBoundingClientRect().top - messages.getBoundingClientRect().top + messages.scrollTop;
      messages.scrollTop = Math.max(0, top - 8);
    });
  }

  function addUserMessage(text, file) {
    const div = document.createElement('div');
    div.className = 'bubble user';
    if (file) {
      if (file.type.startsWith('image/')) {
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.alt = 'Imagen adjunta';
        div.appendChild(img);
      } else {
        const tag = document.createElement('span');
        tag.className = 'pdf-tag';
        tag.textContent = 'PDF · ' + file.name;
        div.appendChild(tag);
      }
    }
    if (text) {
      const p = document.createElement('p');
      p.textContent = text;
      div.appendChild(p);
    }
    messages.appendChild(div);
    scrollDown();
  }

  function addLoader() {
    const div = document.createElement('div');
    div.className = 'bubble bot';
    div.innerHTML = '<span class="typing"><i></i><i></i><i></i></span><span class="typing-label">Resolviendo…</span>';
    messages.appendChild(div);
    scrollDown();
    return div;
  }

  function addError(msg) {
    const div = document.createElement('div');
    div.className = 'bubble bot error';
    const p = document.createElement('p');
    p.textContent = msg;
    div.appendChild(p);
    messages.appendChild(div);
    scrollDown();
  }

  /* ------------------------------------------------------------------ *
   * Render de la solución
   * ------------------------------------------------------------------ */
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function section(cls, title) {
    const s = el('div', 'sol-sec ' + (cls || ''));
    if (title) s.appendChild(el('h3', null, title));
    return s;
  }

  // El LaTeX llega sin delimitadores en datos/fórmulas/resultado; los añadimos aquí.
  const tex = (s) => '$' + String(s).replace(/^\$+|\$+$/g, '') + '$';

  /* ---------- Descargas (PDF y .py) ---------- */
  function slugify(t) {
    return String(t || 'ejercicio').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50) || 'ejercicio';
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  async function downloadPdf(d, btn) {
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Generando PDF…';
    try {
      const res = await fetch('/api/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(d),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.error || `Error ${res.status}`);
      }
      saveBlob(await res.blob(), `principia-${slugify(d.titulo)}.pdf`);
    } catch (err) {
      addError(err.message || 'No se pudo generar el PDF.');
    } finally {
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  function downloadPy(d) {
    saveBlob(new Blob([d.codigo], { type: 'text/x-python;charset=utf-8' }), `grafica-${slugify(d.titulo)}.py`);
  }

  async function copyText(text, btn) {
    const label = btn.textContent;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea'); // respaldo para http:// en la red local
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch { /* sin permiso */ }
      ta.remove();
    }
    btn.textContent = '¡Copiado!';
    setTimeout(() => { btn.textContent = label; }, 1600);
  }

  function button(label, cls, onClick) {
    const b = el('button', 'btn ' + cls, label);
    b.type = 'button';
    b.addEventListener('click', () => onClick(b));
    return b;
  }

  /* ---------- Tarjeta de solución ---------- */
  function renderSolution(d) {
    const card = el('article', 'bubble bot solution');
    const canExport = d.es_fisica && (d.pasos.length || d.resultado);

    const head = el('div', 'sol-head');
    if (d.tema) head.appendChild(el('span', null, d.tema));
    head.appendChild(el('h2', null, d.titulo));
    card.appendChild(head);

    if (d.aviso) card.appendChild(el('div', 'sol-warn', d.aviso));

    if (canExport) {
      const bar = el('div', 'sol-actions');
      bar.appendChild(button('⬇ Descargar PDF', 'btn-primary', (b) => downloadPdf(d, b)));
      if (d.codigo) bar.appendChild(button('⬇ Código .py', 'btn-ghost', () => downloadPy(d)));
      card.appendChild(bar);
    }

    if (d.resumen) {
      const s = section('sol-sum', 'Resumen del ejercicio');
      s.appendChild(el('p', null, d.resumen));
      card.appendChild(s);
    }

    if (d.datos.length) {
      const s = section('', 'Datos');
      const ul = el('ul', 'sol-list');
      d.datos.forEach((x) => ul.appendChild(el('li', null, tex(x))));
      s.appendChild(ul);
      card.appendChild(s);
    }

    if (d.formulas.length) {
      const s = section('', 'Fórmulas');
      const wrap = el('div', 'sol-formulas');
      d.formulas.forEach((x) => wrap.appendChild(el('div', 'sol-formula', tex(x))));
      s.appendChild(wrap);
      card.appendChild(s);
    }

    if (d.pasos.length) {
      const s = section('', 'Resolución paso a paso');
      d.pasos.forEach((p, i) => {
        const step = el('div', 'step');
        step.appendChild(el('div', 'step-n', String(i + 1)));
        const b = el('div', 'step-body');
        if (p.titulo) b.appendChild(el('strong', null, p.titulo));
        b.appendChild(el('p', null, p.explicacion));
        step.appendChild(b);
        s.appendChild(step);
      });
      card.appendChild(s);
    }

    if (d.resultado) {
      const s = section('sol-result', 'Resultado');
      s.appendChild(el('div', 'big', '$$' + d.resultado.replace(/^\$+|\$+$/g, '') + '$$'));
      card.appendChild(s);
    }

    let canvas = null;
    if (d.grafica) {
      const s = section('sol-chart', 'Gráfica');
      if (d.grafica.titulo) s.appendChild(el('div', 'chart-title', d.grafica.titulo));
      const box = el('div', 'chart-box');
      canvas = document.createElement('canvas');
      box.appendChild(canvas);
      s.appendChild(box);
      card.appendChild(s);
    }

    if (d.codigo && canExport) {
      const s = section('sol-code', 'Código Python');
      s.appendChild(el('p', 'code-hint', 'Instala con pip install numpy matplotlib y ejecútalo con python grafica.py para ver la gráfica.'));
      const pre = el('pre', 'code-box');
      pre.tabIndex = 0;
      pre.appendChild(el('code', null, d.codigo));
      s.appendChild(pre);
      const row = el('div', 'sol-actions tight');
      row.appendChild(button('Copiar código', 'btn-ghost', (b) => copyText(d.codigo, b)));
      row.appendChild(button('⬇ Descargar .py', 'btn-ghost', () => downloadPy(d)));
      s.appendChild(row);
      card.appendChild(s);
    }

    const uso = d.uso_cotidiano || {};
    if (uso.texto || (uso.ejemplos && uso.ejemplos.length)) {
      const s = section('sol-day', '🌎 En el día a día');
      if (uso.texto) s.appendChild(el('p', null, uso.texto));
      if (uso.ejemplos && uso.ejemplos.length) {
        const ul = el('ul', 'day-list');
        uso.ejemplos.forEach((x) => ul.appendChild(el('li', null, x)));
        s.appendChild(ul);
      }
      card.appendChild(s);
    }

    messages.appendChild(card);
    if (canvas) drawChart(canvas, d.grafica);
    scrollToCard(card);
    // MathJax cambia la altura al dibujar las ecuaciones: se recoloca cuando termina
    typeset(card).then(() => scrollToCard(card));
  }

  function typeset(node) {
    const run = () => (window.MathJax?.typesetPromise?.([node]) || Promise.resolve()).catch(() => {});
    if (window.MathJax?.typesetPromise) return run();
    return new Promise((resolve) => window.addEventListener('load', () => run().then(resolve), { once: true }));
  }

  /* ------------------------------------------------------------------ *
   * Gráfica interactiva (Chart.js) con paleta de tiza
   * ------------------------------------------------------------------ */
  const PALETTE = ['#f6f1e3', '#9ec5ff', '#f2c46d', '#a8dcb8', '#f08a8a'];

  function drawChart(canvas, g) {
    if (!window.Chart) return;
    Chart.defaults.color = '#c3cade';
    Chart.defaults.borderColor = 'rgba(240,232,210,.12)';

    const axis = (text) => ({ title: { display: !!text, text } });
    const common = { responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: false } };

    if (g.tipo === 'barras') {
      new Chart(canvas, {
        type: 'bar',
        data: {
          labels: g.etiquetas,
          datasets: [{
            label: g.eje_y || 'Valor',
            data: g.valores,
            backgroundColor: g.valores.map((_, i) => PALETTE[i % PALETTE.length] + 'cc'),
            borderRadius: 8,
          }],
        },
        options: { ...common, plugins: { legend: { display: false } }, scales: { x: axis(g.eje_x), y: { ...axis(g.eje_y), beginAtZero: true } } },
      });
      return;
    }

    new Chart(canvas, {
      type: 'scatter',
      data: {
        datasets: g.series.map((s, i) => ({
          label: s.nombre,
          data: s.puntos,
          showLine: true,
          spanGaps: false,
          pointRadius: 0,
          pointHoverRadius: 5,
          borderWidth: 2.5,
          tension: 0.25,
          borderColor: PALETTE[i % PALETTE.length],
          backgroundColor: PALETTE[i % PALETTE.length],
        })),
      },
      options: {
        ...common,
        plugins: { legend: { display: g.series.length > 1 } },
        scales: { x: { type: 'linear', ...axis(g.eje_x) }, y: axis(g.eje_y) },
      },
    });
  }

  /* ------------------------------------------------------------------ *
   * Envío al backend
   * ------------------------------------------------------------------ */
  function setBusy(state) {
    busy = state;
    sendBtn.disabled = state;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return;
    const texto = input.value.trim();
    if (!texto && !selectedFile) return;

    const file = selectedFile;
    addUserMessage(texto, file);

    const fd = new FormData();
    fd.append('texto', texto);
    if (file) fd.append('archivo', file);

    input.value = '';
    autoGrow();
    clearFile();
    setBusy(true);
    const loader = addLoader();

    try {
      const res = await fetch('/api/resolver', { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
      loader.remove();
      renderSolution(data);
    } catch (err) {
      loader.remove();
      addError(err.message || 'No se pudo conectar con el servidor.');
    } finally {
      setBusy(false);
    }
  });

  spawnFormulas();
})();
