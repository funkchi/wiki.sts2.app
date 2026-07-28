export async function onRequest(context) {
  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    return new Response("Method not allowed", {
      status: 405,
      headers: { allow: "GET, HEAD" },
    });
  }

  const parts = Array.isArray(context.params.path)
    ? context.params.path
    : [context.params.path];
  const key = parts.filter(Boolean).join("/");

  if (!/^(cards|characters|relics|enemies|enchantments|events)\/[a-z0-9_-]+\.webp$/.test(key)) {
    return new Response("Not found", { status: 404 });
  }

  const object = await context.env.WIKI_MEDIA.get(key);
  if (!object) {
    return new Response("Not found", { status: 404 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  headers.set("cache-control", "public, max-age=86400, s-maxage=604800");
  headers.set("x-content-type-options", "nosniff");

  const body = context.request.method === "HEAD" ? null : object.body;
  return new Response(body, { headers });
}
