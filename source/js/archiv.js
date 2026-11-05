// Homepage archive: Personen index + Karteikarte, Orte map (Leaflet, loaded on demand).
// Rewrite of the old theme's custom.js; the data is embedded in the page (#archiv-data)
// instead of being parsed from CSV files in the browser.
(() => {
  const dataEl = document.getElementById('archiv-data');
  if (!dataEl) return;
  const { personen, orte } = JSON.parse(dataEl.textContent);
  const leafletBase = document.currentScript.dataset.leaflet;
  const $ = (id) => document.getElementById(id);

  const TILES = 'https://api.mapbox.com/styles/v1/ostblok/ckystbg712l0c14oa0ei616d1/tiles/256/{z}/{x}/{y}@2x?access_token=pk.eyJ1Ijoib3N0YmxvayIsImEiOiJja3MwaWphcWIxa2kzMnVuODE4cnJ4MmU0In0.RBP3Vl0eQHgetavG-P0c8A';
  const ATTRIBUTION = '<a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noopener">&copy; Mapbox</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap</a>';
  const ARROW = '<svg class="svgArrow" viewBox="0 0 75 25" fill="none" stroke="#000" stroke-miterlimit="10" aria-hidden="true"><line x1="1.4" y1="12.6" x2="74" y2="12.6"/><polyline points="62,0.5 74,12.6 62,24.7"/></svg>';
  const OUTLINE = Array.from({ length: 20 }, (_, i) => String.fromCodePoint(0x2460 + i)); // ① ② ③ …
  const FILLED = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x2776 + i))   // ❶ ❷ ❸ …
    .concat(Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x24eb + i)));

  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  };
  const smoothTo = (node) => node && node.scrollIntoView({ behavior: 'smooth' });
  const activate = (node, fn) => {
    node.addEventListener('click', fn);
    node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); } });
  };
  const articleLink = (a) => {
    const t = el(a.href ? 'a' : 'span', 'artikelTitel', a.title);
    if (a.href) t.href = a.href;
    return t;
  };
  const tags = (container, names, href, onPick) => {
    container.textContent = '';
    names.forEach((name) => {
      const tag = el('a', 'tags', name);
      tag.href = href;
      tag.addEventListener('click', (e) => { e.preventDefault(); onPick(name); });
      container.append(tag);
    });
  };

  // =========================================================== Personen
  const namen = personen.map((p) => p.name);
  const liste = $('personenListe');
  const dropdown = $('dropdownP');
  const fade = $('pGrad');
  const spacer = $('spacer');

  if (dropdown) {
    let open = false;
    dropdown.setAttribute('role', 'button');
    dropdown.tabIndex = 0;
    activate(dropdown, () => {
      open = !open;
      liste.style.height = open ? 'auto' : '300px';
      liste.style.overflow = open ? 'visible' : 'hidden';
      dropdown.textContent = open ? 'weniger anzeigen' : 'mehr anzeigen';
      fade.style.display = open ? 'none' : 'block';
    });
  }

  function showPerson(i) {
    const p = personen[i];
    if (!p) return;
    $('portrait').style.backgroundImage = `url(${p.portrait})`;
    $('portrait').setAttribute('aria-label', p.name);
    $('nameW').innerHTML = p.name;
    $('jahr').innerHTML = p.jahr;
    $('text').innerHTML = p.text;

    const box = $('artikelContainer');
    box.textContent = '';
    const rows = [el('div', 'artikelWrap'), el('div', 'artikelWrap')];
    box.append(...rows);
    p.artikel.forEach((a, k) => {
      const item = el('div', 'artikelElement');
      item.append(articleLink(a), el('h5', 'artikelAutor', a.author));
      rows[k % 2].append(item);
    });
    if (p.artikel.length > 4) rows.forEach((r) => r.append(el('div', 'pfeil', ARROW)));
    if (p.artikel.length < 2) rows[1].style.display = 'none';

    tags($('personenContainer'), p.personen, '#personenKarte', (name) => {
      const j = namen.indexOf(name);
      if (j >= 0) { showPerson(j); smoothTo(spacer); }
    });
    tags($('orteContainer'), p.orte, '#orte', (name) => {
      smoothTo(mapHeading);
      const j = orte.findIndex((o) => o.name === name);
      if (j >= 0) openOrt(j);
    });
  }

  if (liste) {
    liste.querySelectorAll('.listenElement').forEach((item) => {
      item.tabIndex = 0;
      item.setAttribute('role', 'button');
      activate(item, () => { showPerson(+item.dataset.index); smoothTo(spacer); });
    });
  }

  // a link from an article (see "checker()" in the Thumb article) can preselect a person
  let start = 0;
  try {
    start = parseInt(sessionStorage.getItem('person'), 10) || 0;
    sessionStorage.removeItem('person');
  } catch (e) { /* storage unavailable */ }
  if ($('personenKarte')) showPerson(start);

  // =========================================================== Orte
  const mapEl = $('map');
  if (!mapEl) return;
  const mapHeading = $('content_b1a16be55') || $('orte');
  let map = null;
  let markers = [];
  let pending = null;

  function showOrtCard(i) {
    const o = orte[i];
    $('ortHeadImg').style.backgroundImage = o.img ? `url(${o.img})` : '';
    $('ortNummer').textContent = FILLED[i];
    $('ortName').innerHTML = o.name;
    $('ortText').innerHTML = o.text;

    const wrap = $('artikelWrapOrt');
    wrap.textContent = '';
    const track = el('div');
    track.id = 'artElWrap';
    o.artikel.forEach((a) => {
      const item = el('div', 'artikelElementOrt');
      item.append(articleLink(a), el('h5', 'artikelAutor', a.author));
      track.append(item);
    });
    wrap.append(track);
    if (o.artikel.length > 2) {
      const next = el('div', 'pfeil', ARROW);
      let current = 0;
      next.setAttribute('role', 'button');
      next.setAttribute('aria-label', 'Weitere Artikel');
      next.tabIndex = 0;
      activate(next, () => {
        const items = track.children;
        if (current >= items.length - 2) { current = 0; track.scrollTo(0, 0); }
        else { current += 1; track.scrollTo(items[0].offsetWidth * current, 0); }
      });
      wrap.append(next);
    }

    tags($('ortePersonenContainer'), o.personen, '#personenKarte', (name) => {
      const j = namen.indexOf(name);
      if (j >= 0) { showPerson(j); smoothTo(spacer); }
    });
  }

  function closeMarkers() {
    markers.forEach(({ node, info }) => {
      node.style.width = '80px';
      node.style.zIndex = '1';
      node.style.backgroundColor = '#202020';
      info.classList.add('menuClose');
      info.style.opacity = '0';
    });
  }

  function openOrt(i) {
    showOrtCard(i);
    if (!map) { pending = i; return; }
    closeMarkers();
    const { marker, node, info } = markers[i];
    node.style.height = '80px';
    node.style.zIndex = '100';
    node.style.backgroundColor = 'rgb(240, 232, 221)';
    info.classList.remove('menuClose');
    info.style.opacity = '1';
    node.style.width = `${info.offsetWidth + 75 * 2 + 20}px`;
    // keep the opened marker (and its label) inside the visible map area
    const p = map.latLngToContainerPoint(marker.getLatLng());
    map.setView(map.containerPointToLatLng(L.point(p.x + 200, p.y + 40)));
  }

  document.querySelectorAll('#orteliste .ortElement').forEach((item) => {
    item.tabIndex = 0;
    item.setAttribute('role', 'button');
    activate(item, () => { smoothTo(mapHeading); openOrt(+item.dataset.index); });
  });
  showOrtCard(0);

  function initMap() {
    map = L.map(mapEl, { center: [48.16556339896821, 16.367312309824765], zoom: 12, zoomControl: true });
    L.tileLayer(TILES, { attribution: ATTRIBUTION }).addTo(map);
    const icon = L.divIcon({ className: 'marker', iconSize: [80, 80] });
    markers = orte.map((o, i) => {
      const marker = L.marker([o.lat, o.lng], { icon, keyboard: true, title: o.name }).addTo(map);
      const node = marker.getElement();
      const info = el('div', 'infoText menuClose');
      info.append(el('h4', null, o.name), el('p'));
      const thumb = el('div', 'thumbWrap');
      if (o.thumb) {
        const img = el('img', 'markerThumb');
        img.src = o.thumb;
        img.alt = '';
        thumb.append(img);
      }
      node.append(info, thumb, el('div', 'number', OUTLINE[i]));
      marker.on('click', () => openOrt(i));
      return { marker, node, info };
    });
    // the map column stretches with the info card next to it; keep Leaflet's size in sync
    new ResizeObserver(() => map.invalidateSize()).observe(mapEl);
    // clicking the map itself (not a marker) collapses the open marker
    map.on('click', closeMarkers);
    if (pending != null) openOrt(pending);
  }

  function loadLeaflet() {
    return new Promise((resolve, reject) => {
      const css = el('link');
      css.rel = 'stylesheet';
      css.href = leafletBase + 'leaflet.css';
      document.head.append(css);
      const js = el('script');
      js.src = leafletBase + 'leaflet.js';
      js.onload = resolve;
      js.onerror = reject;
      document.head.append(js);
    });
  }

  // Leaflet (~150 KB) is only fetched when the map is about to scroll into view
  const io = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    io.disconnect();
    loadLeaflet().then(initMap);
  }, { rootMargin: '800px 0px' });
  io.observe(mapEl);
})();
