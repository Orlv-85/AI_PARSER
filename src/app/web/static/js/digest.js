      const dateInput = document.getElementById("digest-date");
      const heroTitle = document.getElementById("digest-hero-title");
      const emptyState = document.getElementById("digest-empty-state");
      const emptyText = document.getElementById("digest-empty-text");
      const dailyLinkList = document.getElementById("daily-link-list");
      const results = document.getElementById("digest-results");
      const weeklySummary = document.getElementById("weekly-preview-summary");
      const weeklyNew = document.getElementById("weekly-preview-new");
      const weeklyTrendingUp = document.getElementById("weekly-preview-trending-up");
      const weeklyTrendingDown = document.getElementById("weekly-preview-trending-down");

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }

      function renderDigest(payload) {
        if (!payload.groups.length) {
          results.innerHTML = "";
          emptyState.classList.remove("hidden");
          void loadDailyLinks(payload.report_date);
          return;
        }

        emptyState.classList.add("hidden");
        dailyLinkList.innerHTML = "";
        results.innerHTML = payload.groups
          .map((group) => {
            const items = group.items
              .map(
                (item) => `
                  <li class="digest-item">
                    <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
                    <p>${escapeHtml(item.summary)}</p>
                  </li>
                `,
              )
              .join("");

            return `
              <section class="digest-group">
                <h2>${escapeHtml(group.title)}</h2>
                <ul class="digest-list">${items}</ul>
              </section>
            `;
          })
          .join("");
      }

      const signalsBody = document.getElementById("daily-signals-body");
      const SIGNALS_UNAVAILABLE = "Daily signals are not available for this date yet.";
      const SIGNALS_ERROR = "Daily signals are temporarily unavailable.";
      const SIGNALS_LOADING = "Loading daily signals...";
      const SIGNALS_AI_NOTE = "Written by AI from the linked articles; check the sources.";
      // Hard event types shown as chips (HARD_EVENTS in daily_signals_brief); others fold into "+N more".
      const HARD_EVENTS = ["model_release", "product_launch", "funding", "acquisition", "partnership",
        "infrastructure_deal", "hardware", "regulation_policy", "legal", "security_incident", "people_move"];

      const EVENT_SINGULAR = {
        "model releases": "model release", "product launches": "product launch",
        "funding rounds": "funding round", "acquisitions": "acquisition",
        "partnerships": "partnership", "infrastructure deals": "infrastructure deal",
        "security incidents": "security incident", "people moves": "people move",
        "benchmark results": "benchmark result",
      };

      function eventLabel(count, label) {
        return count + " " + (count === 1 ? EVENT_SINGULAR[label] || label : label);
      }

      function signalStatus(text) {
        return `<p class="signals-status">${escapeHtml(text)}</p>`;
      }

      function signalLinks(links, quote) {
        const items = (links || []).filter((link) => /^https?:\/\//i.test(link.url))
          .map((link) => `<li><a href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">${escapeHtml(link.title)}</a> <span>${escapeHtml(link.publisher)}</span></li>`)
          .join("");
        const said = quote ? `<p class="signal-quote">Source says: "${escapeHtml(quote)}"</p>` : "";
        if (!items && !said) return "";
        return `<details class="signal-sources"><summary>sources</summary><ul class="signal-links">${items}</ul>${said}</details>`;
      }

      function signalMeta(parts) {
        return `<p class="signal-meta">${parts.filter(Boolean).map(escapeHtml).join(" &middot; ")}</p>`;
      }

      function outletCount(count) {
        return count + " outlet" + (count === 1 ? "" : "s");
      }

      function signalTrend(item) {
        let counts = item.current_7d != null
          ? `7d: ${item.previous_7d} &rarr; ${item.current_7d} (expected ${Number(item.expected_7d)})`
          : (item.trailing_mean ? `today ${item.today} vs ${Number(item.trailing_mean)}/day` : `today ${item.today} vs none before`);
        if (item.reason) counts += ` - ${escapeHtml(item.reason)}`;
        const badge = item.spike ? ' <span class="signal-badge">spike</span>' : "";
        return `<li><strong>${escapeHtml(item.name)}</strong>${badge}<p class="signal-meta">${counts}</p>${signalLinks(item.links)}</li>`;
      }

      function signalCard(title, body, note, id, empty) {
        const text = note || (body ? "" : empty);
        const noteHtml = text ? `<p class="signal-note">${escapeHtml(text)}</p>` : "";
        return `<section class="signal-card" id="${id}"><h3>${escapeHtml(title)}</h3>${noteHtml}<ul class="signal-list">${body}</ul></section>`;
      }

      function signalQuietLine(payload) {
        const multi = (payload.top_stories || []).length;
        const stories = multi ? `${multi} ${multi === 1 ? "story" : "stories"}` : "no story";
        return `Quiet day: ${(payload.coverage || {}).items || 0} items, ${stories} covered by more than one outlet.`;
      }

      function signalBrief(payload) {
        const quiet = payload.quiet ? `<p class="signal-quiet">${escapeHtml(signalQuietLine(payload))}</p>` : "";
        const items = ((payload.brief && payload.brief.sentences) || []).map((sentence) => {
          const refs = (sentence.links || []).filter((link) => /^https?:\/\//i.test(link.url))
            .map((link, i) => ` <a class="signal-ref" href="${escapeHtml(link.url)}" title="${escapeHtml(link.title)}" target="_blank" rel="noreferrer">[${i + 1}]</a>`)
            .join("");
          return `<li>${escapeHtml(sentence.text)}${refs}</li>`;
        });
        if (!quiet && !items.length) return "";
        const sentences = items.length ? `<ul class="signal-brief">${items.join("")}</ul>` : "";
        const note = items.length ? `<p class="signal-ai-note">${escapeHtml(SIGNALS_AI_NOTE)}</p>` : "";
        return `<div class="signal-brief-block"><h3>In brief</h3>${quiet}${sentences}${note}</div>`;
      }

      function signalChips(payload) {
        const counts = (payload.event_counts || []).filter((c) => c.stories);
        const hard = counts.filter((c) => HARD_EVENTS.includes(c.event_type));
        const soft = counts.filter((c) => !HARD_EVENTS.includes(c.event_type));
        let chips = hard.map((c) => `<li class="signal-chip">${escapeHtml(eventLabel(c.stories, c.label))}</li>`).join("");
        if (soft.length) {
          const title = soft.map((c) => eventLabel(c.stories, c.label)).join(", ");
          const more = soft.reduce((sum, c) => sum + c.stories, 0);
          chips += `<li class="signal-chip signal-chip-more" title="${escapeHtml(title)}">+${more} more</li>`;
        }
        return `<ul class="signal-chips">${chips}</ul>`;
      }

      function signalNewItem(item) {
        const confirmed = item.level === "confirmed";
        const links = item.links || [];
        const source = confirmed || !links.length ? outletCount(item.publishers) : `via ${links[0].publisher}`;
        const line = item.one_liner
          ? `<p class="signal-what">${escapeHtml(item.one_liner_source === "quote" ? `"${item.one_liner}"` : item.one_liner)}</p>`
          : "";
        const variant = item.variant_of ? `<p class="signal-meta">variant of ${escapeHtml(item.variant_of)}</p>` : "";
        const also = (item.variants || []).length ? `<p class="signal-meta">also: ${escapeHtml(item.variants.join(", "))}</p>` : "";
        const quote = item.one_liner_source === "quote" ? null : item.novelty_quote;
        return `<li class="${confirmed ? "signal-confirmed" : "signal-muted"}"><strong>${escapeHtml(item.name)}</strong>${signalMeta([item.type, item.vendor, source])}${line}${variant}${also}${signalLinks(links, quote)}</li>`;
      }

      function renderSignals(payload) {
        if (!payload || payload.status === "unavailable") {
          signalsBody.innerHTML = signalStatus((payload && payload.notes && payload.notes[0]) || SIGNALS_UNAVAILABLE);
          return;
        }
        const sections = payload.sections || {};
        const labels = Object.fromEntries((payload.event_counts || []).map((c) => [c.event_type, eventLabel(1, c.label).split(" ").slice(1).join(" ")]));
        const cov = payload.coverage || {};
        let lines = payload.status === "partial"
          ? signalStatus(`Extracted ${cov.extracted}/${cov.items} digest items; signals may be incomplete.`)
          : (payload.notes || []).map(signalStatus).join("");
        const newList = payload.new || [];
        const stories = (payload.top_stories || []).map((story) => {
          const spikes = (story.spikes || []).length ? `spike: ${story.spikes.join(", ")}` : null;
          return `<li><strong>${escapeHtml(story.label)}</strong>${signalMeta([outletCount(story.publishers), labels[story.event_type], spikes])}${signalLinks(story.links)}</li>`;
        }).join("");
        const rising = sections.rising || {};
        const spikesOnly = rising.state === "spikes_only";
        // A quiet day shows only cards that have items (no empty-state cards, FR-006).
        const hideSpikes = !(payload.rising || []).length && (payload.quiet || spikesOnly);
        if (hideSpikes && !payload.quiet && rising.note) lines += signalStatus(rising.note);
        const cards = [];
        if (newList.length || !payload.quiet) {
          cards.push(signalCard("New", newList.map(signalNewItem).join(""), sections.new && sections.new.note, "signals-new", "Nothing was first seen in our corpus on this date."));
        }
        if ((payload.top_stories || []).length || !payload.quiet) {
          cards.push(signalCard("Top stories", stories, sections.top_stories && sections.top_stories.note, "signals-top", "No story was covered by more than one publisher."));
        }
        if (!hideSpikes) {
          cards.push(signalCard(spikesOnly ? "Spikes" : "Rising", (payload.rising || []).map(signalTrend).join(""), payload.quiet ? null : rising.note, "signals-rising", "Nothing is rising or spiking on this date."));
        }
        const grid = cards.length ? `<div class="signal-grid cols-${cards.length}">${cards.join("")}</div>` : "";
        const cooling = sections.cooling && sections.cooling.state === "ready"
          ? `<details class="signal-cooling"><summary>Cooling (${(payload.cooling || []).length})</summary><ul class="signal-list">${(payload.cooling || []).map(signalTrend).join("")}</ul></details>`
          : "";
        signalsBody.innerHTML = `${signalBrief(payload)}${signalChips(payload)}${lines}${grid}${cooling}`;
      }

      async function loadSignals(selectedDate) {
        // Never keep the previous date's signals on screen while the new date loads.
        signalsBody.innerHTML = signalStatus(SIGNALS_LOADING);
        let payload = null;
        let failed = false;
        try {
          const response = await fetch("/api/news/daily-signals?date=" + encodeURIComponent(selectedDate));
          if (response.ok) {
            payload = await response.json();
          } else {
            failed = true;
          }
        } catch (_error) {
          failed = true;
        }
        // Ignore a late answer for a date that is no longer selected.
        if (dateInput.value !== selectedDate) return;
        if (failed) {
          signalsBody.innerHTML = signalStatus(SIGNALS_ERROR);
          return;
        }
        renderSignals(payload);
      }

      function renderWeeklyPreviewList(node, items, message, limit = 3) {
        if (!items.length) {
          node.innerHTML = `<li class="preview-empty">${escapeHtml(message)}</li>`;
          return;
        }

        node.innerHTML = items.slice(0, limit)
          .map(
            (item) => `
              <li>
                <a href="${/^https?:\/\//i.test(item.url) ? escapeHtml(item.url) : ""}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
                ${item.delta_pp == null ? "" : `<p>Share: ${(100 * Number(item.share_previous)).toFixed(1)}% → ${(100 * Number(item.share_current)).toFixed(1)}% (${Number(item.delta_pp).toFixed(2)} pp)</p>`}
                <p>${escapeHtml(node.id === "weekly-preview-reviews" ? item.summary.replace(/ Comparable coverage is insufficient to confirm an attention trend\.$/, "") : truncateText(item.summary, 360))}</p>
              </li>
            `,
          )
          .join("");
      }

      function truncateText(value, maxLength) {
        const text = String(value || "").replace(/\s+/g, " ").trim();
        return text.length > maxLength ? text.slice(0, maxLength - 1) + "…" : text;
      }

      function updateHeroTitle(selectedDate) {
        heroTitle.textContent =
          selectedDate === defaultReportDate
            ? "Yesterday's Digest"
            : "Digest for " + selectedDate;
      }

      async function loadCollectionStatus() {
        try {
          const response = await fetch("/api/news/collection-status");
          if (!response.ok) return;
          const payload = await response.json();
          const notice = document.getElementById("collection-paused-notice");
          if (payload.paused && payload.message) {
            notice.textContent = payload.message;
            notice.classList.remove("hidden");
          } else {
            notice.textContent = "";
            notice.classList.add("hidden");
          }
        } catch (_error) {
          return;
        }
      }

      async function loadWeeklyPreview(selectedDate) {
        document.getElementById("weekly-topic-reviews").classList.add("hidden");
        const response = await fetch("/api/news/weekly-analytics?date=" + encodeURIComponent(selectedDate));
        if (!response.ok) {
          weeklySummary.textContent = "Weekly analytics are unavailable right now.";
          weeklyNew.innerHTML = '<li class="preview-empty">Unavailable.</li>';
          weeklyTrendingUp.innerHTML = '<li class="preview-empty">Unavailable.</li>';
          weeklyTrendingDown.innerHTML = '<li class="preview-empty">Unavailable.</li>';
          return;
        }

        const payload = await response.json();
        weeklySummary.textContent = payload.summary;
        const reviews = ["new", "trending_up", "trending_down", "other_signals"]
          .flatMap((section) => payload[section] || []).filter((item) => item.claims?.length);
        if (reviews.length) {
          document.getElementById("weekly-topic-reviews").classList.remove("hidden");
          document.getElementById("weekly-reviews-note").textContent =
            `${reviews.length} topic reviews for ${payload.date_from} to ${payload.date_to}. ` +
            (payload.status === "insufficient_data"
              ? "Reported events are available; comparable coverage is insufficient to confirm attention trends."
              : "Reported events with source evidence; see the full report for attention metrics.");
          renderWeeklyPreviewList(document.getElementById("weekly-preview-reviews"), reviews, "", 8);
          document.getElementById("weekly-full-report").href =
            "/weekly-ai-analytics?date=" + encodeURIComponent(payload.report_date) + "#weekly-reviews-panel";
        }
        renderWeeklyPreviewList(weeklyNew, payload.new, payload.section_status?.new?.message
          || "No confirmed new topics in the observed 28-day history.");
        renderWeeklyPreviewList(weeklyTrendingUp, payload.trending_up, payload.section_status?.trending_up?.message
          || "No topics met the growth threshold this week.");
        renderWeeklyPreviewList(weeklyTrendingDown, payload.trending_down, payload.section_status?.trending_down?.message
          || "No topics met the decline threshold this week.");
      }

      async function loadDailyLinks(selectedDate) {
        dailyLinkList.innerHTML = "";
        emptyText.textContent = "No digest has been published for this date yet.";
        const response = await fetch("/api/news/links?date=" + encodeURIComponent(selectedDate) + "&limit=20");
        if (!response.ok) {
          return;
        }
        const items = await response.json();
        if (!items.length) {
          return;
        }
        emptyText.textContent =
          items.length + " articles are available for this date, but the daily digest has not been published yet.";
        dailyLinkList.innerHTML = items
          .map(
            (item) => `
              <li>
                <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
              </li>
            `,
          )
          .join("");
      }

      async function loadDigest(selectedDate) {
        const response = await fetch("/api/news/digests?date=" + encodeURIComponent(selectedDate));
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        const nextUrl = selectedDate ? "?date=" + encodeURIComponent(selectedDate) : "/";
        window.history.replaceState({}, "", nextUrl);
        updateHeroTitle(selectedDate);
        renderDigest(payload);
        await loadWeeklyPreview(selectedDate);
      }

      if (window.location.search !== initialDigestUrl) {
        window.history.replaceState({}, "", initialDigestUrl);
      }
      updateHeroTitle(dateInput.value);
      void loadCollectionStatus();
      setInterval(loadCollectionStatus, 15000);
      void loadWeeklyPreview(dateInput.value);
      if (!emptyState.classList.contains("hidden")) {
        void loadDailyLinks(dateInput.value);
      }

      dateInput.addEventListener("change", async () => {
        const selected = dateInput.value;
        // Signals load on their own, also when the digest request fails.
        void loadSignals(selected);
        await loadDigest(selected);
      });
