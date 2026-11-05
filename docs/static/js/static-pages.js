/* WebCraft - статическая версия для GitHub Pages */
(function () {
  'use strict';
  var root = document.documentElement.getAttribute('data-site-root') || '';
  var localPage = root + '/local/';

  var bar = document.createElement('div');
  bar.className = 'static-bar';
  bar.innerHTML = 'Демо-версия на GitHub Pages: вход, личный кабинет, заказы и CRM работают при ' +
    '<a href="' + localPage + '">локальном запуске проекта</a>.';
  document.body.insertBefore(bar, document.body.firstChild);

  function notice(text) {
    var box = document.querySelector('.flashes');
    if (!box) { box = document.createElement('div'); box.className = 'flashes'; document.body.appendChild(box); }
    var alert = document.createElement('div');
    alert.className = 'alert alert--warning';
    alert.setAttribute('role', 'alert');
    alert.innerHTML = '<span>' + text + '</span><button type="button" class="alert__close" aria-label="Закрыть">&times;</button>';
    alert.querySelector('.alert__close').addEventListener('click', function () { alert.remove(); });
    box.appendChild(alert);
    setTimeout(function () { alert.remove(); }, 9000);
  }

  document.querySelectorAll('form[method=post], form[method=POST]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      notice('В статической версии на GitHub Pages формы не отправляются. ' +
        '<a href="' + localPage + '">Как запустить полную версию</a>.');
    });
  });
})();
