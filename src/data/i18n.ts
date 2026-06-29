export const zhHans = 'zhHans' as const;

export function translated<T extends { translations?: Record<string, any> }>(
  item: T,
  field: string,
  locale = zhHans
): string {
  const value = item.translations?.[locale]?.[field];
  return typeof value === 'string' && value ? value : (item as any)[field] ?? '';
}

export function localizedPath(pathname: string, locale: 'en' | 'zhs'): string {
  const clean = pathname.endsWith('/') ? pathname : `${pathname}/`;
  if (locale === 'zhs') return clean.startsWith('/zhs/') ? clean : `/zhs${clean}`;
  return clean.replace(/^\/zhs(?=\/|$)/, '') || '/';
}
