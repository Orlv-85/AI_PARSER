      const $ = (id) => document.getElementById(id);
      const updateBtn = $("btn-update");
      const viewBtn = $("btn-view");
      const onboardingBtn = $("btn-onboarding");
      const pageUpdate = $("page-update");
      const pageView = $("page-view");
      const pageOnboarding = $("page-onboarding");
      let pollTimer = null;
      let pollInterval = null;
      let sourceCheckTimer = null;
      let sourceCheckCompleted = -1;
      let sourceCheckRunning = false;
      let visibleNewsItems = [];

      function setStatus(id, text, level = "") {
        const el = $(id);
        el.textContent = text;
        el.classList.remove("error", "success");
        if (level) {
          el.classList.add(level);
        }
      }

      function showPage(name) {
        const update = name === "update";
        const view = name === "view";
        const onboarding = name === "onboarding";
        pageUpdate.classList.toggle("hidden", !update);
        pageView.classList.toggle("hidden", !view);
        pageOnboarding.classList.toggle("hidden", !onboarding);
        updateBtn.classList.toggle("active", update);
        viewBtn.classList.toggle("active", view);
        onboardingBtn.classList.toggle("active", onboarding);
      }

      updateBtn.addEventListener("click", () => showPage("update"));
      viewBtn.addEventListener("click", () => showPage("view"));
      onboardingBtn.addEventListener("click", () => showPage("onboarding"));

