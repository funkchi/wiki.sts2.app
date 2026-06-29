import starlight from '@astrojs/starlight';
import svelte from '@astrojs/svelte';
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';

// Phase-1 spike: Astro + Starlight + Svelte, cards only.
// Editorial pages live in Starlight's content collection; entity pages are
// data-driven custom routes under /docs/cards/ wrapped in <StarlightPage>.
export default defineConfig({
  site: 'https://wiki.sts2.app',
  output: 'static',
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'Slay the Spire 2 Wiki',
      tableOfContents: false,
      customCss: ['./src/styles/global.css'],
      components: {
        Head: './src/components/Head.astro',
        LanguageSelect: './src/components/LanguageToggle.astro',
      },
      sidebar: [
        { label: 'Cards', link: '/docs/cards/' },
        { label: 'Relics', link: '/docs/relics/' },
        { label: 'Enemies', link: '/docs/enemies/' },
        { label: 'Characters', link: '/docs/characters/' },
        { label: 'Guides', slug: 'guides' },
        { label: 'About', slug: 'about' },
        { label: 'Privacy', slug: 'privacy' },
        { label: 'Contact', slug: 'contact' },
        { label: 'Disclaimer', slug: 'disclaimer' },
      ],
    }),
    svelte(),
    sitemap({
      serialize(item) {
        const SITE = 'https://wiki.sts2.app';
        const path = item.url.startsWith(SITE) ? item.url.slice(SITE.length) : new URL(item.url).pathname;
        const localeMatch = path.match(/^\/(zhs|jpn)(?=\/|$)/);
        const enPath = localeMatch ? path.replace(/^\/(zhs|jpn)/, '') || '/' : path;
        const zhPath = `/zhs${enPath === '/' ? '/' : enPath}`;
        const jaPath = `/jpn${enPath === '/' ? '/' : enPath}`;
        // Only entity (/docs/*) and landing (/) have localized counterparts.
        if (enPath.startsWith('/docs/') || enPath === '/') {
          item.links = [
            { url: `${SITE}${enPath}`, lang: 'en' },
            { url: `${SITE}${zhPath}`, lang: 'zh-Hans' },
            { url: `${SITE}${jaPath}`, lang: 'ja' },
          ];
        }
        return item;
      },
    }),
  ],
});
