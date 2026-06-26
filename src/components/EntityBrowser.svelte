<script lang="ts">
  type Column = {
    field: string;
    label: string;
    badge?: 'rarity' | 'type';
    format?: 'cardCost' | 'relicRarity';
    chips?: boolean;
  };
  type Filter = { field: string; label: string; multiple?: boolean };

  interface Props {
    entities: Record<string, any>[];
    linkBase: string;
    noun: string;
    nameLabel: string;
    columns: Column[];
    filters: Filter[];
  }

  let { entities, linkBase, noun, nameLabel, columns, filters }: Props = $props();

  let query = $state('');
  let selections: Record<string, string> = $state({});
  let sortField = $state('name');
  let sortDirection: 'asc' | 'desc' = $state('asc');
  let sortTouched = $state(false);
  for (const f of filters) if (!(f.field in selections)) selections[f.field] = '';

  const sortableColumns: Column[] = [{ field: 'name', label: nameLabel }, ...columns];
  const rarityRank: Record<string, number> = {
    basic: 0,
    common: 1,
    uncommon: 2,
    rare: 3,
    ancient: 4,
    special: 5,
    curse: 6,
    status: 7,
    token: 8,
    event: 9,
    'starter relic': 10,
    boss: 11,
    shop: 12,
  };

  const asArray = (v: any): string[] =>
    Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)];

  const distinct = (field: string) => {
    const set = new Set<string>();
    for (const e of entities) for (const v of asArray(e[field])) if (v && v !== '-') set.add(v);
    return [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  };

  const norm = (val: string) =>
    String(val).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

  const STAR_IMG =
    '<img class="star-icon" src="https://cdn.spire-codex.com/icons/star_icon.webp" alt="star" />';

  function costHtml(cr: any) {
    if (!cr) return '';
    if (cr.cost === -1 || cr.cost === -2) return 'Unplayable';
    if (cr.isXStar) return 'X ' + STAR_IMG;
    if (cr.isX) return 'X';
    if (cr.starCost !== null && cr.starCost !== undefined)
      return `${cr.cost}/${cr.starCost} ` + STAR_IMG;
    return String(cr.cost);
  }

  function costRank(cr: any): number {
    if (!cr) return Number.POSITIVE_INFINITY;
    if (cr.cost === -1 || cr.cost === -2) return 200;
    if (cr.isX || cr.isXStar) return 100;
    if (typeof cr.cost === 'number') {
      return cr.cost + (typeof cr.starCost === 'number' ? cr.starCost / 10 : 0);
    }
    return Number.POSITIVE_INFINITY;
  }

  function relicRarityHtml(rarity: string, poolColor: string) {
    if (rarity === 'Starter Relic' && poolColor) {
      return `<span class="tag" style="--tag-color:${poolColor}">Starter Relic</span>`;
    }
    return `<span class="tag tag--plain">${rarity}</span>`;
  }

  const haystack = (e: Record<string, any>) =>
    [e.name, ...columns.map((c) => (Array.isArray(e[c.field]) ? e[c.field].join(' ') : e[c.field]))]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

  const filterOptions = Object.fromEntries(filters.map((f) => [f.field, distinct(f.field)]));
  const searchable = entities.map((entity) => ({ entity, search: haystack(entity) }));
  const sortColumnsByField = Object.fromEntries(sortableColumns.map((col) => [col.field, col]));

  function sortValue(e: Record<string, any>, field: string) {
    const col = sortColumnsByField[field];
    if (col?.format === 'cardCost') return costRank(e.costRaw);
    if (field === 'rarity') {
      const key = String(e[field] ?? '').toLowerCase();
      return rarityRank[key] ?? 999;
    }
    const value = e[field];
    if (Array.isArray(value)) return value.join(', ');
    return value ?? '';
  }

  function compare(a: Record<string, any>, b: Record<string, any>) {
    const av = sortValue(a, sortField);
    const bv = sortValue(b, sortField);
    const direction = sortDirection === 'asc' ? 1 : -1;
    if (typeof av === 'number' && typeof bv === 'number' && av !== bv) return (av - bv) * direction;
    const primary = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
    if (primary !== 0) return primary * direction;
    return String(a.name).localeCompare(String(b.name), undefined, { numeric: true, sensitivity: 'base' });
  }

  const filtered = $derived(
    searchable.filter(({ entity: e, search }) => {
      const q = query.trim().toLowerCase();
      if (q && !search.includes(q)) return false;
      for (const f of filters) {
        const sel = selections[f.field];
        if (!sel) continue;
        if (f.multiple) {
          if (!asArray(e[f.field]).includes(sel)) return false;
        } else if (String(e[f.field]) !== sel) {
          return false;
        }
      }
      return true;
    }).map(({ entity }) => entity).sort(compare)
  );

  function setSort(field: string) {
    sortTouched = true;
    if (sortField === field) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortField = field;
      sortDirection = 'asc';
    }
  }

  function reset() {
    query = '';
    for (const f of filters) selections[f.field] = '';
    sortField = 'name';
    sortDirection = 'asc';
    sortTouched = false;
  }
</script>

<div class="card-browser">
  <div class="card-browser__controls">
    <label>
      <span>Search</span>
      <input type="search" bind:value={query} placeholder={`Search ${noun}`} />
    </label>
    {#each filters as f (f.field)}
      <label>
        <span>{f.label}</span>
        <select bind:value={selections[f.field]}>
          <option value="">All</option>
          {#each filterOptions[f.field] as value}
            <option value={value}>{value}</option>
          {/each}
        </select>
      </label>
    {/each}
    <button type="button" onclick={reset}>Reset</button>
  </div>

  <output class="card-browser__status">{filtered.length} of {entities.length} {noun}</output>

  <table>
    <thead>
      <tr>
        {#each sortableColumns as col (col.field)}
          <th aria-sort={sortField === col.field ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
            <button
              class="sort-button"
              type="button"
              onclick={() => setSort(col.field)}
            >
              <span>{col.label}</span>
              <span class="sort-arrow" aria-hidden="true">{sortTouched && sortField === col.field ? (sortDirection === 'asc' ? '↑' : '↓') : ''}</span>
            </button>
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each filtered as e (e.slug)}
        <tr>
          <td><a href={`${linkBase}${e.slug}/`}>{e.name}</a></td>
          {#each columns as col (col.field)}
            <td>
              {#if col.format === 'cardCost'}
                {@html costHtml(e.costRaw)}
              {:else if col.chips}
                {#each e[col.field] as k (k)}
                  <span class="kw kw-chip">{k}</span>
                {/each}
              {:else if col.badge}
                <span class={`tag tag--${col.badge}-${norm(String(e[col.field]))}`}>{e[col.field]}</span>
              {:else if col.format === 'relicRarity'}
                {@html relicRarityHtml(e[col.field], e.poolColor)}
              {:else if Array.isArray(e[col.field])}
                {e[col.field].join(', ')}
              {:else}
                {e[col.field]}
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
