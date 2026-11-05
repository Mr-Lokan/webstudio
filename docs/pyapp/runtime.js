/* WebCraft: Flask-приложение в браузере (Pyodide) для GitHub Pages.
 *
 * Страницы сайта заранее собраны в статический HTML и открываются сразу.
 * В фоне загружается Pyodide (Python в WebAssembly) с тем же Flask-приложением;
 * после загрузки переходы по ссылкам и отправка форм обрабатываются им прямо
 * в браузере. База SQLite и загруженные изображения хранятся в IndexedDB
 * этого браузера, сессия входа - в localStorage.
 */
(function () {
  'use strict';

  var ROOT = document.documentElement.getAttribute('data-site-root') || '';
  var VERSION = '715d96bcc2';
  var SHIPPED_UPLOADS = ["portfolio-1.svg", "portfolio-2.svg", "portfolio-3.svg", "portfolio-4.svg", "portfolio-5.svg", "portfolio-6.svg", "portfolio-7.svg", "portfolio-8.svg", "portfolio-9.svg"];
  var SESSION_KEY = 'webcraft.session';
  var STATIC_PREFIX = ROOT + '/static/';

  var py = null;
  var api = null;
  var booting = null;
  var active = false;
  var appRendered = false;
  var storageOk = true;
  var blobUrls = {};

  // ------------------------------------------------------------------ хранилище

  var store = {
    get: function (k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* приватный режим */ } },
    remove: function (k) { try { window.localStorage.removeItem(k); } catch (e) { /* приватный режим */ } }
  };

  function syncfs(populate) {
    if (!storageOk) return Promise.resolve();
    return new Promise(function (resolve) {
      try {
        py.FS.syncfs(populate, function (err) {
          if (err) console.warn('WebCraft: IndexedDB недоступна', err);
          resolve();
        });
      } catch (e) {
        console.warn('WebCraft: IndexedDB недоступна', e);
        resolve();
      }
    });
  }

  // ------------------------------------------------------------------ интерфейс

  var style = document.createElement('style');
  style.textContent =
    '.wc-busy{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;' +
    'background:rgba(246,245,255,.72);backdrop-filter:blur(2px);opacity:0;pointer-events:none;transition:opacity .2s}' +
    '.wc-busy.is-on{opacity:1;pointer-events:auto}' +
    '.wc-busy__box{display:flex;align-items:center;gap:12px;padding:14px 20px;border-radius:12px;background:#fff;' +
    'box-shadow:0 12px 32px rgba(30,20,80,.18);font-size:15px;color:#2d2654}' +
    '.wc-busy__spin{width:20px;height:20px;border:3px solid #ddd8ff;border-top-color:#6c5ce7;border-radius:50%;' +
    'animation:wc-spin .8s linear infinite}' +
    '@keyframes wc-spin{to{transform:rotate(360deg)}}' +
    '.wc-pending main,.wc-pending .nav__user,.wc-pending .flashes{visibility:hidden}' +
    '.wc-demo-note{display:block;margin-top:6px;font-size:13px;opacity:.75}' +
    '.wc-demo-note button{border:0;background:none;color:inherit;text-decoration:underline;cursor:pointer;font:inherit;padding:0}';
  document.head.appendChild(style);

  var busyTimer = null;
  function busy(on, text) {
    var el = document.querySelector('.wc-busy');
    if (!el) {
      el = document.createElement('div');
      el.className = 'wc-busy';
      el.innerHTML = '<div class="wc-busy__box"><span class="wc-busy__spin"></span><span class="wc-busy__text"></span></div>';
      document.body.appendChild(el);
    }
    clearTimeout(busyTimer);
    if (on) {
      el.querySelector('.wc-busy__text').textContent = text || 'Загрузка…';
      // короткие запросы выполняются без мигания индикатора
      busyTimer = setTimeout(function () { el.classList.add('is-on'); }, api ? 250 : 0);
    } else {
      el.classList.remove('is-on');
    }
  }

  function notice(text) {
    var box = document.querySelector('.flashes');
    if (!box) { box = document.createElement('div'); box.className = 'flashes'; document.body.appendChild(box); }
    var alert = document.createElement('div');
    alert.className = 'alert alert--error';
    alert.setAttribute('role', 'alert');
    alert.innerHTML = '<span></span><button type="button" class="alert__close" aria-label="Закрыть">&times;</button>';
    alert.querySelector('span').textContent = text;
    alert.querySelector('.alert__close').addEventListener('click', function () { alert.remove(); });
    box.appendChild(alert);
  }

  function demoNote() {
    var bottom = document.querySelector('.footer__bottom');
    if (!bottom || bottom.querySelector('.wc-demo-note')) return;
    var note = document.createElement('span');
    note.className = 'wc-demo-note';
    note.innerHTML = 'Демо-версия на GitHub Pages: приложение работает прямо в браузере, ' +
      'данные сохраняются только на этом устройстве. <button type="button">Сбросить демо-данные</button>';
    note.querySelector('button').addEventListener('click', resetData);
    bottom.appendChild(note);
  }

  // ------------------------------------------------------------------ запуск Python

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('не удалось загрузить ' + src)); };
      document.head.appendChild(s);
    });
  }

  function boot() {
    if (booting) return booting;
    booting = (async function () {
      var indexURL = ROOT + '/pyodide/';
      await loadScript(indexURL + 'pyodide.js');
      py = await window.loadPyodide({ indexURL: indexURL });
      await py.loadPackage(['sqlite3', 'hashlib', 'markupsafe'], { messageCallback: function () {} });
      var resp = await fetch(ROOT + '/pyapp/app.zip?v=' + VERSION);
      if (!resp.ok) throw new Error('app.zip: HTTP ' + resp.status);
      py.unpackArchive(await resp.arrayBuffer(), 'zip', { extractDir: '/app' });
      py.FS.mkdirTree('/data');
      try {
        py.FS.mount(py.FS.filesystems.IDBFS, {}, '/data');
      } catch (e) {
        storageOk = false;
        console.warn('WebCraft: данные не будут сохраняться', e);
      }
      await syncfs(true);
      py.runPython("import sys\nsys.path[:0] = ['/app', '/app/site-packages']");
      api = py.pyimport('webapp');
      if (api.boot(ROOT, store.get(SESSION_KEY))) store.remove(SESSION_KEY);
      await syncfs(false);
      active = true;
      demoNote();
    })();
    booting.catch(function (e) {
      console.error('WebCraft: не удалось запустить приложение', e);
      booting = null;
    });
    return booting;
  }

  async function request(method, path, type, body) {
    if (!api) {
      busy(true, 'Запускаем приложение…');
      await boot();
    }
    var raw = api.handle(method, path, type || null, body || null);
    var res = JSON.parse(raw);
    if (res.session) store.set(SESSION_KEY, res.session); else store.remove(SESSION_KEY);
    if (method !== 'GET') await syncfs(false);
    return res;
  }

  // ------------------------------------------------------------------ адреса

  function inSite(u) {
    return u.origin === location.origin && (u.pathname === ROOT || u.pathname.indexOf(ROOT + '/') === 0);
  }

  function isAsset(u) {
    return u.pathname.indexOf(STATIC_PREFIX) === 0 || u.pathname.indexOf(ROOT + '/pyodide/') === 0 ||
      u.pathname.indexOf(ROOT + '/pyapp/') === 0;
  }

  // адрес статической страницы -> адрес Flask-приложения (без корня сайта)
  function appPath(u) {
    var p = u.pathname.slice(ROOT.length) || '/';
    var m = p.match(/^\/(services|portfolio)\/category\/([\w-]+)\/?$/);
    if (m) return '/' + m[1] + '?category=' + m[2];
    if (/\/index\.html$/.test(p)) p = p.slice(0, -10) || '/';
    if (p.length > 1 && p.charAt(p.length - 1) === '/') p = p.slice(0, -1);
    return p + u.search;
  }

  // страницы, которых нет в статической сборке
  function needsApp(u) {
    return /^\/(cabinet|admin|logout)(\/|$|\?)/.test(appPath(u));
  }

  // ------------------------------------------------------------------ отображение

  function swapStyles(doc) {
    var current = [].slice.call(document.head.querySelectorAll('link[rel=stylesheet]'));
    var next = [].slice.call(doc.head.querySelectorAll('link[rel=stylesheet]'));
    var key = function (l) { return l.getAttribute('href'); };
    if (current.map(key).join('|') === next.map(key).join('|')) return Promise.resolve();
    var loads = next.map(function (l) {
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = l.getAttribute('href');
      var done = new Promise(function (r) { link.onload = r; link.onerror = r; setTimeout(r, 2000); });
      document.head.insertBefore(link, style);
      return done;
    });
    return Promise.all(loads).then(function () { current.forEach(function (l) { l.remove(); }); });
  }

  function fixUploads() {
    var prefix = ROOT + '/static/uploads/';
    document.querySelectorAll('img').forEach(function (img) {
      var src = img.getAttribute('src') || '';
      if (src.indexOf(prefix) !== 0) return;
      var name = src.slice(prefix.length);
      if (SHIPPED_UPLOADS.indexOf(name) !== -1) return;
      if (!blobUrls[name]) {
        var data = api.read_upload(name);
        if (!data) return;
        var bytes = data.toJs();
        data.destroy();
        var ext = name.split('.').pop().toLowerCase();
        var mime = ext === 'svg' ? 'image/svg+xml' : 'image/' + (ext === 'jpg' ? 'jpeg' : ext);
        blobUrls[name] = URL.createObjectURL(new Blob([bytes], { type: mime }));
      }
      img.src = blobUrls[name];
    });
  }

  async function render(res, mode, hash) {
    var target = res.url + (hash || '');
    if (mode === 'push' && target !== location.pathname + location.search + location.hash) {
      history.pushState(null, '', target);
    } else if (mode !== 'none') {
      history.replaceState(null, '', target);
    }
    var doc = new DOMParser().parseFromString(res.body, 'text/html');
    appRendered = true;
    await swapStyles(doc);
    document.title = doc.title;
    document.body.className = doc.body.className;
    document.body.replaceChildren.apply(document.body, [].slice.call(doc.body.childNodes));
    document.body.querySelectorAll('script').forEach(function (old) {
      var s = document.createElement('script');
      [].forEach.call(old.attributes, function (a) { s.setAttribute(a.name, a.value); });
      s.textContent = old.textContent;
      old.replaceWith(s);
    });
    fixUploads();
    demoNote();
    var anchor = hash && document.getElementById(decodeURIComponent(hash.slice(1)));
    if (anchor) anchor.scrollIntoView(); else window.scrollTo(0, 0);
  }

  function download(res) {
    var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.disposition);
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([res.body], { type: res.type || 'application/octet-stream' }));
    a.download = m ? decodeURIComponent(m[1]) : 'download';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  var queue = Promise.resolve();
  function go(u, opts) {
    opts = opts || {};
    queue = queue.then(async function () {
      busy(true, api ? 'Загрузка…' : 'Запускаем приложение…');
      try {
        var res = await request(opts.method || 'GET', appPath(u), opts.type, opts.body);
        if (/^attachment/i.test(res.disposition)) {
          download(res);
        } else {
          await render(res, opts.history || 'push', u.hash);
        }
      } catch (e) {
        console.error(e);
        notice('Не удалось выполнить действие в демо-версии: ' + (e && e.message ? e.message : e));
      } finally {
        busy(false);
      }
    });
    return queue;
  }

  async function resetData() {
    if (!confirm('Удалить все изменения демо-версии в этом браузере (заказы, пользователи, вход)?')) return;
    busy(true, 'Сбрасываем данные…');
    try {
      if (!api) await boot();
      api.reset();
      await syncfs(false);
    } catch (e) { console.error(e); }
    store.remove(SESSION_KEY);
    location.href = ROOT + '/';
  }

  // ------------------------------------------------------------------ перехват навигации

  // клик по строке таблицы в панели управления (main.js делает обычный переход)
  document.addEventListener('click', function (e) {
    var row = e.target.closest && e.target.closest('tr[data-href]');
    if (!row || e.target.closest('a, button, form, input, select, textarea, label')) return;
    e.preventDefault();
    e.stopPropagation();
    go(new URL(row.getAttribute('data-href'), location.href));
  }, true);

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(javascript|mailto|tel):/i.test(href)) return;
    var u = new URL(a.href, location.href);
    if (!inSite(u) || isAsset(u)) return;
    if (u.pathname === location.pathname && u.search === location.search && u.hash) return;
    if (!active && !needsApp(u)) return; // пока приложение грузится, статические страницы открываются как обычно
    e.preventDefault();
    go(u);
  });

  document.addEventListener('submit', function (e) {
    if (e.defaultPrevented) return;
    var form = e.target;
    var submitter = e.submitter || null;
    var attr = function (name, fallback) {
      return (submitter && submitter.getAttribute('form' + name)) || form.getAttribute(name) || fallback;
    };
    var method = attr('method', 'get').toUpperCase();
    var action = new URL(attr('action', location.href), location.href);
    if (!inSite(action) || isAsset(action)) return;
    e.preventDefault();

    var fd;
    try { fd = new FormData(form, submitter); } catch (err) {
      fd = new FormData(form);
      if (submitter && submitter.name) fd.append(submitter.name, submitter.value);
    }
    if (method === 'GET') {
      action.search = new URLSearchParams(fd).toString();
      go(action);
      return;
    }
    (async function () {
      var type, body;
      if (!appRendered && fd.has('csrf_token')) {
        // в заранее собранной странице токен от сборки: берём токен сессии браузерного приложения
        try {
          busy(true, api ? 'Загрузка…' : 'Запускаем приложение…');
          var fresh = await request('GET', appPath(new URL(location.href)));
          var m = /name="csrf_token" value="([^"]+)"/.exec(fresh.body);
          if (m) fd.set('csrf_token', m[1]);
        } catch (err) { console.error(err); }
      }
      if (attr('enctype', '').toLowerCase() === 'multipart/form-data') {
        var req = new Request(location.href, { method: 'POST', body: fd });
        type = req.headers.get('content-type');
        body = new Uint8Array(await req.arrayBuffer());
      } else {
        var params = new URLSearchParams();
        fd.forEach(function (v, k) { if (typeof v === 'string') params.append(k, v); });
        type = 'application/x-www-form-urlencoded';
        body = new TextEncoder().encode(params.toString());
      }
      go(action, { method: 'POST', type: type, body: body });
    })();
  });

  window.addEventListener('popstate', function () {
    if (active) go(new URL(location.href), { history: 'none' });
  });

  // ------------------------------------------------------------------ старт

  var here = new URL(location.href);
  var fallback = document.documentElement.getAttribute('data-page') === '404';
  if (fallback || store.get(SESSION_KEY) || here.search || needsApp(here)) {
    // страницы нет в статической сборке или пользователь вошёл: показываем ответ приложения,
    // а заглушку статической страницы прячем до его загрузки
    document.documentElement.classList.add('wc-pending');
    go(here, { history: 'replace' }).then(function () {
      document.documentElement.classList.remove('wc-pending');
    });
  } else {
    var start = function () { boot().catch(function () {}); };
    if ('requestIdleCallback' in window) window.requestIdleCallback(start, { timeout: 2000 }); else setTimeout(start, 300);
  }
})();
