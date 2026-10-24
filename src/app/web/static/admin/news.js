      async function loadNews() {
        const hours = Number($("hours").value);
        const limit = Number($("limit").value);
        const query = $("query").value.trim();
        const days = Number($("days").value);
        const sort = $("sort").value;
        const dateFrom = $("date_from").value.trim();
        const dateTo = $("date_to").value.trim();
        const params = new URLSearchParams({ limit: String(limit), days: String(days), sort });
        if (dateFrom || dateTo) {
          if (dateFrom) params.set("date_from", dateFrom);
          if (dateTo) params.set("date_to", dateTo);
        } else {
          params.set("hours", String(hours));
        }
        if (query) params.set("query", query);
        const category = $("category").value;
        if (category) params.set("category", category);

        setStatus("news-status", "");
        $("news-empty").classList.add("hidden");
        const tbody = document.querySelector("#news-table tbody");
        tbody.innerHTML = "";
        visibleNewsItems = [];
        try {
          const response = await fetch(`/api/news?${params.toString()}`);
          if (!response.ok) {
            let detail = "Failed to load news.";
            try {
              const body = await response.json();
              if (typeof body.detail === "string") detail = body.detail;
            } catch (_ignored) {}
            setStatus("news-status", detail, "error");
            return;
          }
          const items = await response.json();
          visibleNewsItems = Array.isArray(items) ? items : [];
          if (items.length === 0) {
            $("news-empty").classList.remove("hidden");
            return;
          }
          for (const item of items) {
            const row = document.createElement("tr");
            const sourceLabel = item.source_name || item.source_key || (item.source_id !== null ? `#${item.source_id}` : "n/a");

            const publishedCell = document.createElement("td");
            publishedCell.textContent = item.published_at || item.publication_day ||
              item.publication_literal || "Unknown";
            row.appendChild(publishedCell);

            const rankCell = document.createElement("td");
            rankCell.textContent = Number(item.rank_score).toFixed(3);
            row.appendChild(rankCell);

            const sourceCell = document.createElement("td");
            sourceCell.textContent = sourceLabel;
            row.appendChild(sourceCell);

            const categoryCell = document.createElement("td");
            categoryCell.textContent = (item.category || "Uncategorized") +
              (item.material_type ? " / " + item.material_type : "");
            row.appendChild(categoryCell);

            const titleCell = document.createElement("td");
            titleCell.textContent = item.title;
            row.appendChild(titleCell);

            const urlCell = document.createElement("td");
            const link = document.createElement("a");
            link.textContent = "link";
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            try {
              link.href = new URL(item.url_canonical, window.location.origin).toString();
            } catch (_ignored) {
              link.removeAttribute("href");
            }
            urlCell.appendChild(link);
            row.appendChild(urlCell);

            tbody.appendChild(row);
          }
        } catch (_error) {
          setStatus(
            "news-status",
            "Unable to load news due to a network error. Please retry.",
            "error",
          );
        }
      }

      async function copyVisibleLinks() {
        const urls = visibleNewsItems
          .map((item) => item && item.url_canonical)
          .filter((url) => typeof url === "string" && url.length > 0);
        if (urls.length === 0) {
          setStatus("news-status", "No visible links to copy.", "error");
          return;
        }
        const text = urls.join("\n");
        if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
          setStatus("news-status", "Clipboard API is unavailable in this browser.", "error");
          return;
        }
        try {
          await navigator.clipboard.writeText(text);
          setStatus("news-status", `Copied ${urls.length} visible links to clipboard.`, "success");
        } catch (_error) {
          setStatus("news-status", "Failed to copy visible links to clipboard.", "error");
        }
      }

