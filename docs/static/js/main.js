/* WebCraft — клиентские сценарии */
(function () {
  'use strict';

  const formatMoney = (value) => Math.round(value).toLocaleString('ru-RU') + ' ₽';

  // Мобильное меню сайта и боковое меню панели управления
  document.querySelectorAll('[data-toggle-nav]').forEach((btn) =>
    btn.addEventListener('click', () => document.getElementById('nav').classList.toggle('is-open')));
  document.querySelectorAll('[data-toggle-sidebar]').forEach((btn) =>
    btn.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('is-open')));

  // Уведомления: закрытие по кнопке и автоматическое скрытие
  document.querySelectorAll('.alert').forEach((alert, i) => {
    const close = () => { alert.style.transition = 'opacity .3s'; alert.style.opacity = '0'; setTimeout(() => alert.remove(), 300); };
    alert.querySelector('.alert__close').addEventListener('click', close);
    if (!alert.classList.contains('alert--error')) setTimeout(close, 6000 + i * 500);
  });

  // Подтверждение необратимых действий
  document.querySelectorAll('form[data-confirm]').forEach((form) =>
    form.addEventListener('submit', (e) => { if (!confirm(form.dataset.confirm)) e.preventDefault(); }));

  // Клик по строке таблицы открывает карточку
  document.querySelectorAll('tr[data-href]').forEach((row) =>
    row.addEventListener('click', (e) => { if (!e.target.closest('a, button, form')) location.href = row.dataset.href; }));

  // Предпросмотр загружаемого изображения
  document.querySelectorAll('input[type=file][data-preview]').forEach((input) =>
    input.addEventListener('change', () => {
      const img = document.querySelector(input.dataset.preview);
      if (img && input.files[0]) { img.src = URL.createObjectURL(input.files[0]); img.hidden = false; }
    }));

  // Подсказка о стоимости выбранной услуги в форме заказа
  const serviceSelect = document.getElementById('serviceSelect');
  if (serviceSelect) {
    const box = document.getElementById('serviceEstimate');
    const update = () => {
      const opt = serviceSelect.selectedOptions[0];
      if (!opt || !opt.value) { box.hidden = true; return; }
      document.getElementById('estimatePrice').textContent = 'от ' + formatMoney(+opt.dataset.price);
      document.getElementById('estimateDays').textContent = 'срок от ' + opt.dataset.days + ' дн.';
      box.hidden = false;
    };
    serviceSelect.addEventListener('change', update);
    update();
  }

  // Калькулятор стоимости проекта
  const calc = document.getElementById('calc');
  if (calc) {
    const PAGE_PRICE = 3000;
    const pages = document.getElementById('pages');
    const totalEl = document.getElementById('total');
    const daysEl = document.getElementById('days');
    const link = document.getElementById('orderLink');

    const recalc = () => {
      const type = calc.querySelector('input[name=type]:checked');
      const urgency = parseFloat(calc.querySelector('input[name=urgency]:checked').value);
      const pageCount = parseInt(pages.value, 10);
      const extraPages = Math.max(pageCount - parseInt(type.dataset.pages, 10), 0);
      const options = [...calc.querySelectorAll('.checks input:checked')];

      let total = parseInt(type.value, 10) + extraPages * PAGE_PRICE;
      options.forEach((o) => { total += parseInt(o.value, 10); });
      total *= urgency;

      let days = parseInt(type.dataset.days, 10) + Math.ceil(extraPages / 3) + options.length * 2;
      if (urgency > 1) days = Math.ceil(days * 0.7);

      document.getElementById('pagesOut').textContent = pageCount;
      totalEl.textContent = formatMoney(total);
      daysEl.textContent = 'около ' + days + ' раб. дней';

      const description = [
        'Тип проекта: ' + type.dataset.label,
        'Количество страниц/экранов: ' + pageCount,
        options.length ? 'Дополнительно: ' + options.map((o) => o.dataset.label).join(', ') : '',
        urgency > 1 ? 'Срочное выполнение' : '',
        'Предварительная оценка по калькулятору: ' + formatMoney(total) + ', ' + days + ' раб. дней',
      ].filter(Boolean).join('\n');
      const params = new URLSearchParams({ title: type.dataset.label, budget: Math.round(total), description });
      link.href = link.dataset.base + '?' + params.toString();
    };

    calc.addEventListener('input', recalc);
    calc.addEventListener('change', recalc);
    recalc();
  }
})();
