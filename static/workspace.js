document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  const mobile = window.matchMedia('(max-width: 991px)');
  sidebar.setAttribute('aria-label', t('Workspace navigation'));
  const bar = document.createElement('header');
  bar.className = 'mobile-bar';
  const brand = document.createElement('a');
  brand.href = sidebar.querySelector('.menu a').href;
  brand.textContent = 'PCB Inspect';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.textContent = t('Menu');
  toggle.setAttribute('aria-label', t('Open navigation'));
  toggle.setAttribute('aria-expanded', 'false');
  sidebar.id ||= 'workspace-navigation';
  toggle.setAttribute('aria-controls', sidebar.id);
  bar.append(brand, toggle);
  document.body.prepend(bar);
  const backdrop = document.createElement('button');
  backdrop.type = 'button';
  backdrop.className = 'nav-backdrop';
  backdrop.setAttribute('aria-label', t('Close navigation'));
  document.body.append(backdrop);
  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'sidebar-close';
  closeButton.textContent = '×';
  closeButton.setAttribute('aria-label', t('Close workspace navigation'));
  sidebar.prepend(closeButton);
  const background = [...document.querySelectorAll('.main, .mobile-bar')];
  let previousFocus;
  const close = ({ returnFocus = true } = {}) => {
    const wasOpen = sidebar.classList.contains('show');
    sidebar.classList.remove('show');
    backdrop.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('nav-open');
    background.forEach(element => { element.inert = false; });
    if (wasOpen && returnFocus && mobile.matches) (previousFocus || toggle).focus();
  };
  toggle.addEventListener('click', () => {
    previousFocus = document.activeElement;
    sidebar.classList.add('show');
    backdrop.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.classList.add('nav-open');
    background.forEach(element => { element.inert = true; });
    requestAnimationFrame(() => {
      if (sidebar.classList.contains('show')) closeButton.focus();
    });
  });
  backdrop.addEventListener('click', () => close());
  closeButton.addEventListener('click', () => close());
  sidebar.querySelectorAll('.menu a').forEach(link => link.addEventListener('click', () => close({ returnFocus: false })));
  document.addEventListener('keydown', event => {
    if (!sidebar.classList.contains('show') || !mobile.matches) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key === 'Tab') {
      const links = [...sidebar.querySelectorAll('a,button')].filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && !el.disabled);
      const first = links[0], last = links[links.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  mobile.addEventListener('change', () => close({ returnFocus: false }));
  sidebar.querySelectorAll('.menu a.active').forEach(link => link.setAttribute('aria-current', 'page'));
  // Let keyboard users scroll wide records without squeezing every column.
  document.querySelectorAll('.table-responsive').forEach(region => {
    region.tabIndex = 0;
    region.setAttribute('role', 'region');
    region.setAttribute('aria-label', t('Records table, scroll horizontally to see all columns'));
  });
});
