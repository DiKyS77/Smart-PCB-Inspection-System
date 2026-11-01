document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-record-pagination]').forEach(container => {
    const rows = [...document.querySelectorAll(container.dataset.rows)];
    const info = container.querySelector('[data-page-info]');
    const controls = container.querySelector('[data-page-buttons]');
    const search = container.dataset.search ? document.querySelector(container.dataset.search) : null;
    const table = search ? document.getElementById('tableWrap') : null;
    const empty = search ? document.getElementById('emptySearch') : null;
    const perPage = 10;
    let currentPage = 1;

    function button(label, page, {icon, disabled = false, active = false} = {}) {
      const element = document.createElement('button');
      element.type = 'button';
      element.className = 'pag-btn' + (active ? ' active' : '');
      element.disabled = disabled;
      element.setAttribute('aria-label', label);
      if (active) element.setAttribute('aria-current', 'page');
      if (icon) {
        const glyph = document.createElement('i');
        glyph.className = 'fas fa-chevron-' + icon;
        glyph.setAttribute('aria-hidden', 'true');
        element.append(glyph);
      } else element.textContent = page;
      element.addEventListener('click', () => { currentPage = page; render(); });
      return element;
    }

    function render() {
      const term = search ? search.value.toLowerCase().trim() : '';
      const matching = rows.filter(row => !term || [row.dataset.pcbId, row.dataset.defect, row.dataset.followUp]
        .some(value => (value || '').includes(term)));
      const total = matching.length;
      const pages = Math.max(1, Math.ceil(total / perPage));
      currentPage = Math.max(1, Math.min(currentPage, pages));
      const start = (currentPage - 1) * perPage;
      const end = Math.min(start + perPage, total);
      const visible = new Set(matching.slice(start, end));
      rows.forEach(row => { row.style.display = visible.has(row) ? '' : 'none'; });
      if (empty) empty.classList.toggle('show', total === 0 && term !== '');
      if (table) table.style.display = total === 0 && term !== '' ? 'none' : '';
      info.textContent = total ? t('Showing {start}–{end} of {total} records', {start: start + 1, end, total}) : '';
      controls.replaceChildren();
      if (!total) return;
      controls.append(button(t('Previous page'), currentPage - 1, {icon: 'left', disabled: currentPage === 1}));
      for (let page = 1; page <= pages; page++) {
        if (page === 1 || page === pages || Math.abs(page - currentPage) <= 2) {
          controls.append(button(t('Page {page}', {page}), page, {active: page === currentPage}));
        } else if (Math.abs(page - currentPage) === 3) {
          const ellipsis = document.createElement('span');
          ellipsis.className = 'pagination-ellipsis';
          ellipsis.textContent = '…';
          controls.append(ellipsis);
        }
      }
      controls.append(button(t('Next page'), currentPage + 1, {icon: 'right', disabled: currentPage === pages}));
    }

    if (search) search.addEventListener('input', () => { currentPage = 1; render(); });
    render();
  });
});
