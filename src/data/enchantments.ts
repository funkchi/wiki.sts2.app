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

export function enhancementIndexRows(locale: Lang) {
  const localeLabels = labels[locale];
  return enchantments.map((enchantment) => {
    const localized = enchantmentForLocale(enchantment, locale);
    return {
      slug: enchantment.slug,
      name: localized.name,
      sortName: enchantment.name,
      cardType: localized.cardType || localeLabels.any,
      applicableTo: localized.applicableTo || localeLabels.any,
      stackable: localized.isStackable ? localeLabels.yes : localeLabels.no,
      extraCardText: localized.extraCardText || '-',
    };
  });
}
