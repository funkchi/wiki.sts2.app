import { enchantmentForLocale, enchantments } from './enchantments';
import type { Lang } from './i18n';

type TextToken = {
  start: number;
  end: number;
  priority: number;
  render: (text: string) => string;
};

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const escRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function enhancementHref(slug: string, locale: Lang): string {
  return `${locale === 'en' ? '' : `/${locale}`}/docs/enhancements/${slug}/`;
}

function keywordTokens(text: string, keywords: string[], cls: string): TextToken[] {
  if (!keywords.length) return [];
  const terms = [...new Set(keywords.filter(Boolean))].sort((a, b) => b.length - a.length);
  if (!terms.length) return [];
  const re = new RegExp('\\b(' + terms.map(escRe).join('|') + ')\\b', 'gi');
  const tokens: TextToken[] = [];
  for (const match of text.matchAll(re)) {
    if (match.index === undefined) continue;
    tokens.push({
      start: match.index,
      end: match.index + match[0].length,
      priority: 1,
      render: (value) => `<span class="${cls}">${esc(value)}</span>`,
    });
  }
  return tokens;
}

function enhancementTokens(text: string, locale: Lang): TextToken[] {
  const terms = enchantments
    .map((enchantment) => ({
      slug: enchantment.slug,
      name: enchantmentForLocale(enchantment, locale).name,
    }))
    .filter((term) => term.name)
    .sort((a, b) => b.name.length - a.name.length);
  const tokens: TextToken[] = [];
  for (const term of terms) {
    const source =
      locale === 'en'
        ? `(?<![A-Za-z])${escRe(term.name)}(?![A-Za-z])`
        : escRe(term.name);
    const re = new RegExp(source, locale === 'en' ? 'gi' : 'g');
    for (const match of text.matchAll(re)) {
      if (match.index === undefined) continue;
      tokens.push({
        start: match.index,
        end: match.index + match[0].length,
        priority: 2,
        render: (value) => `<a class="enhancement-link" href="${enhancementHref(term.slug, locale)}">${esc(value)}</a>`,
      });
    }
  }
  return tokens;
}

export function renderEntityTextHtml(
  text: string,
  {
    locale = 'en',
    keywords = [],
    keywordClass = 'kw',
  }: { locale?: Lang; keywords?: string[]; keywordClass?: string } = {}
): string {
  if (!text) return '';
  const tokens = [...enhancementTokens(text, locale), ...keywordTokens(text, keywords, keywordClass)].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    if (a.priority !== b.priority) return b.priority - a.priority;
    return b.end - b.start - (a.end - a.start);
  });
  const selected: TextToken[] = [];
  let cursor = 0;
  for (const token of tokens) {
    if (token.start < cursor) continue;
    selected.push(token);
    cursor = token.end;
  }

  let html = '';
  cursor = 0;
  for (const token of selected) {
    html += esc(text.slice(cursor, token.start));
    html += token.render(text.slice(token.start, token.end));
    cursor = token.end;
  }
  html += esc(text.slice(cursor));
  return html;
}
