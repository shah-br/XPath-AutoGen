"""In-browser DOM extraction script for Playwright evaluate()."""

EXTRACT_ELEMENTS_JS = """
() => {
  const INTERACTIVE_SELECTORS = [
    'a[href]',
    'button',
    'input:not([type="hidden"])',
    'select',
    'textarea',
    '[role="button"]',
    '[role="link"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="switch"]',
    '[role="combobox"]',
    'label[for]',
    'summary',
    '[data-testid]',
    '[data-test]',
  ].join(',');

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width >= 8 && rect.height >= 8;
  }

  function getText(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      return el.value || el.placeholder || '';
    }
    if (tag === 'img') {
      return el.alt || '';
    }
    return (el.innerText || el.textContent || '').trim().slice(0, 200);
  }

  function getDomPath(el, maxDepth = 5) {
    const parts = [];
    let current = el;
    let depth = 0;
    while (current && current.nodeType === 1 && depth < maxDepth) {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part += `#${current.id}`;
        parts.unshift(part);
        break;
      }
      const cls = Array.from(current.classList || []).slice(0, 2).join('.');
      if (cls) part += `.${cls}`;
      parts.unshift(part);
      current = current.parentElement;
      depth += 1;
    }
    return parts.join(' > ');
  }

  function inferSection(el) {
    let current = el;
    while (current && current.nodeType === 1) {
      const tag = current.tagName.toLowerCase();
      const role = (current.getAttribute('role') || '').toLowerCase();
      const cls = (current.className || '').toString().toLowerCase();
      if (tag === 'header' || role === 'banner') return 'Header';
      if (tag === 'nav' || role === 'navigation') return 'Navigation';
      if (tag === 'main' || role === 'main') return 'MainContent';
      if (tag === 'footer' || role === 'contentinfo') return 'Footer';
      if (tag === 'form' || role === 'form') return 'Form';
      if (role === 'dialog' || cls.includes('modal') || cls.includes('dialog')) return 'Modal';
      if (tag === 'aside' || role === 'complementary' || cls.includes('sidebar')) return 'Sidebar';
      current = current.parentElement;
    }
    return '';
  }

  function isAutoId(id) {
    return /^(:|r|ember|react)[\\d\\-_a-z]*$/i.test(id || '');
  }

  function hasMeaningfulHref(href) {
    if (!href || href === '#') return false;
    return !href.trim().toLowerCase().startsWith('javascript:');
  }

  function isTestable(el, text, id, name, role, testId, href, type) {
    if (el.disabled) return false;
    if (!isVisible(el)) return false;

    const tag = el.tagName.toLowerCase();
    const aria = (el.getAttribute('aria-label') || '').trim();
    const placeholder = el.getAttribute('placeholder') || '';
    const stableId = id && !isAutoId(id);
    const meaningfulText = text.trim().length >= 2;
    const hasIdentity = !!(
      stableId || testId || name || meaningfulText || aria.length >= 2 || placeholder
    );

    if (tag === 'select' || tag === 'textarea') return true;
    if (tag === 'input' && type && type !== 'hidden') return hasIdentity || !!type;
    if (tag === 'button' || role === 'button') return hasIdentity;
    if (tag === 'a' || role === 'link') return hasIdentity && hasMeaningfulHref(href);
    if (testId || stableId) return true;
    if (['tab', 'menuitem', 'checkbox', 'radio', 'switch', 'combobox'].includes(role)) {
      return hasIdentity;
    }
    return hasIdentity;
  }

  const seen = new Set();
  const results = [];
  const nodes = document.querySelectorAll(INTERACTIVE_SELECTORS);

  nodes.forEach((el, index) => {
    const rect = el.getBoundingClientRect();
    const text = getText(el);
    const id = el.id || '';
    const name = el.getAttribute('name') || '';
    const role = el.getAttribute('role') || '';
    const type = (el.getAttribute('type') || '').toLowerCase();
    const testId = el.getAttribute('data-testid') || el.getAttribute('data-test') || '';
    const href = el.getAttribute('href') || '';

    if (!isTestable(el, text, id, name, role, testId, href, type)) {
      return;
    }

    const key = [el.tagName, id, name, text.slice(0, 80), role, testId, href].join('|');
    if (seen.has(key)) return;
    seen.add(key);

    results.push({
      element_id: `el_${index}_${Date.now()}`,
      tag: el.tagName.toLowerCase(),
      element_type: type,
      text,
      aria_label: el.getAttribute('aria-label') || '',
      id,
      name,
      placeholder: el.getAttribute('placeholder') || '',
      role,
      data_testid: testId,
      classes: Array.from(el.classList || []).slice(0, 3).join(' '),
      href,
      dom_path: getDomPath(el),
      bbox_x: rect.x,
      bbox_y: rect.y,
      bbox_width: rect.width,
      bbox_height: rect.height,
      is_visible: true,
      is_enabled: !el.disabled,
      heuristic_section: inferSection(el),
    });
  });

  return {
    title: document.title || '',
    url: window.location.href,
    elements: results,
  };
}
"""
