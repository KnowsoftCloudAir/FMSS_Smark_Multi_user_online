/**
 * Knowsoft FMSS — Reliability layer
 * - Makes every nav button open the correct view and load data
 * - Friendly API / JS error handling
 * - Demo data load / clear controls
 * - Never leaves the user on a blank or broken screen
 */
(function () {
  const API = window.API || "";

  // ---------- Toast / notice ----------
  function ensureToast() {
    let t = document.getElementById("ks-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "ks-toast";
      t.style.cssText =
        "position:fixed;bottom:24px;right:24px;z-index:99999;max-width:360px;padding:14px 18px;" +
        "border-radius:10px;background:#1a2332;color:#fff;font-size:14px;box-shadow:0 8px 24px rgba(0,0,0,.35);" +
        "display:none;line-height:1.4;";
      document.body.appendChild(t);
    }
    return t;
  }
  window.ksToast = function (msg, isErr) {
    const t = ensureToast();
    t.textContent = msg;
    t.style.background = isErr ? "#8b1e1e" : "#1a2332";
    t.style.display = "block";
    clearTimeout(t._hide);
    t._hide = setTimeout(() => (t.style.display = "none"), 4500);
  };

  // ---------- Knowsoft error panel (in-app, not browser default) ----------
  function ensureErrorPanel() {
    let p = document.getElementById("ks-error-panel");
    if (!p) {
      p = document.createElement("div");
      p.id = "ks-error-panel";
      p.style.cssText =
        "display:none;position:fixed;inset:0;z-index:100000;background:rgba(8,12,20,.92);" +
        "align-items:center;justify-content:center;padding:24px;";
      p.innerHTML = `
        <div style="background:#0f1724;border:1px solid #1e3a5f;border-radius:16px;padding:32px;max-width:440px;width:100%;text-align:center;color:#e8eef7;">
          <div style="font-size:40px;margin-bottom:8px;">🛡️</div>
          <h2 style="margin:0 0 8px;font-size:22px;color:#5eb3ff;">Knowsoft FMSS</h2>
          <p id="ks-error-msg" style="margin:0 0 20px;color:#9bb0c9;font-size:15px;"></p>
          <button type="button" id="ks-error-back" class="btn btn-accent"
            style="padding:12px 28px;border:none;border-radius:8px;background:#00b4d8;color:#041018;font-weight:600;cursor:pointer;">
            ← Back to app
          </button>
        </div>`;
      document.body.appendChild(p);
      p.querySelector("#ks-error-back").onclick = () => {
        p.style.display = "none";
        try {
          if (typeof showView === "function") showView("dashboard");
        } catch (_) {}
      };
    }
    return p;
  }
  window.ksShowError = function (message) {
    const p = ensureErrorPanel();
    p.querySelector("#ks-error-msg").textContent =
      message || "Something went wrong. You can go back and continue working.";
    p.style.display = "flex";
  };

  // Global unhandled errors → Knowsoft panel, not blank page
  window.addEventListener("error", (e) => {
    console.error(e.error || e.message);
    // Don't block UI for every minor script error
  });
  window.addEventListener("unhandledrejection", (e) => {
    console.error("Unhandled:", e.reason);
    const msg = (e.reason && e.reason.message) || String(e.reason || "");
    if (msg && !/Session expired/i.test(msg)) {
      window.ksToast(msg, true);
    }
  });

  // ---------- Safer API wrapper (preserves existing api if present) ----------
  const _api = window.api;
  if (typeof _api === "function") {
    window.api = async function (path, options) {
      try {
        return await _api(path, options);
      } catch (ex) {
        const msg = ex.message || "Request failed";
        if (/Session expired/i.test(msg)) throw ex;
        window.ksToast(msg, true);
        throw ex;
      }
    };
  }

  // ---------- showView: load data for every module ----------
  const loaders = {
    dashboard: () => {
      if (typeof loadDashboardCharts === "function") loadDashboardCharts();
      if (typeof loadDashboardStats === "function") loadDashboardStats();
    },
    finance: () => {
      if (typeof loadFinanceHub === "function") loadFinanceHub();
      else if (typeof loadPayments === "function") loadPayments();
    },
    "finance-setup": () => {
      if (typeof loadFinanceSetup === "function") loadFinanceSetup();
    },
    payments: () => {
      if (typeof loadPaymentFormData === "function") loadPaymentFormData();
      if (typeof loadPayments === "function") loadPayments();
    },
    "assets-reg": () => {
      if (typeof loadAssets === "function") loadAssets();
      if (typeof loadAssetDashboard === "function") loadAssetDashboard();
    },
    assets: () => {
      if (typeof showView === "function") {
        /* redirect handled below */
      }
      if (typeof loadAssets === "function") loadAssets();
    },
    "inventory-full": () => {
      if (typeof loadInventory === "function") loadInventory();
    },
    inventory: () => {
      if (typeof loadInventory === "function") loadInventory();
    },
    "vendors-full": () => {
      if (typeof loadVendors === "function") loadVendors();
    },
    vendors: () => {
      if (typeof loadVendors === "function") loadVendors();
    },
    procurement: () => {
      if (typeof loadProcurement === "function") loadProcurement();
      if (typeof loadRfqs === "function") loadRfqs();
    },
    reports: () => {
      if (typeof loadReports === "function") loadReports();
    },
    "bank-recon": () => {
      if (typeof loadBankRecon === "function") loadBankRecon();
    },
    corrections: () => {
      if (typeof loadCorrectionsInbox === "function") loadCorrectionsInbox();
    },
    users: () => {
      if (typeof loadUsers === "function") loadUsers();
    },
    settings: () => {
      if (typeof loadCompanySettings === "function") loadCompanySettings();
    },
    security: () => {},
    currency: () => {
      if (typeof loadCurrencyBoard === "function") loadCurrencyBoard();
    },
    tasks: () => {
      if (typeof loadTasks === "function") loadTasks();
    },
    superadmin: () => {
      if (typeof loadRegisteredFirms === "function") loadRegisteredFirms();
      else if (typeof loadCompanies === "function") loadCompanies();
    },
    "project-analysis": () => {
      if (typeof loadProjectList === "function") loadProjectList();
    },
  };

  // Redirect aliases
  const aliases = {
    assets: "assets-reg",
    inventory: "inventory-full",
    vendors: "vendors-full",
  };

  function wireShowView() {
    const prev = window.showView;
    if (typeof prev !== "function") return;
    window.showView = function (name) {
      try {
        if (aliases[name]) name = aliases[name];
        prev(name);
        const fn = loaders[name];
        if (fn) {
          try {
            fn();
          } catch (e) {
            console.warn("loader", name, e);
            window.ksToast("Could not fully load " + name + ": " + (e.message || e), true);
          }
        }
        // Ensure the section is visible
        const el = document.getElementById("view-" + name);
        if (!el) {
          window.ksShowError(
            "This section is not available yet. Use Back to return to the dashboard."
          );
        }
      } catch (e) {
        console.error(e);
        window.ksShowError(e.message || "Could not open that screen.");
      }
    };
  }

  // ---------- Demo data: load & clear ----------
  window.loadDemoData = async function () {
    try {
      const data = await window.api("/api/demo/load", { method: "POST", body: "{}" });
      window.ksToast(data.message || "Demo data loaded");
      if (typeof showView === "function") showView("dashboard");
    } catch (e) {
      // fallback to superadmin reseed
      try {
        const data = await window.api("/api/superadmin/reseed-demo", {
          method: "POST",
          body: "{}",
        });
        window.ksToast(data.message || "Demo data reseeded");
      } catch (e2) {
        window.ksToast(e2.message || "Could not load demo data", true);
      }
    }
  };

  window.clearDemoData = async function () {
    if (!confirm("Remove all demo sample data for this company? Real records you created will stay."))
      return;
    try {
      const data = await window.api("/api/demo/clear", { method: "POST", body: "{}" });
      window.ksToast(data.message || "Demo data cleared");
      if (typeof showView === "function") showView("dashboard");
    } catch (e) {
      window.ksToast(e.message || "Could not clear demo data", true);
    }
  };

  // Expose reseed for General Admin button
  if (typeof window.reseedDemoData !== "function") {
    window.reseedDemoData = window.loadDemoData;
  }

  // ---------- Inject Demo Data controls into dashboard if missing ----------
  function injectDemoControls() {
    const dash = document.getElementById("view-dashboard");
    if (!dash || document.getElementById("ks-demo-controls")) return;
    const box = document.createElement("div");
    box.id = "ks-demo-controls";
    box.className = "card";
    box.style.marginTop = "16px";
    box.innerHTML = `
      <h3 style="margin-top:0;">Demo data</h3>
      <p class="hint" style="margin-bottom:12px;">
        Load sample COA, budgets, payments, inventory and procurement for training.
        Clear removes only sample (demo-flagged) records.
      </p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button type="button" class="btn btn-accent" id="ks-btn-load-demo">Load / Refresh demo data</button>
        <button type="button" class="btn btn-outline" id="ks-btn-clear-demo">Clear demo data</button>
      </div>`;
    dash.appendChild(box);
    document.getElementById("ks-btn-load-demo").onclick = () => window.loadDemoData();
    document.getElementById("ks-btn-clear-demo").onclick = () => window.clearDemoData();
  }

  // ---------- Fix data-perm: don't hide for roles that should see modules ----------
  function fixPermissionsChrome() {
    try {
      const u = window.currentUser || JSON.parse(localStorage.getItem("km_user") || "null");
      if (!u) return;
      const role = u.role || "";
      // Platform admin: only Firm Approvals
      if (["superadmin", "general_admin", "owner"].includes(role) && !u.company_id) {
        return;
      }
      // Company users: show modules unless explicitly false
      document.querySelectorAll("[data-perm]").forEach((el) => {
        const key = "can_access_" + el.dataset.perm;
        if (u[key] === false) el.style.display = "none";
        else el.style.display = "";
      });
      // Always show core ops for company_admin / finance / program
      if (["company_admin", "admin", "finance", "program"].includes(role)) {
        ["finance", "payments", "reports", "dashboard"].forEach((v) => {
          document.querySelectorAll('.nav-item[data-view="' + v + '"]').forEach((el) => {
            el.style.display = "flex";
          });
        });
      }
    } catch (_) {}
  }

  // ---------- Boot ----------
  function boot() {
    wireShowView();
    injectDemoControls();
    fixPermissionsChrome();
    // Re-apply after enterApp may have run
    setTimeout(injectDemoControls, 800);
    setTimeout(fixPermissionsChrome, 900);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Also run when app becomes visible
  const obs = new MutationObserver(() => {
    if (document.getElementById("app-page")?.classList.contains("active")) {
      injectDemoControls();
      fixPermissionsChrome();
    }
  });
  try {
    obs.observe(document.body, { attributes: true, subtree: true, attributeFilter: ["class"] });
  } catch (_) {}
})();
