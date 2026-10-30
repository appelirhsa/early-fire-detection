/* Theme: light / dark / system. Loaded in <head> before the stylesheet so pages never flash. */
(function () {
  var KEY = 'efd-theme';
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function stored() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }

  function resolve(mode) {
    if (mode === 'light' || mode === 'dark') return mode;
    return mq && mq.matches ? 'dark' : 'light';
  }

  function apply(mode) {
    var theme = resolve(mode);
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-theme-mode', mode);
    try {
      document.dispatchEvent(new CustomEvent('themechange', { detail: { mode: mode, theme: theme } }));
    } catch (e) { /* old browsers */ }
  }

  window.getThemeMode = stored;
  window.setThemeMode = function (mode) {
    try { localStorage.setItem(KEY, mode); } catch (e) { /* storage blocked: still apply for this page */ }
    apply(mode);
  };

  if (mq) {
    var onSystemChange = function () { if (stored() === 'system') apply('system'); };
    if (mq.addEventListener) mq.addEventListener('change', onSystemChange);
    else if (mq.addListener) mq.addListener(onSystemChange);
  }

  apply(stored());
})();
