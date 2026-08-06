import { defineMiddleware } from 'astro:middleware';

const localeByPrefix: Record<string, string> = {
  zhs: 'zh-Hans',
  jpn: 'ja',
};

export const onRequest = defineMiddleware(async ({ url }, next) => {
  const response = await next();
  const locale = localeByPrefix[url.pathname.split('/')[1] || ''];
  const contentType = response.headers.get('content-type') || '';

  if (!locale || !contentType.includes('text/html')) return response;

  const html = await response.text();
  return new Response(html.replace(/<html lang="[^"]+"/, `<html lang="${locale}"`), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
});
