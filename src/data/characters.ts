import { z } from 'astro:schema';
import charactersData from '../../data/wiki/characters.json';

const DeckCardSchema = z.object({
  slug: z.string(),
  name: z.string(),
  count: z.number(),
});
const RelicSchema = z.object({ slug: z.string(), name: z.string() });
const QuoteSchema = z.object({ label: z.string(), text: z.string() });

const CharacterSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  color: z.string(),
  character: z.string(),
  description: z.string(),
  image: z.string(),
  icon: z.string(),
  startingHp: z.number().nullable(),
  startingGold: z.number().nullable(),
  maxEnergy: z.number().nullable(),
  orbSlots: z.number().nullable(),
  unlocksAfter: z.string(),
  startingDeck: z.array(DeckCardSchema),
  startingRelics: z.array(RelicSchema),
  quotes: z.array(QuoteSchema),
});

const CharactersFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  characters: z.array(CharacterSchema),
});

const parsed = CharactersFileSchema.parse(charactersData);

export type Character = z.infer<typeof CharacterSchema>;
export const characters: Character[] = parsed.characters;
export const characterBySlug = new Map(characters.map((c) => [c.slug, c]));

const characterAccent: Record<string, string> = {
  ironclad: '#e0534a',
  silent: '#6cbf6b',
  defect: '#4f9cf0',
  necrobinder: '#a98aff',
  regent: '#f0a24a',
};

export function accentFor(slug: string): string {
  return characterAccent[slug] ?? '#4fd1c5';
}

export const poolAccent: Record<string, string> = {
  ironclad: '#e0534a',
  silent: '#6cbf6b',
  defect: '#4f9cf0',
  necrobinder: '#a98aff',
  regent: '#f0a24a',
  shared: '#8b95a3',
};

export function poolColor(poolRaw: string | null | undefined): string {
  return poolAccent[String(poolRaw ?? '').toLowerCase()] ?? '#8b95a3';
}
