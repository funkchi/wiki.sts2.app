import { z } from 'astro:schema';
import cardsData from '../../data/wiki/cards.json';

const CardSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  color: z.string().nullable(),
  character: z.string(),
  type: z.string(),
  rarity: z.string(),
  cost: z.string(),
  costRaw: z.object({
    cost: z.number().nullable(),
    starCost: z.number().nullable(),
    isX: z.boolean(),
    isXStar: z.boolean(),
  }),
  upgradeCost: z.number().nullable(),
  target: z.string(),
  description: z.string(),
  upgradeDescription: z.string(),
  keywords: z.array(z.string()),
  matchedKeywords: z.array(z.string()),
  image: z.string(),
  imageUpg: z.string().nullable(),
  related: z.array(z.string()),
});

const CardsFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  cards: z.array(CardSchema),
});

const parsed = CardsFileSchema.parse(cardsData);

export type Card = z.infer<typeof CardSchema>;
export const cards: Card[] = parsed.cards;
export const cardBySlug = new Map(cards.map((c) => [c.slug, c]));
