      function currentOnboardingBatchId() {
        const batchId = Number($("onboarding-batch-id").value);
        return Number.isInteger(batchId) && batchId > 0 ? batchId : null;
      }

      function currentOnboardingFilters() {
        return {
          batch_id: currentOnboardingBatchId(),
          status: $("onboarding-filter-status").value,
          validation_status: $("onboarding-filter-validation").value,
        };
      }

      function renderOnboardingSummary(summary) {
        $("onboarding-summary-batch").textContent = summary.batch_id ?? "-";
        $("onboarding-summary-parsed").textContent = summary.parsed_count ?? "-";
        $("onboarding-summary-accepted").textContent = summary.accepted_count ?? "-";
        $("onboarding-summary-rejected").textContent = summary.rejected_count ?? "-";
        $("onboarding-summary-pending").textContent = summary.pending_review_count ?? "-";
        $("onboarding-summary-validated").textContent = summary.validated_count ?? "-";
        $("onboarding-summary-approved").textContent = summary.approved_count ?? "-";
        $("onboarding-summary-duplicates").textContent = summary.duplicate_count ?? "-";
      }

      async function loadOnboardingSummary() {
        const batchId = currentOnboardingBatchId();
        if (!batchId) return;
        try {
          const response = await fetch(`/api/source-onboarding/batches/${batchId}/summary`);
          if (!response.ok) {
            setStatus("onboarding-status", "Failed to load batch summary.", "error");
            return;
          }
          renderOnboardingSummary(await response.json());
        } catch (_error) {
          setStatus("onboarding-status", "Failed to load batch summary.", "error");
        }
      }

      async function importOnboardingBatch() {
        if (sourceCheckRunning) {
          setStatus("onboarding-import-status", "Wait for the current source checks to finish.", "error");
          return;
        }
        const rawText = $("onboarding-import-raw-text").value.trim();
        if (!rawText) {
          setStatus("onboarding-import-status", "Paste at least one URL to import.", "error");
          return;
        }

        setStatus("onboarding-import-status", "Importing candidate batch...");
        try {
          const response = await fetch("/api/source-onboarding/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ raw_text: rawText }),
          });
          if (!response.ok) {
            let detail = "Failed to import candidate batch.";
            try {
              const body = await response.json();
              if (typeof body.detail === "string") {
                detail = body.detail;
              }
            } catch (_ignored) {}
            setStatus("onboarding-import-status", detail, "error");
            return;
          }

          const payload = await response.json();
          $("onboarding-batch-id").value = String(payload.batch_id);
          setStatus(
            "onboarding-import-status",
            `Batch ${payload.batch_id}: ${payload.accepted_count} new sources, ${payload.rejected_count} already known or invalid.`,
            "success",
          );
          setStatus("onboarding-status", `Loaded imported batch ${payload.batch_id}.`, "success");
          await loadOnboardingSummary();
          await loadOnboardingCandidates();
          if (payload.accepted_count > 0) {
            await validateOnboardingBatch();
            $("source-check-results").scrollIntoView({ behavior: "smooth", block: "start" });
          } else {
            setStatus("onboarding-status", "No new sources to check. Earlier candidate results are preserved; select their batch to review them.");
          }
        } catch (_error) {
          setStatus("onboarding-import-status", "Failed to import candidate batch.", "error");
        }
      }

      async function validateOnboardingBatch() {
        const batchId = currentOnboardingBatchId();
        if (!batchId) {
          setStatus("onboarding-status", "Import sources or select a batch first.", "error");
          return;
        }
        setStatus("onboarding-status", `Starting checks for batch ${batchId}...`);
        try {
          const response = await fetch(`/api/source-onboarding/batches/${batchId}/check`, {
            method: "POST",
          });
          if (!response.ok) {
            let detail = "Failed to validate batch.";
            try {
              const body = await response.json();
              if (typeof body.detail === "string") {
                detail = body.detail;
              }
            } catch (_ignored) {}
            setStatus("onboarding-status", detail, "error");
            return;
          }

          sourceCheckCompleted = -1;
          await refreshSourceCheck();
        } catch (_error) {
          setStatus("onboarding-status", "Failed to validate batch.", "error");
        }
      }

      async function refreshSourceCheck() {
        try {
          const response = await fetch("/api/source-onboarding/check-status");
          if (!response.ok) throw new Error("Unable to read check progress");
          const job = await response.json();
          const running = job.status === "running";
          sourceCheckRunning = running;
          $("import-onboarding-batch").disabled = running;
          $("validate-onboarding-batch").disabled = running;
          if (running) $("approve-ready-sources").disabled = true;
          if (job.batch_id) {
            setStatus("onboarding-check-status",
              `Batch ${job.batch_id}: ${job.completed || 0}/${job.total || 0} checked. ${job.status}`,
              job.status === "failed" ? "error" : "");
            if (job.error) setStatus("onboarding-status", job.error, "error");
          }
          if (job.batch_id === currentOnboardingBatchId() &&
              (job.completed !== sourceCheckCompleted || !running)) {
            sourceCheckCompleted = job.completed;
            await loadOnboardingSummary();
            await loadOnboardingCandidates();
            if (running) $("approve-ready-sources").disabled = true;
          }
          if (running && !sourceCheckTimer) {
            sourceCheckTimer = setInterval(refreshSourceCheck, 3000);
          } else if (!running && sourceCheckTimer) {
            clearInterval(sourceCheckTimer);
            sourceCheckTimer = null;
          }
          if (job.status === "finished") {
            setStatus("onboarding-status", "Checks complete. Review results and connect recommended sources.", "success");
          }
        } catch (error) {
          setStatus("onboarding-check-status", error.message, "error");
        }
      }

      async function connectRecommendedSources() {
        const batchId = currentOnboardingBatchId();
        if (!batchId) return;
        $("approve-ready-sources").disabled = true;
        try {
          const payload = await sendOnboardingAction(`/api/source-onboarding/batches/${batchId}/approve-ready`);
          setStatus("onboarding-status", `Connected ${payload.approved_count} sources. Use Update > Run update to collect news.`, "success");
          await loadOnboardingSummary();
          await loadOnboardingCandidates();
        } catch (error) {
          setStatus("onboarding-status", error.message, "error");
          await loadOnboardingCandidates();
        }
      }

      async function loadLatestSourceBatch() {
        try {
          const response = await fetch("/api/source-onboarding/latest");
          if (!response.ok) throw new Error("Unable to load the latest source batch");
          const payload = await response.json();
          if (payload.batch_id) {
            $("onboarding-batch-id").value = String(payload.batch_id);
            await loadOnboardingSummary();
            await loadOnboardingCandidates();
          } else {
            setStatus("onboarding-status", "Upload your first source JSON to get started.");
          }
          await refreshSourceCheck();
        } catch (error) {
          setStatus("onboarding-status", error.message, "error");
        }
      }

      function buildOnboardingActionButton(label, handler) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary";
        button.style.marginRight = "6px";
        button.style.marginBottom = "6px";
        button.textContent = label;
        button.addEventListener("click", handler);
        return button;
      }

      async function sendOnboardingAction(path, payload) {
        const response = await fetch(path, {
          method: payload ? "POST" : "POST",
          headers: { "Content-Type": "application/json" },
          body: payload ? JSON.stringify(payload) : null,
        });
        if (!response.ok) {
          let detail = "Review action failed.";
          try {
            const body = await response.json();
            if (typeof body.detail === "string") {
              detail = body.detail;
            }
          } catch (_ignored) {}
          throw new Error(detail);
        }
        return response.json();
      }

      async function updateOnboardingCandidate(candidateId, payload) {
        const response = await fetch(`/api/source-onboarding/candidates/${candidateId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let detail = "Edit failed.";
          try {
            const body = await response.json();
            if (typeof body.detail === "string") {
              detail = body.detail;
            }
          } catch (_ignored) {}
          throw new Error(detail);
        }
        return response.json();
      }

      async function loadOnboardingCandidates() {
        const tbody = document.querySelector("#onboarding-table tbody");
        tbody.innerHTML = "";
        $("onboarding-empty").classList.add("hidden");
        const filters = currentOnboardingFilters();
        if (!filters.batch_id) return;
        const params = new URLSearchParams({ batch_id: String(filters.batch_id) });
        if (filters.status) params.set("status", filters.status);
        if (filters.validation_status) params.set("validation_status", filters.validation_status);

        try {
          const response = await fetch(`/api/source-onboarding/candidates?${params.toString()}`);
          if (!response.ok) {
            setStatus("onboarding-status", "Failed to load onboarding candidates.", "error");
            return;
          }
          const payload = await response.json();
          renderOnboardingSummary(payload.summary || {});
          const items = Array.isArray(payload.items) ? payload.items : [];
          let readyCount = 0;
          for (const item of items) {
            try {
              const review = JSON.parse(item.validation_details || "{}").source_review;
              if (item.status === "draft" && item.validation_status === "validated" && review?.decision === "ready") readyCount++;
            } catch (_ignored) {}
          }
          $("approve-ready-sources").textContent = `Connect recommended (${readyCount})`;
          $("approve-ready-sources").disabled = readyCount === 0 || sourceCheckRunning;
          if (items.length === 0) {
            $("onboarding-empty").classList.remove("hidden");
            return;
          }
          for (const item of items) {
            const row = document.createElement("tr");

            const idCell = document.createElement("td");
            idCell.textContent = String(item.candidate_id);
            row.appendChild(idCell);

            const statusCell = document.createElement("td");
            const statusPill = document.createElement("span");
            statusPill.className = "pill";
            statusPill.textContent = item.status;
            statusCell.appendChild(statusPill);
            row.appendChild(statusCell);

            const validationCell = document.createElement("td");
            let sourceReview = {};
            try {
              sourceReview = JSON.parse(item.validation_details || "{}").source_review || {};
            } catch (_ignored) {}
            const decisionNames = {ready: "Ready to connect", review: "Needs review", reject: "Not suitable", duplicate: "Already known"};
            validationCell.textContent = decisionNames[sourceReview.decision] || item.validation_status;
            if (sourceReview.reason) {
              const reason = document.createElement("div");
              reason.className = "note";
              reason.textContent = sourceReview.reason;
              validationCell.appendChild(reason);
            }
            if (item.validated_at) {
              const validationMeta = document.createElement("div");
              validationMeta.className = "note";
              validationMeta.textContent = item.validated_at;
              validationCell.appendChild(validationMeta);
            }
            row.appendChild(validationCell);

            const typeCell = document.createElement("td");
            const typeValue = item.validation_detected_type || item.candidate_type;
            typeCell.textContent = typeValue;
            if (item.validation_error) {
              const errorMeta = document.createElement("div");
              errorMeta.className = "note";
              errorMeta.textContent = item.validation_error;
              typeCell.appendChild(errorMeta);
            } else if (item.validation_details) {
              const detailsMeta = document.createElement("div");
              detailsMeta.className = "note";
              detailsMeta.textContent = item.validation_details;
              typeCell.appendChild(detailsMeta);
            }
            row.appendChild(typeCell);

            const urlCell = document.createElement("td");
            const urlLink = document.createElement("a");
            urlLink.textContent = item.normalized_url;
            urlLink.target = "_blank";
            urlLink.rel = "noopener noreferrer";
            try {
              urlLink.href = new URL(item.normalized_url).toString();
            } catch (_ignored) {
              urlLink.removeAttribute("href");
            }
            urlCell.appendChild(urlLink);
            if (item.review_note) {
              const noteMeta = document.createElement("div");
              noteMeta.className = "note";
              noteMeta.textContent = item.review_note;
              urlCell.appendChild(noteMeta);
            }
            if (item.approved_source_id) {
              const sourceMeta = document.createElement("div");
              sourceMeta.className = "note";
              sourceMeta.textContent = `Active source #${item.approved_source_id}`;
              urlCell.appendChild(sourceMeta);
            }
            row.appendChild(urlCell);

            const actionsCell = document.createElement("td");
            actionsCell.className = "action-group";
            const urlInput = document.createElement("input");
            urlInput.className = "mini-input";
            urlInput.value = item.normalized_url;
            urlInput.placeholder = "Canonical URL";

            const typeInput = document.createElement("select");
            typeInput.className = "mini-select";
            for (const optionValue of ["rss", "html", "unknown"]) {
              const option = document.createElement("option");
              option.value = optionValue;
              option.textContent = optionValue.toUpperCase();
              option.selected = optionValue === item.candidate_type;
              typeInput.appendChild(option);
            }

            const duplicateInput = document.createElement("input");
            duplicateInput.className = "mini-input";
            duplicateInput.type = "number";
            duplicateInput.min = "1";
            duplicateInput.value = item.duplicate_of_candidate_id || "";
            duplicateInput.placeholder = "Duplicate of candidate ID";

            const approveButton = buildOnboardingActionButton("Approve", async () => {
              try {
                await sendOnboardingAction(`/api/source-onboarding/candidates/${item.candidate_id}/approve`);
                setStatus("onboarding-status", `Candidate ${item.candidate_id} approved.`, "success");
                await loadOnboardingCandidates();
              } catch (error) {
                setStatus("onboarding-status", error.message, "error");
              }
            });
            approveButton.disabled = item.validation_status !== "validated" || item.status === "approved" || item.status === "duplicate";
            actionsCell.appendChild(approveButton);
            if (item.approved_source_id) {
              actionsCell.appendChild(buildOnboardingActionButton("Disable", async () => {
                try {
                  await sendOnboardingAction(`/api/source-onboarding/candidates/${item.candidate_id}/disable`);
                  setStatus("onboarding-status", `Candidate ${item.candidate_id} disabled.`, "success");
                  await loadOnboardingCandidates();
                } catch (error) {
                  setStatus("onboarding-status", error.message, "error");
                }
              }));
            }
            actionsCell.appendChild(buildOnboardingActionButton("Reject", async () => {
              try {
                await sendOnboardingAction(
                  `/api/source-onboarding/candidates/${item.candidate_id}/reject`,
                  { reason: $("onboarding-review-note").value.trim() || "Rejected from review UI" },
                );
                setStatus("onboarding-status", `Candidate ${item.candidate_id} rejected.`, "success");
                await loadOnboardingCandidates();
              } catch (error) {
                setStatus("onboarding-status", error.message, "error");
              }
            }));
            actionsCell.appendChild(buildOnboardingActionButton("Mark Duplicate", async () => {
              const duplicateId = Number(duplicateInput.value);
              if (!(duplicateId > 0)) {
                setStatus("onboarding-status", "Duplicate target ID is required.", "error");
                return;
              }
              try {
                await sendOnboardingAction(
                  `/api/source-onboarding/candidates/${item.candidate_id}/mark-duplicate`,
                  {
                    duplicate_of_candidate_id: duplicateId,
                    reason: $("onboarding-review-note").value.trim() || null,
                  },
                );
                setStatus("onboarding-status", `Candidate ${item.candidate_id} marked duplicate.`, "success");
                await loadOnboardingCandidates();
              } catch (error) {
                setStatus("onboarding-status", error.message, "error");
              }
            }));
            actionsCell.appendChild(buildOnboardingActionButton("Save Edit", async () => {
              try {
                await updateOnboardingCandidate(item.candidate_id, {
                  normalized_url: urlInput.value.trim(),
                  candidate_type: typeInput.value,
                  raw_input: urlInput.value.trim(),
                  review_note: $("onboarding-review-note").value.trim() || null,
                });
                setStatus("onboarding-status", `Candidate ${item.candidate_id} updated.`, "success");
                await loadOnboardingCandidates();
              } catch (error) {
                setStatus("onboarding-status", error.message, "error");
              }
            }));
            actionsCell.appendChild(urlInput);
            actionsCell.appendChild(typeInput);
            actionsCell.appendChild(duplicateInput);
            row.appendChild(actionsCell);

            tbody.appendChild(row);
          }
        } catch (_error) {
          setStatus("onboarding-status", "Failed to load onboarding candidates.", "error");
        }
      }

      $("save-settings").addEventListener("click", saveSettings);
      $("run-update").addEventListener("click", runUpdate);
      $("refresh-status").addEventListener("click", refreshStatus);
      $("load-news").addEventListener("click", loadNews);
      $("copy-links").addEventListener("click", copyVisibleLinks);
      $("import-onboarding-batch").addEventListener("click", importOnboardingBatch);
      $("approve-ready-sources").addEventListener("click", connectRecommendedSources);
      $("onboarding-json-file").addEventListener("change", async (event) => {
        const file = event.target.files[0];
        if (!file) return;
        if (file.size > 1000000) {
          setStatus("onboarding-import-status", "JSON file must be smaller than 1 MB.", "error");
          return;
        }
        try {
          const text = await file.text();
          JSON.parse(text);
          $("onboarding-import-raw-text").value = text;
          await importOnboardingBatch();
        } catch (_error) {
          setStatus("onboarding-import-status", "Choose a valid JSON file.", "error");
        }
      });
      $("load-onboarding").addEventListener("click", loadOnboardingCandidates);
      $("validate-onboarding-batch").addEventListener("click", validateOnboardingBatch);
      $("load-onboarding-summary").addEventListener("click", loadOnboardingSummary);

      loadSettings();
      refreshStatus();
      loadNews();
      loadLatestSourceBatch();
