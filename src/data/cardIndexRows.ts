import { cards, type Card } from './cards';
import { localizedCharacterLabel, translationKey, type Lang } from './i18n';

export type CardIndexRow = {
  slug: string;
  name: string;
  sortName: string;
  character: string;
  cost: string;
  costRaw: Card['costRaw'];
  type: string;
  rarity: string;
  keywords: string[];
};

export function cardIndexRows(locale: Lang): CardIndexRow[] {
  const key = translationKey(locale);

  return cards.map((card) => {
    const translation = key ? card.translations?.[key] : undefined;

    return {
      slug: card.slug,
      name: translation?.name || card.name,
      sortName: card.name,
      character: localizedCharacterLabel(locale, card.character),
      cost: card.cost,
      costRaw: card.costRaw,
      type: translation?.type || card.type,
      rarity: translation?.rarity || card.rarity,
      keywords: translation?.keywords?.length ? translation.keywords : card.matchedKeywords,
    };
  });
}
