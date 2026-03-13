// LinkedIn Job URL Scraper — paste into browser console on LinkedIn Jobs search page
// Clicks through each job card, skips Easy Apply, collects external apply URLs, copies to clipboard
(async () => {
  const DELAY_MS = 1500; // delay between clicks to avoid throttling
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // --- Step 1: Find all job cards in the sidebar ---
  const cardSelectors = [
    ".jobs-search-results-list .job-card-container",
    ".jobs-search-results-list .job-card-list__entity-lockup",
    '[data-occludable-job-id]',
    ".scaffold-layout__list-container .jobs-search-results__list-item",
    "li.jobs-search-results__list-item",
    ".job-card-container--clickable",
  ];

  let cards = [];
  for (const sel of cardSelectors) {
    cards = document.querySelectorAll(sel);
    if (cards.length > 0) {
      console.log(`Found ${cards.length} job cards using: ${sel}`);
      break;
    }
  }

  if (cards.length === 0) {
    console.error(
      "No job cards found. Make sure you're on a LinkedIn Jobs search results page."
    );
    return;
  }

  // --- Step 2: Scroll the job list to load all lazy-loaded cards ---
  const listContainer =
    document.querySelector(".jobs-search-results-list") ||
    document.querySelector(".scaffold-layout__list-container");
  if (listContainer) {
    console.log("Scrolling to load all cards...");
    for (let i = 0; i < 5; i++) {
      listContainer.scrollTop = listContainer.scrollHeight;
      await sleep(800);
    }
    listContainer.scrollTop = 0;
    await sleep(500);
    // Re-query after scroll
    for (const sel of cardSelectors) {
      const fresh = document.querySelectorAll(sel);
      if (fresh.length > 0) {
        cards = fresh;
        break;
      }
    }
    console.log(`After scrolling: ${cards.length} cards`);
  }

  // --- Step 3: Click each card and extract apply URLs ---
  const results = [];
  let easyApplyCount = 0;
  let errorCount = 0;

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    try {
      // Click the card to load job details
      const clickTarget =
        card.querySelector("a") ||
        card.querySelector('[data-control-name]') ||
        card;
      clickTarget.click();
      await sleep(DELAY_MS);

      // Get job title from detail panel or card
      const titleEl =
        document.querySelector(".jobs-unified-top-card__job-title") ||
        document.querySelector(".job-details-jobs-unified-top-card__job-title") ||
        document.querySelector("h1.t-24") ||
        document.querySelector("h2.jobs-unified-top-card__job-title") ||
        card.querySelector(".job-card-list__title") ||
        card.querySelector("strong");
      const title = titleEl ? titleEl.textContent.trim() : `Job ${i + 1}`;

      // Get company name
      const companyEl =
        document.querySelector(".jobs-unified-top-card__company-name") ||
        document.querySelector(".job-details-jobs-unified-top-card__company-name") ||
        card.querySelector(".job-card-container__primary-description");
      const company = companyEl ? companyEl.textContent.trim() : "";

      // Check for Easy Apply
      const applyArea =
        document.querySelector(".jobs-apply-button--top-card") ||
        document.querySelector(".jobs-unified-top-card__content--two-pane .jobs-apply-button") ||
        document.querySelector('[class*="jobs-apply-button"]');

      if (applyArea) {
        const applyText = applyArea.textContent || "";
        if (applyText.toLowerCase().includes("easy apply")) {
          easyApplyCount++;
          console.log(`  [${i + 1}/${cards.length}] SKIP Easy Apply: ${title}`);
          continue;
        }
      }

      // Helper: extract external URL from LinkedIn redirect URLs
      const extractExternalUrl = (href) => {
        if (!href) return null;
        try {
          const u = new URL(href);
          // LinkedIn wraps external applies: /jobs/view/.../externalApply?url=<encoded>
          const embedded = u.searchParams.get("url") || u.searchParams.get("redirectUrl");
          if (embedded) return embedded;
        } catch (_) {}
        // If it's not a linkedin.com URL, it's already external
        if (!href.includes("linkedin.com")) return href;
        return null;
      };

      // Find the external Apply button/link
      const applyBtnSelectors = [
        'a.jobs-apply-button[href]',
        '.jobs-unified-top-card a[href*="externalApply"]',
        '.jobs-apply-button--top-card a[href]',
        'a[data-control-name="jobdetails_topcard_inapply"]',
        '.jobs-unified-top-card a.apply-button[href]',
        // Include linkedin.com links that may contain redirect params
        '.jobs-unified-top-card a[href]',
        '.job-details-jobs-unified-top-card__content a[href]',
      ];

      let applyUrl = null;
      for (const sel of applyBtnSelectors) {
        const btn = document.querySelector(sel);
        if (btn && btn.href) {
          applyUrl = extractExternalUrl(btn.href);
          if (applyUrl) break;
        }
      }

      // Sometimes the Apply button opens a redirect through LinkedIn
      // Check for the button that triggers external navigation
      if (!applyUrl) {
        const allApplyBtns = document.querySelectorAll(
          '.jobs-apply-button, [class*="apply-button"], button[aria-label*="Apply"]'
        );
        for (const btn of allApplyBtns) {
          const text = btn.textContent || "";
          // "Apply" (not "Easy Apply") usually means external
          if (
            text.trim().toLowerCase() === "apply" ||
            text.trim().toLowerCase().startsWith("apply to")
          ) {
            // Check if it's a link (may be LinkedIn redirect or direct external)
            const link = btn.closest("a") || btn.querySelector("a");
            if (link && link.href) {
              const extracted = extractExternalUrl(link.href);
              if (extracted) { applyUrl = extracted; break; }
            }
            // If it's a button that opens a new tab, the URL might be in a data attribute
            const dataUrl =
              btn.getAttribute("data-href") ||
              btn.getAttribute("data-url") ||
              btn.closest("[data-apply-url]")?.getAttribute("data-apply-url");
            if (dataUrl) {
              applyUrl = dataUrl;
              break;
            }
          }
        }
      }

      if (applyUrl) {
        // Clean tracking params
        try {
          const url = new URL(applyUrl);
          // Remove LinkedIn tracking params
          url.searchParams.delete("trk");
          url.searchParams.delete("refId");
          url.searchParams.delete("trackingId");
          applyUrl = url.toString();
        } catch (_) {
          // URL parsing failed, use as-is
        }
        results.push({ title, company, url: applyUrl });
        console.log(
          `  [${i + 1}/${cards.length}] ✓ ${title} @ ${company} → ${applyUrl.substring(0, 80)}...`
        );
      } else {
        // Could be Easy Apply without the badge, or a broken card
        console.log(
          `  [${i + 1}/${cards.length}] - No external URL: ${title} @ ${company}`
        );
      }
    } catch (err) {
      errorCount++;
      console.warn(`  [${i + 1}/${cards.length}] Error: ${err.message}`);
    }
  }

  // --- Step 4: Copy URLs to clipboard ---
  const urls = results.map((r) => r.url);
  if (urls.length > 0) {
    await navigator.clipboard.writeText(urls.join("\n"));
    console.log("\n========================================");
    console.log(`DONE — ${urls.length} external apply URLs copied to clipboard`);
    console.log(`  Easy Apply skipped: ${easyApplyCount}`);
    console.log(`  Errors: ${errorCount}`);
    console.log(`  Total cards processed: ${cards.length}`);
    console.log("========================================");
    console.log("\nPaste (Cmd+V) into JobHunter Quick Apply:\n");
    urls.forEach((u, i) => console.log(`${i + 1}. ${results[i].title} → ${u}`));
  } else {
    console.log("\n========================================");
    console.log("No external apply URLs found.");
    console.log(`  Easy Apply skipped: ${easyApplyCount}`);
    console.log(`  Total cards processed: ${cards.length}`);
    console.log(
      "  Try scrolling down to load more jobs, or check if the page structure changed."
    );
    console.log("========================================");
  }
})();
