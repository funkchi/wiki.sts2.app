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

function normalizedType(value: string | null | undefined): string {
  return value === 'Shared' ? 'Event' : value || 'Event';
}

function normalizedAct(value: string | null | undefined, type: string, locale: Lang): string | null {
  if (type === 'Shared') return allActsLabels[locale];
  if (value === 'Underdocks') return 'Act 1 - Underdocks';
  return value || null;
}

export function eventIndexRows(locale: Lang) {
  const labels = booleanLabels[locale];
  return events.map((event) => {
    const localized = eventForLocale(event, locale);
    const type = normalizedType(event.type);
    const act = normalizedAct(localized.act, event.type, locale);
    return {
      slug: event.slug,
      name: localized.name,
      sortName: event.name,
      type,
      act: act || '-',
      preconditions: localized.preconditions.length ? localized.preconditions.join('; ') : '-',
      hasPreconditions: localized.preconditions.length ? labels.yes : labels.no,
      hasRelics: event.relics.length ? labels.yes : labels.no,
    };
  });
}

export function eventDisplay(event: Event, locale: Lang): Event {
  const localized = eventForLocale(event, locale);
  return {
    ...localized,
    type: normalizedType(event.type),
    act: normalizedAct(localized.act, event.type, locale),
  };
}

export function eventSourceUrl(event: Event, locale: Lang): string {
  const prefix = locale === 'en' ? '' : `/${locale}`;
  return `https://spire-codex.com${prefix}/events/${event.slug}`;
}
