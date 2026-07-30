import { z } from 'astro:schema';
import enchantmentsData from '../../data/wiki/enchantments.json';
import { translationKey, type Lang } from './i18n';

const EnchantmentTranslationSchema = z.object({
  name: z.string(),
  description: z.string(),
  extraCardText: z.string(),
  cardType: z.string().nullable(),
  applicableTo: z.string().nullable(),
});

const EnchantmentSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  extraCardText: z.string(),
  cardType: z.string().nullable(),
  applicableTo: z.string().nullable(),
  isStackable: z.boolean(),
  image: z.string().nullable(),
  translations: z.object({
    zhHans: EnchantmentTranslationSchema.optional(),
    ja: EnchantmentTranslationSchema.optional(),
  }).optional(),
});

const EnchantmentsFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  enchantments: z.array(EnchantmentSchema),
});

const parsed = EnchantmentsFileSchema.parse(enchantmentsData);

export type Enchantment = z.infer<typeof EnchantmentSchema>;

export const enchantments: Enchantment[] = parsed.enchantments;
export const enchantmentBySlug = new Map(enchantments.map((enchantment) => [enchantment.slug, enchantment]));

export function enchantmentForLocale(enchantment: Enchantment, locale: Lang): Enchantment {
  const key = translationKey(locale);
  const translated = key ? enchantment.translations?.[key] : undefined;
  if (!translated) return enchantment;
  return {
    ...enchantment,
    name: translated.name || enchantment.name,
    description: translated.description || enchantment.description,
    extraCardText: translated.extraCardText || enchantment.extraCardText,
    cardType: translated.cardType ?? enchantment.cardType,
    applicableTo: translated.applicableTo ?? enchantment.applicableTo,
  };
}

const labels: Record<Lang, { yes: string; no: string; any: string }> = {
  en: { yes: 'Yes', no: 'No', any: 'Any' },
  zhs: { yes: '是', no: '否', any: '任意' },
  jpn: { yes: 'あり', no: 'なし', any: '任意' },
};

const cardTypeLabels: Record<Lang, Record<string, string>> = {
  en: {},
  zhs: {
    Attack: '攻击',
    Skill: '技能',
    'Attack, Skill': '攻击、技能',
  },
  jpn: {
    Attack: 'アタック',
    Skill: 'スキル',
    'Attack, Skill': 'アタック、スキル',
  },
};

const applicableToLabels: Record<Lang, Record<string, string>> = {
  en: {},
  zhs: {
    'Basic Strike or Defend cards': '基础打击或防御牌',
    'Defend cards': '防御牌',
    'cards that gain Block': '获得格挡的牌',
  },
  jpn: {
    'Basic Strike or Defend cards': '基本のストライクまたは防御カード',
    'Defend cards': '防御カード',
    'cards that gain Block': 'ブロックを得るカード',
  },
};

export function localizedCardType(value: string | null | undefined, locale: Lang): string | null {
  if (!value) return null;
  return cardTypeLabels[locale]?.[value] ?? value;
}

export function localizedApplicableTo(value: string | null | undefined, locale: Lang): string | null {
  if (!value) return null;
  return applicableToLabels[locale]?.[value] ?? value;
}

export function enhancementIndexRows(locale: Lang) {
  const localeLabels = labels[locale];
  return enchantments.map((enchantment) => {
    const localized = enchantmentForLocale(enchantment, locale);
    return {
      slug: enchantment.slug,
      name: localized.name,
      sortName: enchantment.name,
      cardType: localizedCardType(localized.cardType, locale) || localeLabels.any,
      applicableTo: localizedApplicableTo(localized.applicableTo, locale) || localeLabels.any,
      stackable: localized.isStackable ? localeLabels.yes : localeLabels.no,
      extraCardText: localized.extraCardText || '-',
    };
  });
}
