      const form = document.getElementById("stats-form");
      const dateFrom = document.getElementById("date-from");
      const dateTo = document.getElementById("date-to");
      const summary = document.getElementById("summary");
      const chart = document.getElementById("chart");
      const emptyChart = document.getElementById("empty-chart");
      const table = document.getElementById("stats-table");

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }

      function sum(items, key) {
        return items.reduce((total, item) => total + Number(item[key] || 0), 0);
      }

      function renderSummary(items) {
        const zeroDays = items.filter((item) => item.published_count === 0).length;
        const metrics = [
          ["Published", sum(items, "published_count")],
          ["Discovered", sum(items, "discovered_count")],
          ["Fetch New", sum(items, "new_count")],
          ["Zero Days", zeroDays],
        ];
        summary.innerHTML = metrics
          .map(
            ([label, value]) => `
              <div class="metric">
                <span class="muted">${escapeHtml(label)}</span>
                <span class="metric-value">${escapeHtml(value)}</span>
              </div>
            `,
          )
          .join("");
      }

      function renderChart(items) {
        const maxPublished = Math.max(...items.map((item) => item.published_count), 0);
        if (!items.length) {
          chart.innerHTML = "";
          emptyChart.classList.remove("hidden");
          return;
        }
        emptyChart.classList.add("hidden");
        chart.innerHTML = items
          .map((item) => {
            const width = maxPublished > 0 ? Math.round((item.published_count / maxPublished) * 100) : 0;
            const zeroClass = item.published_count === 0 ? " zero" : "";
            return `
              <div class="bar-row">
                <span class="muted">${escapeHtml(item.stat_date)}</span>
                <div class="bar-track">
                  <div class="bar${zeroClass}" style="width: ${width}%"></div>
                </div>
                <span class="count">${escapeHtml(item.published_count)}</span>
              </div>
            `;
          })
          .join("");
      }

      function renderTable(items) {
        table.innerHTML = items
          .map(
            (item) => `
              <tr class="${item.published_count === 0 ? "zero-day" : ""}">
                <td>${escapeHtml(item.stat_date)}</td>
                <td>${escapeHtml(item.published_count)}</td>
                <td>${escapeHtml(item.discovered_count)}</td>
                <td>${escapeHtml(item.fetch_run_count)}</td>
                <td>${escapeHtml(item.fetched_count)}</td>
                <td>${escapeHtml(item.new_count)}</td>
                <td>${escapeHtml(item.duplicate_count)}</td>
                <td>${escapeHtml(item.error_count)}</td>
              </tr>
            `,
          )
          .join("");
      }

      async function loadStats() {
        const params = new URLSearchParams({
          date_from: dateFrom.value,
          date_to: dateTo.value,
        });
        const response = await fetch("/api/news/stats/daily?" + params.toString());
        if (!response.ok) {
          summary.innerHTML = '<p class="muted">Stats are unavailable right now.</p>';
          chart.innerHTML = "";
          table.innerHTML = "";
          return;
        }
        const payload = await response.json();
        const items = payload.items || [];
        window.history.replaceState({}, "", "/news-stats?" + params.toString());
        renderSummary(items);
        renderChart(items);
        renderTable(items);
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await loadStats();
      });

      void loadStats();
