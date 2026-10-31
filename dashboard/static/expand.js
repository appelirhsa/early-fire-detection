'use strict';
/*
 * Enlargeable cards ("widgets"): every .card gets a button in its top-right corner
 * that opens it as a large view over the page. Esc, the close button or a click
 * on the dimmed background returns it to its place. Charts redraw at the new size.
 */
(function () {
  const ICON_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>';
  const ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';

  let openCard = null;
  let backdrop = null;

  function redraw() {
    // Charts listen for resize; run twice so layout has settled.
    window.dispatchEvent(new Event('resize'));
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  }

  function setButton(btn, expanded) {
    btn.innerHTML = expanded ? ICON_CLOSE : ICON_OPEN;
    btn.setAttribute('aria-expanded', String(expanded));
    btn.setAttribute('aria-label', expanded ? 'Close enlarged view' : 'Enlarge');
    btn.title = expanded ? 'Close (Esc)' : 'Enlarge';
  }

  function close() {
    if (!openCard) return;
    const btn = openCard.querySelector(':scope > .card-expand');
    openCard.classList.remove('is-expanded');
    document.body.classList.remove('card-open');
    if (backdrop) backdrop.hidden = true;
    setButton(btn, false);
    openCard = null;
    btn.focus({ preventScroll: true });
    redraw();
  }

  function open(card) {
    if (openCard) close();
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.className = 'card-backdrop';
      backdrop.addEventListener('click', close);
      document.body.appendChild(backdrop);
    }
    backdrop.hidden = false;
    card.classList.add('is-expanded');
    document.body.classList.add('card-open');
    openCard = card;
    const btn = card.querySelector(':scope > .card-expand');
    setButton(btn, true);
    btn.focus({ preventScroll: true });
    card.scrollTop = 0;
    redraw();
  }

  function init() {
    document.querySelectorAll('.card').forEach(card => {
      if (card.querySelector(':scope > .card-expand') || card.dataset.noExpand !== undefined) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'card-expand no-print';
      setButton(btn, false);
      btn.addEventListener('click', () => (openCard === card ? close() : open(card)));
      card.classList.add('has-expand');
      card.appendChild(btn);
    });
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && openCard) {
      e.preventDefault();
      close();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
