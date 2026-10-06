/**
 * General Admin (Owner) console — approval & technical corrections only.
 * Drop-in fix for missing owner-form handlers + professional approval UI.
 * Include AFTER app.js:
 *   <script src="/frontend/general_admin.js"></script>
 * Or paste into app.js near the login handlers.
 */

(function () {
  const API = window.API || "";

  // ---------- Card switches ----------
  function showCard(which) {
    ["login-card", "register-card", "owner-card"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = id === which ? "block" : "none";
    });
  }

  document.getElementById("switch-to-owner")?.addEventListener("click", (e) => {
    e.preventDefault();
    showCard("owner-card");
  });

  document.getElementById("switch-owner-login")?.addEventListener("click", (e) => {
    e.preventDefault();
    showCard("login-card");
  });

  // Also support a top-nav "Owner console" if present
  document.getElementById("btn-show-owner")?.addEventListener("click", (e) => {
    e.preventDefault();
    showCard("owner-card");
  });

  // ---------- General Admin login ----------
  document.getElementById("owner-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("owner-error");
    const btn = e.target.querySelector('button[type="submit"]');
    if (err) {
      err.style.display = "none";
      err.textContent = "";
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Opening…";
    }

    const username = (document.getElementById("owner-username")?.value || "").trim();
    const password = document.getElementById("owner-password")?.value || "";

    try {
      // Prefer dedicated General Admin endpoint; fall back to standard login
      let data = null;
      let res = await fetch(API + "/api/general-admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        data = await res.json();
      } else {
        // Fallback: classic form login (username = general_admin or superadmin)
        const form = new URLSearchParams();
        form.append("username", username);
        form.append("password", password);
        res = await fetch(API + "/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: form,
        });
        data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = data.detail || data.message || "Login failed";
          throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
      }

      window.token = data.access_token;
      window.currentUser = data.user;
      localStorage.setItem("km_token", data.access_token);
      localStorage.setItem("km_user", JSON.stringify(data.user));

      if (typeof hideSplash === "function") hideSplash();
      if (typeof enterApp === "function") enterApp();
      else {
        document.getElementById("landing-page")?.classList.remove("active");
        document.getElementById("app-page")?.classList.add("active");
        document.getElementById("app-page").style.display = "flex";
      }

      // Force General Admin chrome: hide company modules, show approvals only
      applyGeneralAdminChrome(data.user);
      // Retry visibility several times in case enterApp overwrites display
      function forceApprovalsVisible() {
        applyGeneralAdminChrome(data.user);
        document.querySelectorAll(".super-only, #nav-firm-approvals, .nav-item[data-view='superadmin']").forEach(el => {
          el.style.display = "flex";
          el.style.visibility = "visible";
        });
        if (typeof showView === "function") showView("superadmin");
        loadRegisteredFirms();
      }
      setTimeout(forceApprovalsVisible, 100);
      setTimeout(forceApprovalsVisible, 400);
      setTimeout(forceApprovalsVisible, 900);
    } catch (ex) {
      console.error(ex);
      if (err) {
        err.textContent = ex.message || "Login failed";
        err.style.display = "block";
      } else alert(ex.message || "Login failed");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Open owner console";
      }
    }
  });

  function applyGeneralAdminChrome(user) {
    const role = (user?.role || "").toLowerCase();
    const isGA =
      role === "general_admin" ||
      role === "superadmin" ||
      role === "owner" ||
      user?.is_general_admin === true;

    // ALWAYS show Firm Approvals for platform admins
    document.querySelectorAll(".super-only").forEach((el) => {
      el.style.display = isGA ? "flex" : "none";
    });
    document.querySelectorAll('.nav-item[data-view="superadmin"]').forEach((el) => {
      el.innerHTML = '<span class="icon">🛡️</span> Firm Approvals';
      el.style.display = isGA ? "flex" : "none";
      el.classList.add("super-only");
    });

    // Hide company modules for pure platform admin (no company_id)
    if (isGA && (user.company_id == null || user.company_id === undefined)) {
      const hideViews = ["finance","inventory","assets","vendors","payments","users","settings",
        "finance-setup","assets-reg","currency","tasks","reports","corrections","bank"];
      hideViews.forEach(v => {
        document.querySelectorAll('.nav-item[data-view="'+v+'"]').forEach(el => {
          el.style.display = "none";
        });
      });
    }

    // Force open the approvals view
    if (isGA && typeof showView === "function") {
      try { showView("superadmin"); } catch (e) {}
    }
  }

  // ---------- Registered Firms table ----------
  async function loadRegisteredFirms() {
    const tbody = document.querySelector("#companies-table tbody");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5">Loading…</td></tr>';

    try {
      const token = localStorage.getItem("km_token");
      let rows = [];
      // Prefer new endpoint
      let res = await fetch(API + "/api/general-admin/companies", {
        headers: { Authorization: "Bearer " + token },
      });
      if (!res.ok) {
        res = await fetch(API + "/api/superadmin/companies", {
          headers: { Authorization: "Bearer " + token },
        });
      }
      if (!res.ok) throw new Error("Could not load firms");
      rows = await res.json();

      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" style="text-align:center;padding:24px;color:#888">No companies registered yet</td></tr>';
        return;
      }

      tbody.innerHTML = rows
        .map((c) => {
          const statusClass = "status-" + (c.status || "pending");
          const actions = [];
          if (c.status === "pending") {
            actions.push(
              `<button class="btn btn-sm btn-success" onclick="gaAction(${c.id},'approve')">Approve</button>`
            );
            actions.push(
              `<button class="btn btn-sm btn-danger" onclick="gaAction(${c.id},'reject')">Reject</button>`
            );
          }
          if (c.status === "approved") {
            actions.push(
              `<button class="btn btn-sm btn-primary" onclick="gaAction(${c.id},'license')">Issue / Extend License</button>`
            );
          }
          if (c.status !== "suspended" && c.status !== "rejected") {
            actions.push(
              `<button class="btn btn-sm btn-outline" onclick="gaAction(${c.id},'suspend')">Suspend</button>`
            );
          }
          return `<tr>
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td><code>${escapeHtml(c.slug)}</code></td>
            <td><span class="status-pill ${statusClass}">${escapeHtml(c.status)}</span></td>
            <td>${c.license_expires || "—"}</td>
            <td class="actions-cell">${actions.join(" ")}</td>
          </tr>`;
        })
        .join("");
    } catch (ex) {
      tbody.innerHTML = `<tr><td colspan="5" style="color:#c00">${escapeHtml(ex.message)}</td></tr>`;
    }
  }

  window.loadCompanies = loadRegisteredFirms; // keep old name working
  window.loadRegisteredFirms = loadRegisteredFirms;

  window.gaAction = async function (id, action) {
    const token = localStorage.getItem("km_token");
    const base = "/api/general-admin/companies/" + id + "/";
    const fallback = "/api/superadmin/companies/" + id + "/";
    try {
      let url = base + action;
      let opts = { method: "POST", headers: { Authorization: "Bearer " + token } };
      if (action === "license") {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify({ years: 1, notes: "Annual license" });
      }
      let res = await fetch(API + url, opts);
      if (!res.ok) {
        url = fallback + action;
        res = await fetch(API + url, opts);
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.message || "Action failed");
      alert(data.message || "Done");
      loadRegisteredFirms();
    } catch (ex) {
      alert(ex.message);
    }
  };

  // Keep old saAction alias
  window.saAction = window.gaAction;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Hook showView so opening superadmin always refreshes the table
  const _showView = window.showView;
  if (typeof _showView === "function") {
    window.showView = function (name) {
      _showView(name);
      if (name === "superadmin") loadRegisteredFirms();
    };
  }

  // If already logged in as GA on page load, apply chrome
  try {
    const u = JSON.parse(localStorage.getItem("km_user") || "null");
    if (u && (u.role === "general_admin" || u.role === "superadmin" || u.is_general_admin)) {
      document.addEventListener("DOMContentLoaded", () => applyGeneralAdminChrome(u));
    }
  } catch (_) {}
})();
