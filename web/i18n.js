import en from './locales/en.js';
import zh from './locales/zh-CN.js';
import ja from './locales/ja.js';

export const catalogs = {en, 'zh-CN': zh, ja};
export function normalizeLocale(value) {
  const prefix = String(value ?? '').toLowerCase().split('-')[0];
  return prefix === 'zh' ? 'zh-CN' : prefix === 'ja' ? 'ja' : 'en';
}
function preferredLocale() {
  if (typeof window === 'undefined') return 'en';
  return normalizeLocale(new URL(location.href).searchParams.get('lang') ||
    localStorage.getItem('avatar-language') || navigator.language);
}
export const locale = preferredLocale();
export function translate(language, key, ...values) {
  const catalog = catalogs[normalizeLocale(language)];
  const prefix = catalog[key] === undefined && Object.keys(en).find(k => k.endsWith('：') && key.startsWith(k));
  const text = catalog[key] ?? (prefix ? catalog[prefix] + key.slice(prefix.length) : key);
  return text.replace(/\{(\d+)\}/g, (token, index) => values[index] === undefined ? token : String(values[index]));
}
export const t = (key, ...values) => translate(locale, key, ...values);

// Translate static text nodes once, keeping nested controls and event targets intact.
// Dynamic messages call t() explicitly; character content is kept in its own language.
if (typeof document !== 'undefined' && !document.documentElement.dataset.localized) {
  document.documentElement.dataset.localized = locale;
  document.documentElement.lang = locale;
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (node.parentElement.closest('script,style')) continue;
    const key = node.textContent.trim();
    if (key && catalogs.en[key]) node.textContent = node.textContent.replace(key, t(key));
  }
  for (const node of document.querySelectorAll('[title],[placeholder],[aria-label],[alt]')) {
    for (const attr of ['title', 'placeholder', 'aria-label', 'alt']) {
      if (node.hasAttribute(attr)) node.setAttribute(attr, t(node.getAttribute(attr)));
    }
  }
  const picker = document.getElementById('language');
  if (picker) {
    picker.value = locale;
    picker.onchange = () => {
      localStorage.setItem('avatar-language', picker.value);
      const draft = document.getElementById('prompt')?.value;
      if (draft) sessionStorage.setItem('avatar-language-draft', draft);
      const url = new URL(location.href);
      url.searchParams.set('lang', picker.value);
      location.assign(url);
    };
  }
}
