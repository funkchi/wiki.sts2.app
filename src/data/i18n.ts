export const zhHans = 'zhHans' as const;
export const ja = 'ja' as const;

export type Lang = 'en' | 'zhs' | 'jpn';
export type TranslationKey = typeof zhHans | typeof ja;

export const languages: Array<{
  code: Lang;
  key?: TranslationKey;
  hreflang: string;
  label: string;
  shortLabel: string;
}> = [
  { code: 'en', hreflang: 'en', label: 'English', shortLabel: 'EN' },
  { code: 'zhs', key: zhHans, hreflang: 'zh-Hans', label: '中文', shortLabel: '中文' },
  { code: 'jpn', key: ja, hreflang: 'ja', label: '日本語', shortLabel: '日本語' },
];

export const languageByCode = Object.fromEntries(languages.map((language) => [language.code, language])) as Record<
  Lang,
  (typeof languages)[number]
>;

export function localeFromPath(pathname: string): Lang {
  if (pathname.startsWith('/zhs/')) return 'zhs';
  if (pathname.startsWith('/jpn/')) return 'jpn';
  return 'en';
}

export function translationKey(locale: Lang): TranslationKey | undefined {
  return languageByCode[locale].key;
}

export function translated<T extends { translations?: Record<string, any> }>(
  item: T,
  field: string,
  locale: Lang | TranslationKey = zhHans
): string {
  const key = locale === 'en' || locale === 'zhs' || locale === 'jpn' ? translationKey(locale) : locale;
  const value = key ? item.translations?.[key]?.[field] : undefined;
  return typeof value === 'string' && value ? value : (item as any)[field] ?? '';
}

export function localizedPath(pathname: string, locale: Lang): string {
  const clean = pathname.endsWith('/') ? pathname : `${pathname}/`;
  const base = clean.replace(/^\/(?:zhs|jpn)(?=\/|$)/, '') || '/';
  if (locale === 'en') return base;
  return `/${locale}${base === '/' ? '/' : base}`;
}
