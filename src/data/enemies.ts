import { z } from 'astro:schema';
import enemiesData from '../../data/wiki/enemies.json';

const MoveSchema = z.object({
  name: z.string(),
  intent: z.string(),
  damage: z.string(),
  block: z.string(),
  heal: z.string(),
});

const EncounterSchema = z.object({
  name: z.string(),
  roomType: z.string(),
  act: z.string().nullable(),
});
const EnemyTranslationSchema = z.object({
  name: z.string(),
  type: z.string(),
  pattern: z.string(),
  moves: z.array(MoveSchema),
  encounters: z.array(EncounterSchema),
  encounterNames: z.array(z.string()),
  movesSummary: z.string(),
});

const EnemySchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  type: z.string(),
  hp: z.string(),
  pattern: z.string(),
  moves: z.array(MoveSchema),
  encounters: z.array(EncounterSchema),
  encounterNames: z.array(z.string()),
  acts: z.array(z.string()),
  movesSummary: z.string(),
  image: z.string(),
  translations: z.object({
    zhHans: EnemyTranslationSchema.optional(),
    ja: EnemyTranslationSchema.optional(),
  }).optional(),
});

const EnemiesFileSchema = z.object({
  schemaVersion: z.number(),
  kind: z.string(),
  count: z.number(),
  enemies: z.array(EnemySchema),
});

const parsed = EnemiesFileSchema.parse(enemiesData);

export type Enemy = z.infer<typeof EnemySchema>;
export const enemies: Enemy[] = parsed.enemies;
export const enemyBySlug = new Map(enemies.map((e) => [e.slug, e]));
