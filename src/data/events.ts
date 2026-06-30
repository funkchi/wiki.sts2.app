import { z } from 'astro:schema';
import eventsData from '../../data/wiki/events.json';
import { translationKey, type Lang } from './i18n';

const EventOptionSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
});

const EventPageSchema = z.object({
  id: z.string(),
  options: z.array(EventOptionSchema),
});

const EventTranslationSchema = z.object({
  name: z.string(),
  type: z.string(),
  act: z.string().nullable(),
  preconditions: z.array(z.string()),
  options: z.array(EventOptionSchema),
  pages: z.array(EventPageSchema),
});

const EventSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  type: z.string(),
  act: z.string().nullable(),
  preconditions: z.array(z.string()),
  options: z.array(EventOptionSchema),
  pages: z.array(EventPageSchema),
  relics: z.array(z.string()),
  imageUrl: z.string().nullable(),
  translations: z.object({
    zhHans: EventTranslationSchema.optional(),
    ja: EventTranslationSchema.optional(),
  }).optional(),
});

const EventsFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  events: z.array(EventSchema),
});

const parsed = EventsFileSchema.parse(eventsData);

export type EventOption = z.infer<typeof EventOptionSchema>;
export type EventPage = z.infer<typeof EventPageSchema>;
export type Event = z.infer<typeof EventSchema>;

export const events: Event[] = parsed.events;
export const eventBySlug = new Map(events.map((event) => [event.slug, event]));

function localizedOptions(base: EventOption[], translated?: EventOption[]): EventOption[] {
  return base.map((option, index) => {
    const local = translated?.[index];
    return {
      ...option,
      title: local?.title || option.title,
      description: local?.description || option.description,
    };
  });
}

export function eventForLocale(event: Event, locale: Lang): Event {
  const key = translationKey(locale);
  const translated = key ? event.translations?.[key] : undefined;
  if (!translated) return event;
  const translatedPagesById = new Map(translated.pages.map((page) => [page.id, page]));
  return {
    ...event,
    name: translated.name || event.name,
    type: translated.type || event.type,
    act: translated.act ?? event.act,
    preconditions: translated.preconditions.length ? translated.preconditions : event.preconditions,
    options: localizedOptions(event.options, translated.options),
    pages: event.pages.map((page, index) => {
      const translatedPage = translatedPagesById.get(page.id) ?? translated.pages[index];
      return {
        ...page,
        options: localizedOptions(page.options, translatedPage?.options),
      };
    }),
  };
}

const booleanLabels: Record<Lang, { yes: string; no: string }> = {
  en: { yes: 'Yes', no: 'No' },
  zhs: { yes: '是', no: '否' },
  jpn: { yes: 'あり', no: 'なし' },
};

const allActsLabels: Record<Lang, string> = {
  en: 'All Acts',
  zhs: '全章节',
  jpn: '全ての章',
};

const eventTypeLabels: Record<Lang, Record<string, string>> = {
  en: { Event: 'Event', Ancient: 'Ancient' },
  zhs: { Event: '事件', Ancient: '先古' },
  jpn: { Event: 'イベント', Ancient: 'エンシェント' },
};

const actLabels: Record<Lang, Record<string, string>> = {
  en: {
    'Act 1 - Overgrowth': 'Act 1 - Overgrowth',
    'Act 1 - Underdocks': 'Act 1 - Underdocks',
    'Act 1 - Overgrowth / Underdocks': 'Act 1 - Overgrowth / Underdocks',
    'Act 2 - Hive': 'Act 2 - Hive',
    'Act 3 - Glory': 'Act 3 - Glory',
  },
  zhs: {
    'Act 1 - Overgrowth': '第一章 - 蔓生林地',
    'Act 1 - Underdocks': '第一章 - 地下码头',
    'Act 1 - Overgrowth / Underdocks': '第一章 - 蔓生林地 / 地下码头',
    'Act 2 - Hive': '第二章 - 蜂巢',
    'Act 3 - Glory': '第三章 - 荣耀',
  },
  jpn: {
    'Act 1 - Overgrowth': '第1章 - 過成長地帯',
    'Act 1 - Underdocks': '第1章 - 地下埠頭',
    'Act 1 - Overgrowth / Underdocks': '第1章 - 過成長地帯 / 地下埠頭',
    'Act 2 - Hive': '第2章 - 蜂の巣',
    'Act 3 - Glory': '第3章 - 栄光',
  },
};

const preconditionLabels: Record<Lang, Record<string, string>> = {
  en: {},
  zhs: {
    'Act 1 only': '仅第一章',
    'Act 1-2 only': '仅第一至第二章',
    'Act 2 only': '仅第二章',
    'Act 2+': '第二章及以后',
    'Cannot have an event pet': '不能已有事件宠物',
    'Floor 7+': '第 7 层及以后',
    'Requires 10+ HP': '需要 10 点以上生命',
    'Requires 100+ gold': '需要 100 以上金币',
    'Requires 100+ gold or a Foul Potion': '需要 100 以上金币或一瓶污浊药水',
    'Requires 100-149 gold': '需要 100-149 金币',
    'Requires 12+ HP': '需要 12 点以上生命',
    'Requires 120+ gold': '需要 120 以上金币',
    'Requires 125+ gold': '需要 125 以上金币',
    'Requires 150+ gold': '需要 150 以上金币',
    'Requires 19+ HP': '需要 19 点以上生命',
    'Requires 2+ Defends in deck': '牌组中需要 2 张以上防御',
    'Requires 2+ Strikes in deck': '牌组中需要 2 张以上打击',
    'Requires 44+ gold': '需要 44 以上金币',
    'Requires 5+ tradeable relics': '需要 5 件以上可交易遗物',
    'Requires 55+ gold': '需要 55 以上金币',
    'Requires a removable basic card': '需要一张可移除的基础牌',
    'Requires at least one potion': '需要至少一瓶药水',
    'Requires more than one character unlocked': '需要解锁超过一个角色',
    'Requires removable cards in deck': '牌组中需要可移除的牌',
    'Requires ≤70% HP': '需要当前生命不高于 70%',
    'Single player only': '仅限单人模式',
  },
  jpn: {
    'Act 1 only': '第1章のみ',
    'Act 1-2 only': '第1-2章のみ',
    'Act 2 only': '第2章のみ',
    'Act 2+': '第2章以降',
    'Cannot have an event pet': 'イベントペットを所持していないこと',
    'Floor 7+': '7階以降',
    'Requires 10+ HP': 'HP 10以上が必要',
    'Requires 100+ gold': '100ゴールド以上が必要',
    'Requires 100+ gold or a Foul Potion': '100ゴールド以上、または汚れたポーションが必要',
    'Requires 100-149 gold': '100-149ゴールドが必要',
    'Requires 12+ HP': 'HP 12以上が必要',
    'Requires 120+ gold': '120ゴールド以上が必要',
    'Requires 125+ gold': '125ゴールド以上が必要',
    'Requires 150+ gold': '150ゴールド以上が必要',
    'Requires 19+ HP': 'HP 19以上が必要',
    'Requires 2+ Defends in deck': 'デッキに防御が2枚以上必要',
    'Requires 2+ Strikes in deck': 'デッキにストライクが2枚以上必要',
    'Requires 44+ gold': '44ゴールド以上が必要',
    'Requires 5+ tradeable relics': '交換可能なレリックが5個以上必要',
    'Requires 55+ gold': '55ゴールド以上が必要',
    'Requires a removable basic card': '削除可能な基本カードが必要',
    'Requires at least one potion': 'ポーションが1個以上必要',
    'Requires more than one character unlocked': '複数のキャラクターをアンロックしていること',
    'Requires removable cards in deck': 'デッキに削除可能なカードが必要',
    'Requires ≤70% HP': 'HPが70%以下であること',
    'Single player only': 'シングルプレイのみ',
  },
};

function normalizedType(value: string | null | undefined, locale: Lang): string {
  const type = value === 'Shared' ? 'Event' : value || 'Event';
  return eventTypeLabels[locale]?.[type] ?? type;
}

function normalizedAct(value: string | null | undefined, type: string, locale: Lang): string | null {
  if (type === 'Shared') return allActsLabels[locale];
  const normalized = value === 'Underdocks' ? 'Act 1 - Underdocks' : value || null;
  return normalized ? actLabels[locale]?.[normalized] ?? normalized : null;
}

function localizedPreconditions(values: string[], locale: Lang): string[] {
  return values.map((value) => preconditionLabels[locale]?.[value] ?? value);
}

export function eventIndexRows(locale: Lang) {
  const labels = booleanLabels[locale];
  return events.map((event) => {
    const localized = eventForLocale(event, locale);
    const type = normalizedType(event.type, locale);
    const act = normalizedAct(localized.act, event.type, locale);
    const preconditions = localizedPreconditions(localized.preconditions, locale);
    return {
      slug: event.slug,
      name: localized.name,
      sortName: event.name,
      type,
      act: act || '-',
      preconditions: preconditions.length ? preconditions.join('; ') : '-',
      hasPreconditions: localized.preconditions.length ? labels.yes : labels.no,
      hasRelics: event.relics.length ? labels.yes : labels.no,
    };
  });
}

export function eventDisplay(event: Event, locale: Lang): Event {
  const localized = eventForLocale(event, locale);
  return {
    ...localized,
    type: normalizedType(event.type, locale),
    act: normalizedAct(localized.act, event.type, locale),
    preconditions: localizedPreconditions(localized.preconditions, locale),
  };
}

export function eventSourceUrl(event: Event, locale: Lang): string {
  const prefix = locale === 'en' ? '' : `/${locale}`;
  return `https://spire-codex.com${prefix}/events/${event.slug}`;
}
