      function clearSettingErrors() {
        for (const field of [
          "request_timeout_seconds",
          "max_retries",
          "per_source_min_interval_seconds",
          "concurrency_limit",
          "fetch_http_max_connections",
          "fetch_http_max_keepalive_connections",
          "rss_known_streak_stop",
          "html_known_streak_stop",
          "html_max_links_per_source",
          "article_batch_upsert_enabled",
          "fetch_emit_source_metrics",
        ]) {
          $(`err-${field}`).textContent = "";
        }
      }

      function validateSettings(payload) {
        const errors = {};
        if (!(payload.request_timeout_seconds > 0 && payload.request_timeout_seconds <= 120)) {
          errors.request_timeout_seconds = "Must be > 0 and <= 120";
        }
        if (!(payload.max_retries >= 0 && payload.max_retries <= 10)) {
          errors.max_retries = "Must be between 0 and 10";
        }
        if (!(payload.per_source_min_interval_seconds >= 0 && payload.per_source_min_interval_seconds <= 60)) {
          errors.per_source_min_interval_seconds = "Must be between 0 and 60";
        }
        if (!(payload.concurrency_limit >= 1 && payload.concurrency_limit <= 64)) {
          errors.concurrency_limit = "Must be between 1 and 64";
        }
        if (!(payload.fetch_http_max_connections >= 1 && payload.fetch_http_max_connections <= 256)) {
          errors.fetch_http_max_connections = "Must be between 1 and 256";
        }
        if (!(payload.fetch_http_max_keepalive_connections >= 0 && payload.fetch_http_max_keepalive_connections <= 256)) {
          errors.fetch_http_max_keepalive_connections = "Must be between 0 and 256";
        }
        if (!(payload.rss_known_streak_stop >= 0 && payload.rss_known_streak_stop <= 500)) {
          errors.rss_known_streak_stop = "Must be between 0 and 500";
        }
        if (!(payload.html_known_streak_stop >= 0 && payload.html_known_streak_stop <= 500)) {
          errors.html_known_streak_stop = "Must be between 0 and 500";
        }
        if (!(payload.html_max_links_per_source >= 1 && payload.html_max_links_per_source <= 500)) {
          errors.html_max_links_per_source = "Must be between 1 and 500";
        }
        return errors;
      }

      async function loadSettings() {
        setStatus("settings-status", "");
        try {
          const response = await fetch("/api/update/settings");
          const settings = await response.json();
          $("request_timeout_seconds").value = settings.request_timeout_seconds;
          $("max_retries").value = settings.max_retries;
          $("per_source_min_interval_seconds").value = settings.per_source_min_interval_seconds;
          $("concurrency_limit").value = settings.concurrency_limit;
          $("fetch_http_max_connections").value = settings.fetch_http_max_connections;
          $("fetch_http_max_keepalive_connections").value = settings.fetch_http_max_keepalive_connections;
          $("rss_known_streak_stop").value = settings.rss_known_streak_stop;
          $("html_known_streak_stop").value = settings.html_known_streak_stop;
          $("html_max_links_per_source").value = settings.html_max_links_per_source;
          $("article_batch_upsert_enabled").checked = settings.article_batch_upsert_enabled;
          $("fetch_emit_source_metrics").checked = settings.fetch_emit_source_metrics;
        } catch (error) {
          setStatus("settings-status", `Failed to load settings: ${error}`, "error");
        }
      }

      async function saveSettings() {
        clearSettingErrors();
        const payload = {
          request_timeout_seconds: Number($("request_timeout_seconds").value),
          max_retries: Number($("max_retries").value),
          per_source_min_interval_seconds: Number($("per_source_min_interval_seconds").value),
          concurrency_limit: Number($("concurrency_limit").value),
          fetch_http_max_connections: Number($("fetch_http_max_connections").value),
          fetch_http_max_keepalive_connections: Number($("fetch_http_max_keepalive_connections").value),
          rss_known_streak_stop: Number($("rss_known_streak_stop").value),
          html_known_streak_stop: Number($("html_known_streak_stop").value),
          html_max_links_per_source: Number($("html_max_links_per_source").value),
          article_batch_upsert_enabled: $("article_batch_upsert_enabled").checked,
          fetch_emit_source_metrics: $("fetch_emit_source_metrics").checked,
        };
        const localErrors = validateSettings(payload);
        if (Object.keys(localErrors).length > 0) {
          for (const [field, message] of Object.entries(localErrors)) {
            $(`err-${field}`).textContent = message;
          }
          setStatus("settings-status", "Validation failed. Fix highlighted fields.", "error");
          return;
        }
        const response = await fetch("/api/update/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let detail = "Failed to save settings";
          try {
            const errorBody = await response.json();
            if (Array.isArray(errorBody.detail)) {
              for (const item of errorBody.detail) {
                const field = item.loc[item.loc.length - 1];
                if ($(`err-${field}`)) {
                  $(`err-${field}`).textContent = item.msg;
                }
              }
              detail = "Validation failed. Fix highlighted fields.";
            } else if (typeof errorBody.detail === "string") {
              detail = errorBody.detail;
            }
          } catch (_ignored) {}
          setStatus("settings-status", detail, "error");
          return;
        }
        setStatus("settings-status", "Settings saved.", "success");
      }

      async function runUpdate() {
        const response = await fetch("/api/update/run", { method: "POST" });
        if (response.status === 409) {
          setStatus("run-error", "Update is already running.", "error");
          return;
        }
        if (!response.ok) {
          setStatus("run-error", "Failed to start update.", "error");
          return;
        }
        await refreshStatus();
      }

      let activeScreeningMessage = "";

      function renderRunStatus(status) {
        $("run-id").textContent = status.run_id || "-";
        $("run-started").textContent = status.started_at || "-";
        $("run-finished").textContent = status.finished_at || "-";
        $("run-sources").textContent = status.source_count ?? 0;
        $("run-fetched").textContent = status.fetched;
        $("run-new").textContent = status.new;
        $("run-duplicates").textContent = status.duplicates;
        $("run-errors").textContent = status.errors;
        const line = `Status: ${status.status}`;
        if (status.screening_paused) {
          activeScreeningMessage = status.screening_message || "";
          setStatus("run-error", activeScreeningMessage, "error");
          setStatus("run-status", line, "error");
        } else {
          if (activeScreeningMessage) {
            setStatus("run-error", "", "");
            activeScreeningMessage = "";
          }
          if (status.status === "failed" && status.error_message) {
            setStatus("run-status", `${line}; ${status.error_message}`, "error");
          } else {
            setStatus("run-status", line, status.status === "finished" ? "success" : "");
          }
        }
      }

      function syncPolling(status) {
        const interval = status === "running" ? 1500 : 15000;
        if (pollInterval !== interval) {
          if (pollTimer !== null) clearInterval(pollTimer);
          pollInterval = interval;
          pollTimer = setInterval(refreshStatus, interval);
        }
      }

      async function refreshStatus() {
        try {
          const response = await fetch("/api/update/status");
          if (!response.ok) {
            setStatus("run-error", "Unable to read update status.", "error");
            return;
          }
          const status = await response.json();
          renderRunStatus(status);
          syncPolling(status.status);
        } catch (error) {
          setStatus("run-error", `Unable to read update status: ${error}`, "error");
        }
      }

