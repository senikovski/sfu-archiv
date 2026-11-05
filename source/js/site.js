// Site-wide behaviour: mobile menu, back-to-top button, reduced motion.
(() => {
  const body = document.body;

  // ---- mobile overlay menu
  const toggle = document.querySelector('.hamburger .menu-icon');
  const overlay = document.getElementById('overlay-menu');
  const setMenu = (open) => {
    overlay.hidden = !open;
    body.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Menü schließen' : 'Menü öffnen');
  };
  if (toggle && overlay) {
    toggle.addEventListener('click', () => setMenu(overlay.hidden));
    overlay.addEventListener('click', (e) => { if (e.target.closest('a')) setMenu(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !overlay.hidden) setMenu(false); });
  }

  // ---- back to top
  const top = document.querySelector('.back-to-top');
  if (top) {
    const update = () => top.classList.toggle('visible', window.scrollY > window.innerHeight * 0.6);
    window.addEventListener('scroll', update, { passive: true });
    update();
    top.querySelector('a').addEventListener('click', (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ---- collapsible boxes (Bibliographie): collapsed by default, header toggles
  document.querySelectorAll('[data-collapse-toggle]').forEach((head) => {
    const box = document.getElementById(head.dataset.collapseToggle);
    if (!box) return;
    const set = (open) => {
      box.hidden = !open;
      head.setAttribute('aria-expanded', String(open));
      head.classList.toggle('is-open', open);
    };
    head.setAttribute('role', 'button');
    head.setAttribute('aria-controls', box.id);
    head.tabIndex = 0;
    head.addEventListener('click', () => set(box.hidden));
    head.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); set(box.hidden); }
    });
    set(false);
  });

  // ---- background videos: respect "reduce motion"
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.querySelectorAll('.background-video video').forEach((v) => { v.removeAttribute('autoplay'); v.pause(); });
  }
})();
