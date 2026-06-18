const ALLOWED_EVENTS = new Set(["navigation", "search", "search_empty"]);

function cleanString(value, limit) {
  return typeof value === "string"
    ? value.replace(/\s+/g, " ").trim().slice(0, limit)
    : "";
}

function cleanPath(value) {
  const path = cleanString(value, 240);
  return path.startsWith("/") && !path.includes("\\") ? path : "";
}

function response(status) {
  return new Response(null, {
    status,
    headers: {
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method !== "POST") {
    return response(405);
  }

  const requestUrl = new URL(request.url);
  const origin = request.headers.get("origin");
  if (origin && origin !== requestUrl.origin) {
    return response(403);
  }

  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 2048) {
    return response(413);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return response(400);
  }

  const event = cleanString(payload.event, 32);
  const path = cleanPath(payload.path);
  const target = cleanPath(payload.target);
  const value = cleanString(payload.value, 80).toLowerCase();
  const count = Math.max(0, Math.min(10000, Number(payload.count) || 0));
  if (!ALLOWED_EVENTS.has(event) || !path || (event === "navigation" && !target)) {
    return response(400);
  }
  if (!env.WIKI_ANALYTICS) {
    return response(503);
  }

  env.WIKI_ANALYTICS.writeDataPoint({
    blobs: [event, path, target, value],
    doubles: [count],
    indexes: [event],
  });
  return response(204);
}
