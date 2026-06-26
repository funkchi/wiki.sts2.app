(() => {
  const storageKey = "wiki-sts2-consent-v1";
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };

  function updateConsent(value) {
    const granted = value === "granted" ? "granted" : "denied";
    window.gtag("consent", "update", {
      ad_storage: granted,
      ad_user_data: granted,
      ad_personalization: granted,
    });
  }

  window.gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    wait_for_update: 500,
  });

  let choice = null;
  try { choice = localStorage.getItem(storageKey); } catch {}
  if (choice) updateConsent(choice);

  function addStyles() {
    if (document.getElementById("wiki-consent-styles")) return;
    const style = document.createElement("style");
    style.id = "wiki-consent-styles";
    style.textContent = `
      .wiki-consent{position:fixed;z-index:1000;inset:auto 1rem 1rem;max-width:680px;margin:auto;padding:1rem;border:1px solid #6f6578;border-radius:6px;background:#17111e;color:#f7f2f8;box-shadow:0 12px 40px #0006;font:400 14px/1.5 system-ui,sans-serif}
      .wiki-consent[hidden]{display:none}.wiki-consent p{margin:0}.wiki-consent a{color:#d6b7ff}.wiki-consent__actions{display:flex;flex-wrap:wrap;gap:.65rem;margin-top:.85rem}.wiki-consent button{min-height:40px;padding:.5rem .85rem;border:1px solid #95879f;border-radius:4px;background:transparent;color:inherit;font:600 14px system-ui,sans-serif;cursor:pointer}.wiki-consent button[data-choice="granted"]{border-color:#d6b7ff;background:#d6b7ff;color:#17111e}
    `;
    document.head.appendChild(style);
  }

  function closeBanner(banner, value) {
    try { localStorage.setItem(storageKey, value); } catch {}
    updateConsent(value);
    banner.hidden = true;
  }

  function openBanner() {
    addStyles();
    let banner = document.getElementById("wiki-consent");
    if (!banner) {
      banner = document.createElement("aside");
      banner.id = "wiki-consent";
      banner.className = "wiki-consent";
      banner.setAttribute("aria-label", "Advertising privacy choices");
      banner.innerHTML = `
        <p>We use Google AdSense to support this wiki. You can allow personalized advertising or continue with non-personalized advertising signals. Cloudflare analytics remains cookie-free. <a href="/privacy/">Privacy details</a></p>
        <div class="wiki-consent__actions">
          <button type="button" data-choice="denied">Reject optional advertising</button>
          <button type="button" data-choice="granted">Allow personalized advertising</button>
        </div>`;
      banner.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-choice]");
        if (button) closeBanner(banner, button.dataset.choice);
      });
      document.body.appendChild(banner);
    }
    banner.hidden = false;
  }

  window.wikiConsent = { open: openBanner };
  if (!choice) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", openBanner);
    else openBanner();
  }
})();
