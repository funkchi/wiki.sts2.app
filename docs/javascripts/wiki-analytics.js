(() => {
  const endpoint = "/api/analytics";

  function send(payload) {
    const body = JSON.stringify({ path: location.pathname, ...payload });
    if (navigator.sendBeacon) {
      const queued = navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
      if (queued) return;
    }
    fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => {});
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || target.pathname === location.pathname) return;
    send({ event: "navigation", target: target.pathname });
  });

  function mountSearch() {
    const input = document.querySelector("input.md-search__input");
    if (!input || input.dataset.analyticsMounted) return;
    input.dataset.analyticsMounted = "true";
    let timer;
    let lastQuery = "";
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const query = input.value.replace(/\s+/g, " ").trim().slice(0, 80);
        if (query.length < 2 || query === lastQuery) return;
        lastQuery = query;
        const count = document.querySelectorAll(".md-search-result__link").length;
        send({ event: "search", value: query, count });
        if (count === 0) send({ event: "search_empty", value: query, count: 0 });
      }, 900);
    });
  }

  mountSearch();
  document.addEventListener("DOMContentSwitch", mountSearch);
})();
