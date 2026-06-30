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

const localizedPrefixes = /^\/(?:zhs|jpn)(?=\/|$)/;

export const languageByCode = Object.fromEntries(languages.map((language) => [language.code, language])) as Record<
  Lang,
  (typeof languages)[number]
>;

export const siteTitles: Record<Lang, string> = {
  en: 'Slay the Spire 2 Wiki',
  zhs: '杀戮尖塔 2 Wiki',
  jpn: 'Slay the Spire 2 日本語Wiki',
};

export const sidebarLabels: Record<Lang, Record<string, string>> = {
  en: {
    cards: 'Cards',
    relics: 'Relics',
    enemies: 'Enemies',
    characters: 'Characters',
    guides: 'Guides',
    about: 'About',
    privacy: 'Privacy',
    contact: 'Contact',
    disclaimer: 'Disclaimer',
  },
  zhs: {
    cards: '卡牌',
    relics: '遗物',
    enemies: '敌人',
    characters: '角色',
    guides: '指南',
    about: '关于',
    privacy: '隐私',
    contact: '联系',
    disclaimer: '免责声明',
  },
  jpn: {
    cards: 'カード',
    relics: 'レリック',
    enemies: '敵',
    characters: 'キャラクター',
    guides: 'ガイド',
    about: '概要',
    privacy: 'プライバシー',
    contact: '連絡先',
    disclaimer: '免責事項',
  },
};

const entitySections = [
  { key: 'cards', path: '/docs/cards/' },
  { key: 'relics', path: '/docs/relics/' },
  { key: 'enemies', path: '/docs/enemies/' },
  { key: 'characters', path: '/docs/characters/' },
] as const;

const englishEditorial = [
  { key: 'guides', path: '/guides/' },
  { key: 'about', path: '/about/' },
  { key: 'privacy', path: '/privacy/' },
  { key: 'contact', path: '/contact/' },
  { key: 'disclaimer', path: '/disclaimer/' },
] as const;

export const characterLabels: Record<Lang, Record<string, string>> = {
  en: {
    shared: 'Shared',
    ironclad: 'Ironclad',
    silent: 'Silent',
    defect: 'Defect',
    necrobinder: 'Necrobinder',
    regent: 'Regent',
    colorless: 'Colorless',
    event: 'Event',
    token: 'Token',
    quest: 'Quest',
    curse: 'Curse',
    status: 'Status',
  },
  zhs: {
    shared: '通用',
    ironclad: '铁甲战士',
    silent: '静默猎手',
    defect: '故障机器人',
    necrobinder: '亡灵束缚者',
    regent: '摄政者',
    colorless: '无色',
    event: '事件',
    token: '衍生',
    quest: '任务',
    curse: '诅咒',
    status: '状态',
  },
  jpn: {
    shared: '共通',
    ironclad: 'アイアンクラッド',
    silent: 'サイレント',
    defect: 'ディフェクト',
    necrobinder: 'ネクロバインダー',
    regent: 'リージェント',
    colorless: '無色',
    event: 'イベント',
    token: 'トークン',
    quest: 'クエスト',
    curse: '呪い',
    status: '状態異常',
  },
};

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
  const base = clean.replace(localizedPrefixes, '') || '/';
  if (locale === 'en') return base;
  return `/${locale}${base === '/' ? '/' : base}`;
}

export function hasLocalizedCounterpart(pathname: string): boolean {
  const clean = pathname.endsWith('/') ? pathname : `${pathname}/`;
  const base = clean.replace(localizedPrefixes, '') || '/';
  return base === '/' || base === '/docs/' || /^\/docs\/(?:cards|relics|enemies|characters)(?:\/|$)/.test(base);
}

export function siteTitleFor(locale: Lang): string {
  return siteTitles[locale] ?? siteTitles.en;
}

export function localizedHome(locale: Lang): string {
  return locale === 'en' ? '/' : `/${locale}/`;
}

export function sidebarItemsFor(locale: Lang): Array<{ key: string; label: string; href: string }> {
  const labels = sidebarLabels[locale] ?? sidebarLabels.en;
  const entityItems = entitySections.map((item) => ({
    key: item.key,
    label: labels[item.key],
    href: localizedPath(item.path, locale),
  }));
  if (locale !== 'en') return entityItems;
  return [
    ...entityItems,
    ...englishEditorial.map((item) => ({
      key: item.key,
      label: labels[item.key],
      href: item.path,
    })),
  ];
}

export function localizedCharacterLabel(locale: Lang, value: string | null | undefined): string {
  if (!value) return '-';
  const key = String(value).toLowerCase().replace(/^the\s+/, '').replace(/[^a-z0-9]+/g, '');
  return characterLabels[locale]?.[key] ?? characterLabels.en[key] ?? value;
}
