import { z } from 'astro:schema';
import relicsData from '../../data/wiki/relics.json';

const RelicTranslationSchema = z.object({
  name: z.string(),
  description: z.string(),
  rarity: z.string(),
  pool: z.string(),
  flavor: z.string(),
  notes: z.array(z.string()),
});

const RelicSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  rarity: z.string(),
  pool: z.string(),
  poolRaw: z.string().nullable(),
  price: z.string(),
  flavor: z.string(),
  notes: z.array(z.string()),
  image: z.string(),
  related: z.array(z.string()),
  translations: z.object({
    zhHans: RelicTranslationSchema.optional(),
    ja: RelicTranslationSchema.optional(),
  }).optional(),
});

const RelicsFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  relics: z.array(RelicSchema),
});

const parsed = RelicsFileSchema.parse(relicsData);

export type Relic = z.infer<typeof RelicSchema>;
export const relics: Relic[] = parsed.relics;
export const relicBySlug = new Map(relics.map((r) => [r.slug, r]));
