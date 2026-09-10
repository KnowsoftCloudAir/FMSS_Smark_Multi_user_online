const API = "";
let token = localStorage.getItem("km_token");
let currentUser = JSON.parse(localStorage.getItem("km_user") || "null");

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const res = await fetch(API + path, { ...options, headers });
  if (res.status === 401) {
    logout(false);
    throw new Error("Session expired");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : (detail?.[0]?.msg || data.message || "Request failed"));
  }
  return data;
}

function showPage(id) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
}

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  const el = document.getElementById("view-" + name);
  if (el) el.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  const nav = document.querySelector(`.nav-item[data-view="${name}"]`);
  if (nav) nav.classList.add("active");
  const titles = {
    dashboard: "Dashboard", finance: "Finance", inventory: "Inventory",
    assets: "Fixed Assets", vendors: "Vendors", reports: "Reports",
    users: "User Management", settings: "Settings & Branding",
  };
  document.getElementById("page-title").textContent = titles[name] || name;
  if (name === "users") loadUsers();
  if (name === "settings") loadCompanySettings();
}

function logout(redirect = true) {
  token = null;
  currentUser = null;
  localStorage.removeItem("km_token");
  localStorage.removeItem("km_user");
  if (redirect) {
    showPage("landing-page");
    showLoginCard();
  }
}

/* ---------- Splash ---------- */
function hideSplash() {
  const splash = document.getElementById("splash");
  if (!splash) return;
  splash.classList.add("hide");
  splash.style.opacity = "0";
  splash.style.visibility = "hidden";
  splash.style.pointerEvents = "none";
  setTimeout(() => { splash.style.display = "none"; }, 700);
}

function runSplash() {
  return new Promise((resolve) => {
    const fill = document.getElementById("splash-fill");
    const status = document.getElementById("splash-status");
    const messages = [
      "Loading modules…",
      "Preparing secure workspace…",
      "Starting Knowsoft FMSS ERP…",
    ];
    let p = 0;
    let i = 0;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      hideSplash();
      resolve();
    };
    // Hard failsafe — never stay on splash more than 2.5s
    setTimeout(finish, 2500);
    const timer = setInterval(() => {
      try {
        p += 12 + Math.random() * 15;
        if (p > 100) p = 100;
        if (fill) fill.style.width = p + "%";
        if (status) {
          if (p > 25 && i === 0) { status.textContent = messages[0]; i = 1; }
          if (p > 55 && i === 1) { status.textContent = messages[1]; i = 2; }
          if (p > 80 && i === 2) { status.textContent = messages[2]; i = 3; }
        }
        if (p >= 100) {
          clearInterval(timer);
          setTimeout(finish, 200);
        }
      } catch (e) {
        clearInterval(timer);
        finish();
      }
    }, 80);
  });
}

/* ---------- Auth panel toggle ---------- */
function showLoginCard() {
  document.getElementById("login-card").style.display = "block";
  document.getElementById("register-card").style.display = "none";
}
function showRegisterCard() {
  document.getElementById("login-card").style.display = "none";
  document.getElementById("register-card").style.display = "block";
}

document.getElementById("btn-show-login")?.addEventListener("click", () => {
  showLoginCard();
  document.getElementById("auth-panel")?.scrollIntoView({ behavior: "smooth" });
});
document.getElementById("btn-show-register")?.addEventListener("click", () => {
  showRegisterCard();
  document.getElementById("auth-panel")?.scrollIntoView({ behavior: "smooth" });
});
document.getElementById("btn-hero-login")?.addEventListener("click", () => {
  showLoginCard();
  document.getElementById("auth-panel")?.scrollIntoView({ behavior: "smooth" });
});
document.getElementById("btn-hero-register")?.addEventListener("click", () => {
  showRegisterCard();
  document.getElementById("auth-panel")?.scrollIntoView({ behavior: "smooth" });
});
document.getElementById("switch-to-register")?.addEventListener("click", (e) => {
  e.preventDefault();
  showRegisterCard();
});
document.getElementById("switch-to-login")?.addEventListener("click", (e) => {
  e.preventDefault();
  showLoginCard();
});

// Auto-slug from company name
document.getElementById("reg-company-name")?.addEventListener("input", (e) => {
  const slugEl = document.getElementById("reg-company-slug");
  if (slugEl && !slugEl.dataset.touched) {
    slugEl.value = e.target.value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 80);
  }
});
document.getElementById("reg-company-slug")?.addEventListener("input", function () {
  this.dataset.touched = "1";
  this.value = this.value.toLowerCase().replace(/[^a-z0-9\-]/g, "");
});

/* ---------- Login ---------- */
document.getElementById("login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("login-btn");
  const err = document.getElementById("login-error");
  err.style.display = "none";
  btn.disabled = true;
  btn.textContent = "Signing in…";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const form = new URLSearchParams();
    form.append("username", username);
    form.append("password", password);
    const res = await fetch(API + "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");

    token = data.access_token;
    currentUser = data.user;
    localStorage.setItem("km_token", token);
    localStorage.setItem("km_user", JSON.stringify(currentUser));
    enterApp();
  } catch (ex) {
    err.textContent = ex.message || "Login failed";
    err.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign In";
  }
});

/* ---------- Register company ---------- */
document.getElementById("register-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("register-btn");
  const err = document.getElementById("register-error");
  const ok = document.getElementById("register-success");
  err.style.display = "none";
  ok.style.display = "none";
  btn.disabled = true;
  btn.textContent = "Creating…";

  const payload = {
    company_name: document.getElementById("reg-company-name").value.trim(),
    company_slug: document.getElementById("reg-company-slug").value.trim().toLowerCase(),
    address: document.getElementById("reg-address").value.trim(),
    admin_username: document.getElementById("reg-admin-user").value.trim(),
    admin_email: document.getElementById("reg-admin-email").value.trim(),
    admin_full_name: document.getElementById("reg-admin-name").value.trim() || null,
    admin_password: document.getElementById("reg-admin-pass").value,
  };

  try {
    const data = await api("/api/auth/register-company", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    ok.innerHTML = `Company <strong>${data.company.name}</strong> created.<br/>Login as <code>${data.company.slug}/${data.admin_username}</code>`;
    ok.style.display = "block";
    document.getElementById("username").value = `${data.company.slug}/${data.admin_username}`;
    setTimeout(() => showLoginCard(), 2500);
  } catch (ex) {
    err.textContent = ex.message;
    err.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Create Company Account";
  }
});

function enterApp() {
  showPage("app-page");
  document.getElementById("current-user-name").textContent =
    currentUser.full_name || currentUser.username;
  document.getElementById("current-user-role").textContent =
    (currentUser.role || "").replace("_", " ").toUpperCase();
  document.getElementById("sidebar-company").textContent =
    currentUser.company_name || currentUser.company_slug || "";
  document.getElementById("org-name-display").textContent =
    currentUser.company_name || "";

  const isAdmin = ["company_admin", "admin", "superadmin"].includes(currentUser.role);
  document.querySelectorAll(".admin-only").forEach(el => {
    el.style.display = isAdmin ? "flex" : "none";
  });
  document.getElementById("admin-divider").style.display = isAdmin ? "block" : "none";

  document.querySelectorAll("[data-perm]").forEach(el => {
    const key = "can_access_" + el.dataset.perm;
    el.style.display = currentUser[key] === false ? "none" : "";
  });

  loadCompanySettings();
  showView("dashboard");
}

document.getElementById("logout-btn").addEventListener("click", () => logout(true));

document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", (e) => {
    e.preventDefault();
    const view = item.dataset.view;
    if (view) showView(view);
    document.getElementById("sidebar").classList.remove("open");
  });
});
document.getElementById("menu-toggle")?.addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});

/* ---------- Users ---------- */
async function loadUsers() {
  try {
    const users = await api("/api/admin/users");
    const tbody = document.querySelector("#users-table tbody");
    tbody.innerHTML = "";
    document.getElementById("kpi-users").textContent = users.length;
    users.forEach(u => {
      const perms = [];
      if (u.can_access_finance) perms.push("Finance");
      if (u.can_access_inventory) perms.push("Inventory");
      if (u.can_access_assets) perms.push("Assets");
      if (u.can_access_vendors) perms.push("Vendors");
      if (u.can_access_reports) perms.push("Reports");
      const roleClass = u.role === "user" ? "user" : "company_admin";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${u.id}</td>
        <td><strong>${u.username}</strong></td>
        <td>${u.full_name || "—"}</td>
        <td>${u.email}</td>
        <td><span class="badge badge-${roleClass}">${u.role}</span></td>
        <td><span class="badge badge-${u.is_active ? "active" : "inactive"}">${u.is_active ? "Active" : "Inactive"}</span></td>
        <td><div class="perm-tags">${perms.map(p => `<span class="perm-tag">${p}</span>`).join("")}</div></td>
        <td>
          <button class="btn btn-sm btn-outline" onclick="editUser(${u.id})">Edit</button>
          ${u.id !== currentUser.id ? `<button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id}, '${u.username}')">Delete</button>` : ""}
        </td>`;
      tbody.appendChild(tr);
    });
  } catch (ex) {
    alert("Failed to load users: " + ex.message);
  }
}

let editingUserId = null;
document.getElementById("btn-add-user")?.addEventListener("click", () => {
  editingUserId = null;
  document.getElementById("modal-title").textContent = "Create Staff Account";
  document.getElementById("user-form").reset();
  document.getElementById("edit-user-id").value = "";
  document.getElementById("u-username").disabled = false;
  document.getElementById("pwd-hint").textContent = "(required)";
  document.getElementById("u-password").required = true;
  document.getElementById("user-modal").classList.add("open");
});
document.getElementById("modal-close")?.addEventListener("click", closeModal);
document.getElementById("modal-cancel")?.addEventListener("click", closeModal);
function closeModal() {
  document.getElementById("user-modal").classList.remove("open");
}

window.editUser = async function (id) {
  try {
    const users = await api("/api/admin/users");
    const u = users.find(x => x.id === id);
    if (!u) return;
    editingUserId = id;
    document.getElementById("modal-title").textContent = "Edit Staff Account";
    document.getElementById("edit-user-id").value = id;
    document.getElementById("u-username").value = u.username;
    document.getElementById("u-username").disabled = true;
    document.getElementById("u-email").value = u.email;
    document.getElementById("u-fullname").value = u.full_name || "";
    document.getElementById("u-password").value = "";
    document.getElementById("u-password").required = false;
    document.getElementById("pwd-hint").textContent = "(leave blank to keep)";
    document.getElementById("u-role").value = u.role === "admin" ? "company_admin" : u.role;
    document.getElementById("u-active").checked = u.is_active;
    document.getElementById("u-finance").checked = u.can_access_finance;
    document.getElementById("u-inventory").checked = u.can_access_inventory;
    document.getElementById("u-assets").checked = u.can_access_assets;
    document.getElementById("u-vendors").checked = u.can_access_vendors;
    document.getElementById("u-reports").checked = u.can_access_reports;
    document.getElementById("user-modal").classList.add("open");
  } catch (ex) {
    alert(ex.message);
  }
};

window.deleteUser = async function (id, username) {
  if (!confirm(`Delete user "${username}"?`)) return;
  try {
    await api(`/api/admin/users/${id}`, { method: "DELETE" });
    loadUsers();
  } catch (ex) {
    alert(ex.message);
  }
};

document.getElementById("user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    username: document.getElementById("u-username").value.trim(),
    email: document.getElementById("u-email").value.trim(),
    full_name: document.getElementById("u-fullname").value.trim() || null,
    role: document.getElementById("u-role").value,
    is_active: document.getElementById("u-active").checked,
    can_access_finance: document.getElementById("u-finance").checked,
    can_access_inventory: document.getElementById("u-inventory").checked,
    can_access_assets: document.getElementById("u-assets").checked,
    can_access_vendors: document.getElementById("u-vendors").checked,
    can_access_reports: document.getElementById("u-reports").checked,
    can_edit_assets: document.getElementById("u-edit-assets")?.checked || false,
    can_approve_payment: document.getElementById("u-approve")?.checked || false,
  };
  const pwd = document.getElementById("u-password").value;
  if (pwd) payload.password = pwd;

  try {
    if (editingUserId) {
      if (!pwd) delete payload.password;
      await api(`/api/admin/users/${editingUserId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      if (!pwd || pwd.length < 6) {
        alert("Password must be at least 6 characters");
        return;
      }
      payload.password = pwd;
      await api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    closeModal();
    loadUsers();
  } catch (ex) {
    alert(ex.message);
  }
});

/* ---------- Company settings ---------- */
async function loadCompanySettings() {
  try {
    const s = await api("/api/company");
    document.getElementById("set-org-name").value = s.name || "";
    document.getElementById("set-address").value = s.address || "";
    document.getElementById("set-project-code").value = s.project_code || "";
    document.getElementById("set-currency-code").value = s.reporting_currency_code || "NGN";
    document.getElementById("set-currency-symbol").value = s.reporting_currency_symbol || "₦";
    document.getElementById("org-name-display").textContent = s.name || "";
    document.getElementById("sidebar-company").textContent = s.name || "";

    const logoUrl = (s.logo_path || "/static/images/logo.png") + "?t=" + Date.now();
    const favUrl = (s.favicon_path || "/static/images/favicon.ico") + "?t=" + Date.now();
    ["sidebar-logo", "preview-logo"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.src = logoUrl;
    });
    const fav = document.getElementById("favicon");
    if (fav) fav.href = favUrl;
    const prevFav = document.getElementById("preview-favicon");
    if (prevFav) prevFav.src = favUrl;
  } catch (ex) {
    console.warn("Company settings:", ex);
  }
}

document.getElementById("settings-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/company", {
      method: "PUT",
      body: JSON.stringify({
        name: document.getElementById("set-org-name").value,
        address: document.getElementById("set-address").value,
        project_code: document.getElementById("set-project-code").value,
        reporting_currency_code: document.getElementById("set-currency-code").value,
        reporting_currency_symbol: document.getElementById("set-currency-symbol").value,
      }),
    });
    alert("Settings saved");
    loadCompanySettings();
  } catch (ex) {
    alert(ex.message);
  }
});

document.getElementById("btn-upload-logo")?.addEventListener("click", async () => {
  const fileInput = document.getElementById("logo-file");
  if (!fileInput.files.length) return alert("Select an image first");
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  try {
    const res = await fetch(API + "/api/company/upload-logo", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    alert("Logo uploaded");
    loadCompanySettings();
  } catch (ex) {
    alert(ex.message);
  }
});

document.getElementById("btn-upload-favicon")?.addEventListener("click", async () => {
  const fileInput = document.getElementById("favicon-file");
  if (!fileInput.files.length) return alert("Select an icon first");
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  try {
    const res = await fetch(API + "/api/company/upload-favicon", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    alert("Icon uploaded");
    loadCompanySettings();
  } catch (ex) {
    alert(ex.message);
  }
});

/* ---------- Boot ---------- */
/* init moved to end of file */


/* ========== Extended modules: payments, assets, superadmin, charts, security ========== */

let chartAssets = null;
let chartPayments = null;

const titlesExtra = {
  payments: "Payment Requests",
  "finance-setup": "Finance Setup",
  "assets-reg": "Asset Register",
  superadmin: "Superadmin",
  security: "Security & Backup",
};

const _origShowView = showView;
showView = function (name) {
  // map old assets view to assets-reg if needed
  if (name === "assets") name = "assets-reg";
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  const el = document.getElementById("view-" + name);
  if (el) el.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  const nav = document.querySelector(`.nav-item[data-view="${name}"]`) ||
              document.querySelector(`.nav-item[data-view="assets"]`);
  if (nav) nav.classList.add("active");
  const titles = {
    dashboard: "Dashboard", finance: "Finance", inventory: "Inventory",
    assets: "Fixed Assets", vendors: "Vendors", reports: "Reports",
    users: "User Management", settings: "Settings & Branding",
    ...titlesExtra,
  };
  document.getElementById("page-title").textContent = titles[name] || name;
  if (name === "users") loadUsers();
  if (name === "settings") loadCompanySettings();
  if (name === "dashboard") loadDashboardCharts();
  if (name === "payments") { loadPaymentFormData(); loadPayments(); }
  if (name === "finance-setup") loadFinanceSetup();
  if (name === "assets-reg") loadAssets();
  if (name === "superadmin") loadCompanies();
};

const _origEnterApp = enterApp;
enterApp = function () {
  showPage("app-page");
  document.getElementById("current-user-name").textContent =
    currentUser.full_name || currentUser.username;
  document.getElementById("current-user-role").textContent =
    (currentUser.role || "").replace("_", " ").toUpperCase();
  document.getElementById("sidebar-company").textContent =
    currentUser.company_name || currentUser.company_slug || "";
  document.getElementById("org-name-display").textContent =
    currentUser.company_name || "";

  const isAdmin = ["company_admin", "admin", "superadmin"].includes(currentUser.role);
  const isSuper = currentUser.role === "superadmin";
  const isFinance = ["finance", "company_admin", "superadmin"].includes(currentUser.role);

  document.querySelectorAll(".admin-only").forEach(el => {
    el.style.display = isAdmin ? "flex" : "none";
  });
  document.querySelectorAll(".super-only").forEach(el => {
    el.style.display = isSuper ? "flex" : "none";
  });
  const finSetup = document.querySelector('[data-view="finance-setup"]');
  if (finSetup) finSetup.style.display = isFinance ? "flex" : "none";

  document.getElementById("admin-divider").style.display = (isAdmin || isSuper) ? "block" : "none";

  document.querySelectorAll("[data-perm]").forEach(el => {
    const key = "can_access_" + el.dataset.perm;
    if (currentUser[key] === false && currentUser.role !== "superadmin") {
      el.style.display = "none";
    }
  });

  // Auth header for download links
  document.querySelectorAll('a[href^="/api/"]').forEach(a => {
    a.addEventListener("click", async (e) => {
      if (!token) return;
      e.preventDefault();
      const res = await fetch(a.href, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) { alert("Download failed"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const tmp = document.createElement("a");
      tmp.href = url;
      tmp.download = (a.href.split("/").pop() || "download") + (a.href.includes("backup") ? ".zip" : ".csv");
      if (a.href.includes("backup")) tmp.download = "backup.zip";
      tmp.click();
      URL.revokeObjectURL(url);
    });
  });

  if (!isSuper) loadCompanySettings();
  showView(isSuper ? "superadmin" : "dashboard");
};

async function loadDashboardCharts() {
  try {
    const s = await api("/api/dashboard/stats");
    if (s.assets_count !== undefined) {
      document.getElementById("kpi-assets").textContent = s.assets_count;
      document.getElementById("kpi-inventory").textContent = s.payments_pending ?? 0;
      document.getElementById("kpi-vendors").textContent = s.payments_paid ?? 0;
      document.getElementById("kpi-users").textContent = s.users_count ?? "—";
    }
    const cond = s.condition_breakdown || {};
    const pay = s.payment_status_breakdown || {};

    const common3d = {
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { grid: { color: "rgba(15,28,58,0.06)" } },
        y: { grid: { color: "rgba(15,28,58,0.06)" }, beginAtZero: true },
      },
    };

    const ctx1 = document.getElementById("chart-assets");
    if (ctx1 && window.Chart) {
      if (chartAssets) chartAssets.destroy();
      chartAssets = new Chart(ctx1, {
        type: "bar",
        data: {
          labels: Object.keys(cond),
          datasets: [{
            label: "Assets by Condition",
            data: Object.values(cond),
            backgroundColor: [
              "rgba(39,174,96,0.85)",
              "rgba(52,152,219,0.85)",
              "rgba(231,76,60,0.85)",
              "rgba(243,156,18,0.85)",
            ],
            borderWidth: 0,
            borderRadius: 8,
            borderSkipped: false,
          }],
        },
        options: {
          ...common3d,
          plugins: {
            ...common3d.plugins,
            title: { display: true, text: "Asset Condition (3D style)", font: { weight: "700" } },
          },
        },
      });
    }
    const ctx2 = document.getElementById("chart-payments");
    if (ctx2 && window.Chart) {
      if (chartPayments) chartPayments.destroy();
      chartPayments = new Chart(ctx2, {
        type: "doughnut",
        data: {
          labels: Object.keys(pay),
          datasets: [{
            data: Object.values(pay),
            backgroundColor: [
              "rgba(243,156,18,0.9)",
              "rgba(52,152,219,0.9)",
              "rgba(155,89,182,0.9)",
              "rgba(39,174,96,0.9)",
              "rgba(231,76,60,0.9)",
            ],
            borderWidth: 3,
            borderColor: "#fff",
            hoverOffset: 12,
          }],
        },
        options: {
          plugins: {
            legend: { position: "bottom" },
            title: { display: true, text: "Payment Workflow Status", font: { weight: "700" } },
          },
          cutout: "45%",
        },
      });
    }
  } catch (ex) {
    console.warn("Dashboard stats", ex);
  }
}

/* ---- Finance setup ---- */
async function loadFinanceSetup() {
  try {
    const [coa, budgets, expenses] = await Promise.all([
      api("/api/finance/coa"),
      api("/api/finance/budget-codes"),
      api("/api/finance/expense-codes"),
    ]);
    document.getElementById("coa-list").innerHTML = coa.map(c =>
      `<li><strong>${c.code}</strong> — ${c.name} <em>(${c.account_type})</em></li>`).join("");
    document.getElementById("budget-list").innerHTML = budgets.map(b =>
      `<li><strong>${b.code}</strong> — ${b.description || ""} · Budget: ${b.amount}</li>`).join("");
    document.getElementById("expense-list").innerHTML = expenses.map(e =>
      `<li><strong>${e.code}</strong> — ${e.description}<br/><small>Dr: ${e.default_debit_label || "—"} · Cr: ${e.default_credit_label || "—"}</small></li>`).join("");

    const fill = (sel, rows, labelFn) => {
      const el = document.getElementById(sel);
      if (!el) return;
      const keep = el.querySelector('option[value=""]');
      el.innerHTML = "";
      if (keep) el.appendChild(keep);
      else el.innerHTML = '<option value="">—</option>';
      rows.forEach(r => {
        const o = document.createElement("option");
        o.value = r.id;
        o.textContent = labelFn(r);
        el.appendChild(o);
      });
    };
    fill("exp-debit", coa, r => `${r.code} - ${r.name}`);
    fill("exp-credit", coa, r => `${r.code} - ${r.name}`);
  } catch (ex) { console.warn(ex); }
}

document.getElementById("coa-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/finance/coa", {
      method: "POST",
      body: JSON.stringify({
        code: document.getElementById("coa-code").value,
        name: document.getElementById("coa-name").value,
        account_type: document.getElementById("coa-type").value,
      }),
    });
    e.target.reset();
    loadFinanceSetup();
  } catch (ex) { alert(ex.message); }
});

document.getElementById("budget-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/finance/budget-codes", {
      method: "POST",
      body: JSON.stringify({
        code: document.getElementById("bud-code").value,
        description: document.getElementById("bud-desc").value,
        amount: parseFloat(document.getElementById("bud-amount").value || 0),
      }),
    });
    e.target.reset();
    loadFinanceSetup();
  } catch (ex) { alert(ex.message); }
});

document.getElementById("expense-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const debit = document.getElementById("exp-debit").value;
    const credit = document.getElementById("exp-credit").value;
    await api("/api/finance/expense-codes", {
      method: "POST",
      body: JSON.stringify({
        code: document.getElementById("exp-code").value,
        description: document.getElementById("exp-desc").value,
        default_debit_account_id: debit ? parseInt(debit) : null,
        default_credit_account_id: credit ? parseInt(credit) : null,
      }),
    });
    e.target.reset();
    loadFinanceSetup();
  } catch (ex) { alert(ex.message); }
});

/* ---- Payments ---- */
async function loadPaymentFormData() {
  try {
    const [budgets, expenses, coa, approvers] = await Promise.all([
      api("/api/finance/budget-codes"),
      api("/api/finance/expense-codes"),
      api("/api/finance/coa"),
      api("/api/admin/approvers"),
    ]);
    window._expenses = expenses;
    const fill = (id, rows, fn) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = '<option value="">— Select —</option>';
      rows.forEach(r => {
        const o = document.createElement("option");
        o.value = r.id;
        o.textContent = fn(r);
        el.appendChild(o);
      });
    };
    fill("pay-budget", budgets, r => `${r.code} — ${r.description || ""}`);
    fill("pay-expense", expenses, r => `${r.code} — ${r.description}`);
    fill("pay-debit", coa, r => `${r.code} - ${r.name}`);
    fill("pay-credit", coa, r => `${r.code} - ${r.name}`);
    fill("pay-approver", approvers, r => `${r.full_name || r.username} (${r.role})`);
  } catch (ex) { console.warn(ex); }
}

document.getElementById("pay-expense")?.addEventListener("change", function () {
  const exp = (window._expenses || []).find(e => String(e.id) === this.value);
  document.getElementById("pay-expense-desc").value = exp ? exp.description : "";
  if (exp?.default_debit_account_id) {
    document.getElementById("pay-debit").value = exp.default_debit_account_id;
  }
  if (exp?.default_credit_account_id) {
    document.getElementById("pay-credit").value = exp.default_credit_account_id;
  }
});

document.getElementById("btn-new-payment")?.addEventListener("click", () => {
  document.getElementById("payment-form").style.display = "grid";
  loadPaymentFormData();
});
document.getElementById("btn-cancel-payment")?.addEventListener("click", () => {
  document.getElementById("payment-form").style.display = "none";
});

document.getElementById("payment-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const debit = document.getElementById("pay-debit").value;
  const credit = document.getElementById("pay-credit").value;
  try {
    await api("/api/payments/request", {
      method: "POST",
      body: JSON.stringify({
        budget_code_id: parseInt(document.getElementById("pay-budget").value),
        expense_code_id: parseInt(document.getElementById("pay-expense").value),
        amount: parseFloat(document.getElementById("pay-amount").value),
        payee_name: document.getElementById("pay-payee").value,
        narration: document.getElementById("pay-narration").value,
        debit_account_id: debit ? parseInt(debit) : null,
        credit_account_id: credit ? parseInt(credit) : null,
        designated_approver_id: parseInt(document.getElementById("pay-approver").value),
      }),
    });
    alert("Payment request submitted");
    e.target.reset();
    document.getElementById("payment-form").style.display = "none";
    loadPayments();
  } catch (ex) { alert(ex.message); }
});

async function loadPayments() {
  try {
    const rows = await api("/api/payments");
    const tbody = document.querySelector("#payments-table tbody");
    if (!tbody) return;
    const role = currentUser.role;
    tbody.innerHTML = rows.map(p => {
      let actions = "";
      if (p.status === "submitted" && ["program", "project_manager", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-success" onclick="actPay(${p.id},'program-approve')">Program Approve</button> `;
      }
      if (p.status === "program_approved" && ["finance", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-primary" onclick="actPay(${p.id},'finance-approve')">Finance Approve</button> `;
      }
      if (p.status === "finance_approved" && ["finance", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-accent" onclick="actPay(${p.id},'pay')">Mark Paid</button> `;
      }
      if (["submitted", "program_approved"].includes(p.status) && ["finance", "program", "project_manager", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-danger" onclick="actPay(${p.id},'reject')">Reject</button>`;
      }
      return `<tr>
        <td>${p.request_no}</td>
        <td>${p.payee_name || "—"}</td>
        <td>${Number(p.amount).toLocaleString()}</td>
        <td>${p.expense_code || ""} — ${p.expense_description || ""}</td>
        <td><span class="status-pill status-${p.status}">${p.status}</span></td>
        <td>${actions}</td>
      </tr>`;
    }).join("");
  } catch (ex) { console.warn(ex); }
}

window.actPay = async function (id, action) {
  let body = { comment: "" };
  if (action === "finance-approve") {
    const debit = prompt("Debit account ID (leave blank to keep current):");
    const credit = prompt("Credit account ID (leave blank to keep current):");
    if (debit) body.debit_account_id = parseInt(debit);
    if (credit) body.credit_account_id = parseInt(credit);
    body.comment = prompt("Comment (optional):") || "";
  } else if (action === "reject") {
    body.comment = prompt("Rejection reason:") || "Rejected";
  }
  try {
    await api(`/api/payments/${id}/${action}`, { method: "POST", body: JSON.stringify(body) });
    loadPayments();
  } catch (ex) { alert(ex.message); }
};

/* ---- Assets ---- */
document.getElementById("btn-add-asset")?.addEventListener("click", () => {
  document.getElementById("asset-form").style.display = "grid";
});
document.getElementById("btn-cancel-asset")?.addEventListener("click", () => {
  document.getElementById("asset-form").style.display = "none";
});

document.getElementById("asset-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/assets", {
      method: "POST",
      body: JSON.stringify({
        asset_number: document.getElementById("ast-number").value,
        asset_name: document.getElementById("ast-name").value,
        category: document.getElementById("ast-cat").value,
        location: document.getElementById("ast-loc").value,
        cost: parseFloat(document.getElementById("ast-cost").value || 0),
        nbv: parseFloat(document.getElementById("ast-nbv").value || 0),
        condition: document.getElementById("ast-cond").value,
        insurance: document.getElementById("ast-ins").value,
      }),
    });
    e.target.reset();
    document.getElementById("asset-form").style.display = "none";
    loadAssets();
  } catch (ex) { alert(ex.message); }
});

async function loadAssets() {
  try {
    const rows = await api("/api/assets");
    const tbody = document.querySelector("#assets-table tbody");
    if (!tbody) return;
    const canEdit = currentUser.can_edit_assets || ["finance", "project_manager", "company_admin", "asset_editor"].includes(currentUser.role);
    tbody.innerHTML = rows.map(a => `<tr>
      <td>${a.image_path ? `<img class="asset-thumb" src="${a.image_path}" />` : "—"}</td>
      <td>${a.asset_number}</td>
      <td>${a.asset_name}</td>
      <td>${a.category || ""}</td>
      <td>${Number(a.cost || 0).toLocaleString()}</td>
      <td>${Number(a.nbv || 0).toLocaleString()}</td>
      <td>${a.condition || ""}</td>
      <td>${canEdit ? `<input type="file" accept="image/*" onchange="uploadAssetPhoto(${a.id}, this)" />` : "View only"}</td>
    </tr>`).join("");
  } catch (ex) {
    if (ex.message.includes("403") || ex.message.includes("access")) {
      document.querySelector("#assets-table tbody").innerHTML = "<tr><td colspan='8'>No access to asset register</td></tr>";
    }
  }
}

window.uploadAssetPhoto = async function (id, input) {
  if (!input.files.length) return;
  const form = new FormData();
  form.append("file", input.files[0]);
  try {
    const res = await fetch(API + `/api/assets/${id}/photo`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    loadAssets();
  } catch (ex) { alert(ex.message); }
};

/* ---- Superadmin ---- */
async function loadCompanies() {
  try {
    const rows = await api("/api/superadmin/companies");
    const tbody = document.querySelector("#companies-table tbody");
    if (!tbody) return;
    tbody.innerHTML = rows.map(c => `<tr>
      <td>${c.name}</td>
      <td><code>${c.slug}</code></td>
      <td><span class="status-pill status-${c.status}">${c.status}</span></td>
      <td>${c.license_expires || "—"}</td>
      <td>
        ${c.status === "pending" ? `<button class="btn btn-sm btn-success" onclick="saAction(${c.id},'approve')">Approve</button>` : ""}
        ${c.status === "pending" ? `<button class="btn btn-sm btn-danger" onclick="saAction(${c.id},'reject')">Reject</button>` : ""}
        ${c.status === "approved" ? `<button class="btn btn-sm btn-primary" onclick="saAction(${c.id},'license')">Issue 1yr License</button>` : ""}
        ${c.status !== "suspended" ? `<button class="btn btn-sm btn-outline" onclick="saAction(${c.id},'suspend')">Suspend</button>` : ""}
      </td>
    </tr>`).join("");
  } catch (ex) { alert(ex.message); }
}

window.saAction = async function (id, action) {
  try {
    if (action === "license") {
      await api(`/api/superadmin/companies/${id}/license`, {
        method: "POST",
        body: JSON.stringify({ years: 1, notes: "Annual license" }),
      });
    } else {
      await api(`/api/superadmin/companies/${id}/${action}`, { method: "POST" });
    }
    loadCompanies();
  } catch (ex) { alert(ex.message); }
};

/* ---- Security ---- */
document.getElementById("pwd-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: document.getElementById("pwd-current").value,
        new_password: document.getElementById("pwd-new").value,
      }),
    });
    alert("Password updated");
    e.target.reset();
  } catch (ex) { alert(ex.message); }
});

document.getElementById("reset-req-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/auth/request-reset", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("reset-email").value,
        company_slug: document.getElementById("reset-slug").value || null,
      }),
    });
    alert(data.message + (data.reset_token ? "\n\nDemo token:\n" + data.reset_token : ""));
    if (data.reset_token) document.getElementById("reset-token").value = data.reset_token;
  } catch (ex) { alert(ex.message); }
});

document.getElementById("reset-confirm-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/auth/confirm-reset", {
      method: "POST",
      body: JSON.stringify({
        token: document.getElementById("reset-token").value,
        new_password: document.getElementById("reset-new").value,
      }),
    });
    alert("Password reset complete. You can sign in.");
  } catch (ex) { alert(ex.message); }
});

document.getElementById("restore-file")?.addEventListener("change", async function () {
  if (!this.files.length) return;
  const form = new FormData();
  form.append("file", this.files[0]);
  try {
    const res = await fetch(API + "/api/backup/restore", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Restore failed");
    alert(data.message);
  } catch (ex) { alert(ex.message); }
});

// Update user form roles
(function patchUserRoles() {
  const sel = document.getElementById("u-role");
  if (sel && sel.options.length < 5) {
    sel.innerHTML = `
      <option value="user">User</option>
      <option value="finance">Finance</option>
      <option value="program">Program</option>
      <option value="project_manager">Project Manager</option>
      <option value="asset_editor">Asset Editor</option>
      <option value="company_admin">Company Admin</option>`;
  }
  // add can_edit_assets checkbox if missing
  const fs = document.querySelector("#user-form fieldset");
  if (fs && !document.getElementById("u-edit-assets")) {
    const lab = document.createElement("label");
    lab.innerHTML = `<input type="checkbox" id="u-edit-assets" /> Can Edit Assets`;
    fs.appendChild(lab);
    const lab2 = document.createElement("label");
    lab2.innerHTML = `<input type="checkbox" id="u-approve" /> Can Approve Payments`;
    fs.appendChild(lab2);
  }
})();


/* ---- Payment detail view ---- */
window.openPaymentDetail = async function (id) {
  try {
    const p = await api(`/api/payments/${id}`);
    document.getElementById("pd-title").textContent = p.request_no + " — " + (p.status || "");
    document.getElementById("pd-body").innerHTML = `
      <p><strong>Payee:</strong> ${p.payee_name || "—"}</p>
      <p><strong>Amount:</strong> ${Number(p.amount).toLocaleString()}</p>
      <p><strong>Budget:</strong> ${p.budget_code || ""} — ${p.budget_description || ""}</p>
      <p><strong>Expense:</strong> ${p.expense_code || ""} — ${p.expense_description || ""}</p>
      <p><strong>Debit:</strong> ${p.debit_account || "—"}</p>
      <p><strong>Credit:</strong> ${p.credit_account || "—"}</p>
      <p><strong>Requester:</strong> ${p.requester || "—"}</p>
      <p><strong>Approver:</strong> ${p.designated_approver || "—"}</p>
      <p><strong>Narration:</strong> ${p.narration || "—"}</p>
      ${p.rejection_reason ? `<p><strong>Rejection:</strong> ${p.rejection_reason}</p>` : ""}
      <h4 style="margin-top:12px;">Attachments</h4>
      <ul>${(p.attachments || []).map(a => `<li><a href="${a.url}" target="_blank">${a.filename}</a> (${a.size_bytes} bytes)</li>`).join("") || "<li>None</li>"}</ul>
      <h4 style="margin-top:12px;">History</h4>
      <ul>${(p.history || []).map(h => `<li>${h.action} — ${h.comment || ""} <small>${h.at || ""}</small></li>`).join("")}</ul>
    `;
    document.getElementById("payment-detail-modal").dataset.pid = id;
    document.getElementById("payment-detail-modal").classList.add("open");
  } catch (ex) { alert(ex.message); }
};

document.getElementById("pd-upload-btn")?.addEventListener("click", async () => {
  const pid = document.getElementById("payment-detail-modal").dataset.pid;
  const f = document.getElementById("pd-file");
  if (!pid || !f.files.length) return alert("Select a file");
  if (f.files[0].size > 100 * 1024) return alert("Max 100KB");
  const form = new FormData();
  form.append("file", f.files[0]);
  try {
    const res = await fetch(API + `/api/payments/${pid}/attachments`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    openPaymentDetail(pid);
  } catch (ex) { alert(ex.message); }
});

// Enhance payments table with View button
const _loadPayments = loadPayments;
loadPayments = async function () {
  try {
    const rows = await api("/api/payments");
    const tbody = document.querySelector("#payments-table tbody");
    if (!tbody) return;
    const role = currentUser.role;
    tbody.innerHTML = rows.map(p => {
      let actions = `<button class="btn btn-sm btn-outline" onclick="openPaymentDetail(${p.id})">Open</button> `;
      if (p.status === "submitted" && ["program", "project_manager", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-success" onclick="actPay(${p.id},'program-approve')">Program Approve</button> `;
      }
      if (p.status === "program_approved" && ["finance", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-primary" onclick="actPay(${p.id},'finance-approve')">Finance Approve</button> `;
      }
      if (p.status === "finance_approved" && ["finance", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-accent" onclick="actPay(${p.id},'pay')">Mark Paid</button> `;
      }
      if (["submitted", "program_approved"].includes(p.status) && ["finance", "program", "project_manager", "company_admin"].includes(role)) {
        actions += `<button class="btn btn-sm btn-danger" onclick="actPay(${p.id},'reject')">Reject</button>`;
      }
      return `<tr>
        <td>${p.request_no}</td>
        <td>${p.payee_name || "—"}</td>
        <td>${Number(p.amount).toLocaleString()}</td>
        <td>${p.expense_code || ""} — ${p.expense_description || ""}</td>
        <td><span class="status-pill status-${p.status}">${p.status}</span></td>
        <td>${actions}</td>
      </tr>`;
    }).join("");
  } catch (ex) { console.warn(ex); }
};

/* ---- Asset dashboard + form fields ---- */
let chartIns, chartCond2, chartLife, chartCost;

async function loadAssetDashboard() {
  try {
    const d = await api("/api/assets/dashboard");
    const k = document.getElementById("asset-kpis");
    if (k) {
      k.innerHTML = `
        <div class="kpi-card"><div class="kpi-value">${d.total}</div><div class="kpi-label">Active Assets</div></div>
        <div class="kpi-card"><div class="kpi-value">${d.insured}</div><div class="kpi-label">Insured</div></div>
        <div class="kpi-card"><div class="kpi-value">${d.uninsured}</div><div class="kpi-label">Uninsured</div></div>
        <div class="kpi-card"><div class="kpi-value">${d.damaged}</div><div class="kpi-label">Damaged</div></div>
        <div class="kpi-card"><div class="kpi-value">${d.under_repair}</div><div class="kpi-label">Under Repair</div></div>
        <div class="kpi-card"><div class="kpi-value">${Number(d.total_nbv).toLocaleString()}</div><div class="kpi-label">Total NBV</div></div>`;
    }
    if (!window.Chart) return;
    const mk = (id, type, labels, data, label) => {
      const ctx = document.getElementById(id);
      if (!ctx) return null;
      return new Chart(ctx, {
        type,
        data: { labels, datasets: [{ label, data, backgroundColor: ["#27AE60","#E74C3C","#3498DB","#F39C12","#9B59B6"], borderRadius: 8, borderWidth: 0, hoverOffset: 10 }] },
        options: { plugins: { legend: { position: "bottom" }, title: { display: true, text: label, font: { weight: "700" } } }, scales: type === "bar" ? { y: { beginAtZero: true } } : undefined },
      });
    };
    if (chartIns) chartIns.destroy();
    chartIns = mk("chart-asset-ins", "doughnut", ["Insured", "Uninsured"], [d.insured, d.uninsured], "Insurance");
    if (chartCond2) chartCond2.destroy();
    const bc = d.by_condition || {};
    chartCond2 = mk("chart-asset-cond", "bar", Object.keys(bc), Object.values(bc), "Condition");
    if (chartLife) chartLife.destroy();
    const ul = d.useful_life_buckets || {};
    chartLife = mk("chart-asset-life", "bar", Object.keys(ul), Object.values(ul), "Useful Life");
    if (chartCost) chartCost.destroy();
    chartCost = mk("chart-asset-cost", "bar", ["Cost", "NBV"], [d.total_cost, d.total_nbv], "Cost vs NBV");
  } catch (ex) { console.warn(ex); }
}

const _loadAssets = loadAssets;
loadAssets = async function () {
  await loadAssetDashboard();
  try {
    const rows = await api("/api/assets");
    const tbody = document.querySelector("#assets-table tbody");
    if (!tbody) return;
    const canEdit = currentUser.can_edit_assets || ["finance", "project_manager", "company_admin", "asset_editor"].includes(currentUser.role);
    tbody.innerHTML = rows.map(a => `<tr>
      <td>${a.image_path ? `<img class="asset-thumb" src="${a.image_path}" />` : "—"}</td>
      <td>${a.asset_number}</td>
      <td><a href="#" onclick="openAsset(${a.id});return false;">${a.asset_name}</a></td>
      <td>${a.category || ""}</td>
      <td>${Number(a.cost || 0).toLocaleString()}</td>
      <td>${Number(a.nbv || 0).toLocaleString()}</td>
      <td>${a.condition || ""} / ${a.status || ""}</td>
      <td>${canEdit ? `<input type="file" accept="image/*" onchange="uploadAssetPhoto(${a.id}, this)" />
        <button class="btn btn-sm btn-outline" onclick="disposeAsset(${a.id})">Dispose</button>` : "View"}</td>
    </tr>`).join("");
  } catch (ex) { console.warn(ex); }
};

window.openAsset = async function (id) {
  try {
    const a = await api(`/api/assets/${id}`);
    const canFin = ["finance", "company_admin", "project_manager"].includes(currentUser.role);
    let html = `<div class="card"><h3>${a.asset_name} (${a.asset_number})</h3>
      <p>Assigned to: <strong>${a.assigned_to || "—"}</strong> · Status: ${a.status} · Condition: ${a.condition}</p>
      <p>Cost: ${Number(a.cost||0).toLocaleString()} · NBV: ${Number(a.nbv||0).toLocaleString()} · Life: ${a.useful_life || "—"} yrs</p>
      <p>Debit: ${a.debit_account_label || "—"} · Credit: ${a.credit_account_label || "—"}</p>
      ${a.image_path ? `<img src="${a.image_path}" style="max-width:200px;border-radius:8px;" />` : ""}
      <h4>Accounting entries</h4>
      <ul>${(a.accounting_entries||[]).map(e => `<li>${e.date} ${e.description}: ${e.amount} (${e.journal_entry_no||""})</li>`).join("") || "<li>None yet</li>"}</ul>`;
    if (canFin) {
      html += `<h4>Post value adjustment</h4>
        <div class="form-grid">
          <div class="form-group"><label>Amount (+ increase / − decrease NBV)</label><input id="adj-amt" type="number" step="0.01" /></div>
          <div class="form-group"><label>Description</label><input id="adj-desc" /></div>
          <div class="form-group"><label>Narration</label><input id="adj-narr" /></div>
          <div class="form-group"><label>Debit Account ID</label><input id="adj-debit" type="number" /></div>
          <div class="form-group"><label>Credit Account ID</label><input id="adj-credit" type="number" /></div>
          <div class="form-group"><button class="btn btn-primary" onclick="postAssetAdj(${id})">Post to Ledger</button></div>
        </div>`;
    }
    html += `</div>`;
    document.getElementById("pd-title").textContent = "Asset Detail";
    document.getElementById("pd-body").innerHTML = html;
    document.getElementById("payment-detail-modal").classList.add("open");
  } catch (ex) { alert(ex.message); }
};

window.postAssetAdj = async function (id) {
  const form = new FormData();
  form.append("amount", document.getElementById("adj-amt").value);
  form.append("description", document.getElementById("adj-desc").value);
  form.append("narration", document.getElementById("adj-narr").value);
  form.append("debit_account_id", document.getElementById("adj-debit").value);
  form.append("credit_account_id", document.getElementById("adj-credit").value);
  try {
    const res = await fetch(API + `/api/assets/${id}/accounting`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    alert(data.message + " NBV: " + data.new_nbv);
    openAsset(id);
  } catch (ex) { alert(ex.message); }
};

window.disposeAsset = async function (id) {
  if (!confirm("Mark asset as disposed? It will be auto-deleted after 14 days.")) return;
  try {
    await api(`/api/assets/${id}/dispose`, { method: "POST" });
    loadAssets();
  } catch (ex) { alert(ex.message); }
};

// Patch asset form submit for new fields
document.getElementById("asset-form")?.addEventListener("submit", async (e) => {
  // already has listener - add second is ok for extra fields if first doesn't send them
}, true);

const origAssetSubmit = document.getElementById("asset-form");
if (origAssetSubmit) {
  origAssetSubmit.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/assets", {
        method: "POST",
        body: JSON.stringify({
          asset_number: document.getElementById("ast-number").value,
          asset_name: document.getElementById("ast-name").value,
          category: document.getElementById("ast-cat").value,
          location: document.getElementById("ast-loc").value,
          cost: parseFloat(document.getElementById("ast-cost").value || 0),
          nbv: parseFloat(document.getElementById("ast-nbv").value || 0),
          condition: document.getElementById("ast-cond").value,
          insurance: document.getElementById("ast-ins").value,
          assigned_to: document.getElementById("ast-assigned")?.value || "",
          useful_life: parseFloat(document.getElementById("ast-life")?.value || 0),
          status: document.getElementById("ast-status")?.value || "active",
          debit_account_id: document.getElementById("ast-debit")?.value ? parseInt(document.getElementById("ast-debit").value) : null,
          credit_account_id: document.getElementById("ast-credit")?.value ? parseInt(document.getElementById("ast-credit").value) : null,
        }),
      });
      e.target.reset();
      document.getElementById("asset-form").style.display = "none";
      loadAssets();
    } catch (ex) { alert(ex.message); }
  };
}

/* ---- Inventory ---- */
document.getElementById("btn-add-inv")?.addEventListener("click", () => {
  document.getElementById("inv-form").style.display = "grid";
});
document.getElementById("inv-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  form.append("item_code", document.getElementById("inv-code").value);
  form.append("item_name", document.getElementById("inv-name").value);
  form.append("category", document.getElementById("inv-cat").value);
  form.append("department", document.getElementById("inv-dept").value);
  form.append("cost_price", document.getElementById("inv-cost").value || 0);
  form.append("qty_received", document.getElementById("inv-qty").value || 0);
  if (document.getElementById("inv-debit").value) form.append("debit_account_id", document.getElementById("inv-debit").value);
  if (document.getElementById("inv-credit").value) form.append("credit_account_id", document.getElementById("inv-credit").value);
  try {
    const res = await fetch(API + "/api/inventory", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    e.target.reset();
    document.getElementById("inv-form").style.display = "none";
    loadInventory();
  } catch (ex) { alert(ex.message); }
});

async function loadInventory() {
  try {
    const rows = await api("/api/inventory");
    const tbody = document.querySelector("#inv-table tbody");
    if (!tbody) return;
    tbody.innerHTML = rows.map(i => `<tr>
      <td>${i.item_code}</td><td>${i.item_name}</td><td>${i.category||""}</td>
      <td>${Number(i.cost_price||0).toLocaleString()}</td>
      <td>${i.balance_qty}</td><td>${Number(i.total_value||0).toLocaleString()}</td>
      <td>
        <button class="btn btn-sm btn-success" onclick="invMove(${i.id},'receive')">Receive</button>
        <button class="btn btn-sm btn-outline" onclick="invMove(${i.id},'issue')">Issue</button>
      </td>
    </tr>`).join("");
  } catch (ex) { console.warn(ex); }
}

window.invMove = async function (id, type) {
  const qty = prompt("Quantity:");
  if (!qty) return;
  const form = new FormData();
  form.append("movement_type", type);
  form.append("quantity", qty);
  form.append("narration", type + " stock");
  try {
    const res = await fetch(API + `/api/inventory/${id}/move`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    loadInventory();
  } catch (ex) { alert(ex.message); }
};

/* ---- Vendors ---- */
document.getElementById("btn-add-vendor")?.addEventListener("click", () => {
  document.getElementById("vendor-form").style.display = "grid";
});
document.getElementById("vendor-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  ["ven-no","ven-name","ven-addr","ven-cac","ven-tax","ven-reg","ven-audit","ven-bank","ven-amt","ven-desc","ven-debit","ven-credit"].forEach(() => {});
  form.append("vendor_number", document.getElementById("ven-no").value);
  form.append("name", document.getElementById("ven-name").value);
  form.append("address", document.getElementById("ven-addr").value);
  form.append("cac_number", document.getElementById("ven-cac").value);
  form.append("tax_clearance", document.getElementById("ven-tax").value);
  form.append("reg_with_govt", document.getElementById("ven-reg").value);
  form.append("audit_3yrs", document.getElementById("ven-audit").value);
  form.append("bank", document.getElementById("ven-bank").value);
  form.append("amount", document.getElementById("ven-amt").value || 0);
  form.append("description", document.getElementById("ven-desc").value);
  if (document.getElementById("ven-debit").value) form.append("debit_account_id", document.getElementById("ven-debit").value);
  if (document.getElementById("ven-credit").value) form.append("credit_account_id", document.getElementById("ven-credit").value);
  try {
    const res = await fetch(API + "/api/vendors", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    e.target.reset();
    document.getElementById("vendor-form").style.display = "none";
    loadVendors();
  } catch (ex) { alert(ex.message); }
});

async function loadVendors() {
  try {
    const rows = await api("/api/vendors");
    const tbody = document.querySelector("#vendor-table tbody");
    if (!tbody) return;
    tbody.innerHTML = rows.map(v => `<tr>
      <td>${v.vendor_number}</td><td>${v.name}</td><td>${v.tax_clearance||""}</td>
      <td>${v.score||0}</td><td>${Number(v.amount||0).toLocaleString()}</td>
      <td>${v.bank||""}</td><td>${v.description||""}</td>
    </tr>`).join("");
  } catch (ex) { console.warn(ex); }
}

/* ---- Reports ---- */
document.getElementById("btn-load-tb")?.addEventListener("click", async () => {
  try {
    const d = await api("/api/reports/trial-balance");
    let h = `<table class="data-table"><thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Project</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead><tbody>`;
    (d.rows || []).forEach(r => {
      h += `<tr><td>${r.code}</td><td>${r.name}</td><td>${r.type}</td><td>${r.project_code||""}</td>
        <td>${Number(r.debit).toLocaleString()}</td><td>${Number(r.credit).toLocaleString()}</td>
        <td>${Number(r.balance).toLocaleString()}</td></tr>`;
    });
    h += `</tbody></table><p><strong>Total Debit:</strong> ${Number(d.total_debit).toLocaleString()} ·
      <strong>Total Credit:</strong> ${Number(d.total_credit).toLocaleString()} ·
      <strong>${d.balanced ? "✅ Balanced" : "⚠️ Out of balance"}</strong></p>`;
    document.getElementById("report-output").innerHTML = h;
  } catch (ex) { alert(ex.message); }
});

document.getElementById("btn-load-ledger")?.addEventListener("click", async () => {
  try {
    const rows = await api("/api/reports/ledger");
    let h = `<table class="data-table"><thead><tr><th>Entry</th><th>Date</th><th>Source</th><th>Account</th><th>Description</th><th>Debit</th><th>Credit</th></tr></thead><tbody>`;
    rows.forEach(r => {
      h += `<tr><td>${r.entry_no}</td><td>${r.date}</td><td>${r.source_type}</td><td>${r.account}</td>
        <td>${r.description}</td><td>${Number(r.debit).toLocaleString()}</td><td>${Number(r.credit).toLocaleString()}</td></tr>`;
    });
    h += `</tbody></table>`;
    document.getElementById("report-output").innerHTML = h;
  } catch (ex) { alert(ex.message); }
});

// Wire showView for new pages
const _sv = showView;
showView = function (name) {
  if (name === "inventory") name = "inventory-full";
  if (name === "vendors") name = "vendors-full";
  _sv(name);
  if (name === "inventory-full") loadInventory();
  if (name === "vendors-full") loadVendors();
  if (name === "assets-reg") loadAssets();
  if (name === "reports") { /* wait for button */ }
};


/* Finance journal + bank rec + COA project code */
(function patchCoaForm() {
  const form = document.getElementById("coa-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    try {
      await api("/api/finance/coa", {
        method: "POST",
        body: JSON.stringify({
          code: document.getElementById("coa-code").value,
          name: document.getElementById("coa-name").value,
          account_type: document.getElementById("coa-type").value,
          project_code: document.getElementById("coa-project")?.value || "",
        }),
      });
      form.reset();
      loadFinanceSetup();
    } catch (ex) { alert(ex.message); }
  }, true);
})();

document.getElementById("journal-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  form.append("description", document.getElementById("je-desc").value);
  form.append("narration", document.getElementById("je-narr").value);
  form.append("debit_account_id", document.getElementById("je-debit").value);
  form.append("credit_account_id", document.getElementById("je-credit").value);
  form.append("amount", document.getElementById("je-amt").value);
  if (document.getElementById("je-proj").value) form.append("project_code_id", document.getElementById("je-proj").value);
  try {
    const res = await fetch(API + "/api/finance/journal", {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    alert("Posted: " + data.entry_no);
    e.target.reset();
  } catch (ex) { alert(ex.message); }
});

document.getElementById("btn-load-bank-rec")?.addEventListener("click", async () => {
  try {
    const rows = await api("/api/finance/bank-lines");
    const el = document.getElementById("bank-rec-list");
    if (!rows.length) { el.innerHTML = "<p>No cash ledger lines yet. Post payments or journals first.</p>"; return; }
    el.innerHTML = `<table class="data-table"><thead><tr><th>Tick</th><th>Date</th><th>Entry</th><th>Account</th><th>Description</th><th>Debit</th><th>Credit</th></tr></thead><tbody>
      ${rows.map(r => `<tr>
        <td><input type="checkbox" /></td>
        <td>${r.date}</td><td>${r.entry_no}</td><td>${r.account}</td>
        <td>${r.description||""}</td>
        <td>${Number(r.debit||0).toLocaleString()}</td>
        <td>${Number(r.credit||0).toLocaleString()}</td>
      </tr>`).join("")}
    </tbody></table>`;
  } catch (ex) { alert(ex.message); }
});

// Auto-redirect old stub views
const __sv = showView;
showView = function (name) {
  if (name === "inventory") name = "inventory-full";
  if (name === "assets") name = "assets-reg";
  if (name === "vendors") name = "vendors-full";
  __sv(name);
};

/* ========== Bank recon, variance, module dashboards, auth downloads ========== */

async function authDownload(url, filename) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    let msg = "Download failed";
    try { const j = await res.json(); msg = j.detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename || url.split("/").pop() || "report";
  a.click();
  URL.revokeObjectURL(a.href);
}

document.querySelectorAll("[data-auth-dl]").forEach(a => {
  a.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      const name = a.getAttribute("href").split("/").pop() + (a.getAttribute("href").includes("pdf") ? ".pdf" : ".csv");
      await authDownload(a.href, name);
    } catch (ex) { alert(ex.message); }
  });
});

/* Bank reconciliation */
async function loadBankRecon() {
  const acc = document.getElementById("br-account")?.value || "";
  const sd = document.getElementById("br-start")?.value || "";
  const ed = document.getElementById("br-end")?.value || "";
  let url = "/api/finance/bank-recon?";
  if (acc) url += `account_id=${acc}&`;
  if (sd) url += `start_date=${sd}&`;
  if (ed) url += `end_date=${ed}&`;
  try {
    const data = await api(url);
    const sel = document.getElementById("br-account");
    if (sel && sel.options.length <= 1) {
      (data.cash_accounts || []).forEach(a => {
        const o = document.createElement("option");
        o.value = a.id;
        o.textContent = `${a.code} - ${a.name}`;
        sel.appendChild(o);
      });
    }
    const t = data.totals || {};
    document.getElementById("br-book").value = (t.book_balance || 0).toFixed(2);
    document.getElementById("br-totals").innerHTML = `
      <div class="kpi-card"><div class="kpi-value" style="color:#27AE60">${Number(t.reconciled||0).toLocaleString()}</div><div class="kpi-label">Reconciled</div></div>
      <div class="kpi-card"><div class="kpi-value" style="color:#E74C3C">${Number(t.outstanding||0).toLocaleString()}</div><div class="kpi-label">Outstanding</div></div>
      <div class="kpi-card"><div class="kpi-value">${Number(t.book_balance||0).toLocaleString()}</div><div class="kpi-label">Book Balance</div></div>`;
    const tbody = document.querySelector("#br-table tbody");
    tbody.innerHTML = (data.lines || []).map(L => `<tr>
      <td><input type="checkbox" ${L.ticked ? "checked" : ""} onchange="tickRecon(${L.journal_entry_id}, this.checked)" /></td>
      <td>${L.date}</td>
      <td><a href="#" onclick="openTrail(${L.journal_entry_id});return false;">${L.entry_no}</a></td>
      <td>${L.account}</td>
      <td>${L.description || ""}</td>
      <td>${Number(L.debit||0).toLocaleString()}</td>
      <td>${Number(L.credit||0).toLocaleString()}</td>
      <td>${Number(L.balance||0).toLocaleString()}</td>
      <td><button class="btn btn-sm btn-outline" onclick="openTrail(${L.journal_entry_id})">Trail</button></td>
    </tr>`).join("");
  } catch (ex) { alert(ex.message); }
}

window.tickRecon = async function (jid, ticked) {
  const form = new FormData();
  form.append("journal_entry_id", jid);
  form.append("ticked", ticked ? "true" : "false");
  try {
    const res = await fetch(API + "/api/finance/bank-recon/tick", {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Tick failed");
  } catch (ex) { alert(ex.message); loadBankRecon(); }
};

window.openTrail = async function (jid) {
  try {
    const t = await api(`/api/finance/transaction-trail/${jid}`);
    document.getElementById("trail-panel").style.display = "block";
    const src = t.source ? `<p><strong>Source:</strong> ${t.source.type} ${t.source.ref || ""} — ${t.source.name || t.source.payee || ""} (${t.source.status || ""})</p>` : "<p>No linked source document (manual journal).</p>";
    const pair = (t.paired_entries || []).map(p =>
      `<li>Acct #${p.account_id}: Dr ${p.debit} / Cr ${p.credit} — ${p.description || ""}</li>`
    ).join("");
    document.getElementById("trail-body").innerHTML = `
      <div class="trail-box">
        <p><strong>Entry:</strong> ${t.line.entry_no} · ${t.line.date}</p>
        <p>${t.line.description || ""} — ${t.line.narration || ""}</p>
        <p>Debit: ${t.line.debit} · Credit: ${t.line.credit}</p>
        <p>Created by: ${t.created_by || "—"}</p>
        ${src}
        <h4>Double-entry pair</h4>
        <ul>${pair}</ul>
        ${t.can_correct ? `
          <h4>Request correction</h4>
          <div class="form-grid">
            <div class="form-group"><label>Staff User ID</label><input id="corr-to" type="number" /></div>
            <div class="form-group full-width"><label>Message</label><input id="corr-msg" placeholder="Please correct this entry…" /></div>
            <div class="form-group"><button class="btn btn-sm btn-primary" onclick="sendCorrection(${jid})">Send to staff</button></div>
          </div>` : "<p class="hint">You need finance permission to request corrections.</p>"}
      </div>`;
  } catch (ex) { alert(ex.message); }
};

window.sendCorrection = async function (jid) {
  const form = new FormData();
  form.append("to_user_id", document.getElementById("corr-to").value);
  form.append("message", document.getElementById("corr-msg").value);
  form.append("journal_entry_id", jid);
  try {
    const res = await fetch(API + "/api/finance/correction-request", {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    alert(data.message);
  } catch (ex) { alert(ex.message); }
};

document.getElementById("btn-load-br")?.addEventListener("click", loadBankRecon);

window.loadVariance = async function () {
  document.getElementById("variance-panel").style.display = "block";
  const pc = document.getElementById("var-project")?.value || "";
  try {
    const d = await api("/api/reports/budget-variance" + (pc ? `?project_code=${encodeURIComponent(pc)}` : ""));
    let h = `<table class="data-table"><thead><tr><th>Code</th><th>Description</th><th>Budgeted</th><th>Actual</th><th>Variance</th><th>Remark</th></tr></thead><tbody>`;
    (d.rows || []).forEach(r => {
      h += `<tr><td>${r.budget_code}</td><td>${r.description}</td>
        <td>${Number(r.budgeted).toLocaleString()}</td>
        <td>${Number(r.actual).toLocaleString()}</td>
        <td style="color:${r.variance>=0?"#27AE60":"#E74C3C"}">${Number(r.variance).toLocaleString()}</td>
        <td>${r.remark}</td></tr>`;
    });
    h += `</tbody></table>
      <p><strong>Total Budget:</strong> ${Number(d.total_budget).toLocaleString()} ·
      <strong>Actual:</strong> ${Number(d.total_actual).toLocaleString()} ·
      <strong>Variance:</strong> ${Number(d.total_variance).toLocaleString()}</p>`;
    document.getElementById("variance-out").innerHTML = h;
  } catch (ex) { alert(ex.message); }
};

/* Inventory dashboard */
const _loadInv = loadInventory;
loadInventory = async function () {
  await _loadInv();
  try {
    const rows = await api("/api/inventory");
    const byCat = {};
    let totalVal = 0;
    rows.forEach(i => {
      byCat[i.category || "Other"] = (byCat[i.category || "Other"] || 0) + 1;
      totalVal += i.total_value || 0;
    });
    const k = document.getElementById("inv-kpis");
    if (k) k.innerHTML = `
      <div class="kpi-card"><div class="kpi-value">${rows.length}</div><div class="kpi-label">Items</div></div>
      <div class="kpi-card"><div class="kpi-value">${Number(totalVal).toLocaleString()}</div><div class="kpi-label">Stock Value</div></div>
      <div class="kpi-card"><div class="kpi-value">${Object.keys(byCat).length}</div><div class="kpi-label">Categories</div></div>`;
    if (window.Chart) {
      const c1 = document.getElementById("chart-inv-cat");
      if (c1) {
        if (c1._chart) c1._chart.destroy();
        c1._chart = new Chart(c1, {
          type: "doughnut",
          data: { labels: Object.keys(byCat), datasets: [{ data: Object.values(byCat), backgroundColor: ["#27AE60","#3498DB","#F39C12","#9B59B6","#E74C3C"], borderWidth: 2, borderColor: "#fff" }] },
          options: { plugins: { title: { display: true, text: "Items by Category", font: { weight: "700" } }, legend: { position: "bottom" } }, cutout: "45%" },
        });
      }
      const c2 = document.getElementById("chart-inv-val");
      if (c2) {
        if (c2._chart) c2._chart.destroy();
        const top = rows.slice(0, 8);
        c2._chart = new Chart(c2, {
          type: "bar",
          data: { labels: top.map(i => i.item_code), datasets: [{ label: "Value", data: top.map(i => i.total_value || 0), backgroundColor: "rgba(26,107,154,0.85)", borderRadius: 8 }] },
          options: { plugins: { title: { display: true, text: "Stock Value by Item", font: { weight: "700" } } }, scales: { y: { beginAtZero: true } } },
        });
      }
    }
  } catch (_) {}
};

/* Vendor dashboard */
const _loadVen = loadVendors;
loadVendors = async function () {
  await _loadVen();
  try {
    const rows = await api("/api/vendors");
    const k = document.getElementById("ven-kpis");
    if (k) k.innerHTML = `
      <div class="kpi-card"><div class="kpi-value">${rows.length}</div><div class="kpi-label">Vendors</div></div>
      <div class="kpi-card"><div class="kpi-value">${Number(rows.reduce((s,v)=>s+(v.amount||0),0)).toLocaleString()}</div><div class="kpi-label">Total Commitments</div></div>
      <div class="kpi-card"><div class="kpi-value">${rows.filter(v=>(v.tax_clearance||"").toLowerCase()==="yes").length}</div><div class="kpi-label">Tax Compliant</div></div>`;
    if (window.Chart) {
      const c1 = document.getElementById("chart-ven-score");
      if (c1) {
        if (c1._chart) c1._chart.destroy();
        c1._chart = new Chart(c1, {
          type: "bar",
          data: { labels: rows.map(v => v.vendor_number), datasets: [{ label: "Score", data: rows.map(v => v.score || 0), backgroundColor: "rgba(39,174,96,0.85)", borderRadius: 8 }] },
          options: { plugins: { title: { display: true, text: "Vendor Scores", font: { weight: "700" } } }, scales: { y: { beginAtZero: true, max: 100 } } },
        });
      }
      const c2 = document.getElementById("chart-ven-amt");
      if (c2) {
        if (c2._chart) c2._chart.destroy();
        c2._chart = new Chart(c2, {
          type: "doughnut",
          data: { labels: rows.map(v => v.name), datasets: [{ data: rows.map(v => v.amount || 0), backgroundColor: ["#1A6B9A","#27AE60","#F39C12","#9B59B6","#E74C3C"], borderWidth: 2, borderColor: "#fff" }] },
          options: { plugins: { title: { display: true, text: "Commitment by Vendor", font: { weight: "700" } }, legend: { position: "bottom" } }, cutout: "40%" },
        });
      }
    }
  } catch (_) {}
};

/* Finance dashboard */
async function loadFinanceDash() {
  try {
    const s = await api("/api/dashboard/stats");
    const k = document.getElementById("finance-kpis");
    if (k) k.innerHTML = `
      <div class="kpi-card"><div class="kpi-value">${s.payments_pending ?? 0}</div><div class="kpi-label">Pending Payments</div></div>
      <div class="kpi-card"><div class="kpi-value">${s.payments_paid ?? 0}</div><div class="kpi-label">Paid</div></div>
      <div class="kpi-card"><div class="kpi-value">${Number(s.payments_total_amount||0).toLocaleString()}</div><div class="kpi-label">Paid Amount</div></div>
      <div class="kpi-card"><div class="kpi-value">${s.users_count ?? "—"}</div><div class="kpi-label">Users</div></div>`;
    const pay = s.payment_status_breakdown || {};
    if (window.Chart && document.getElementById("chart-fin-pay")) {
      const c = document.getElementById("chart-fin-pay");
      if (c._chart) c._chart.destroy();
      c._chart = new Chart(c, {
        type: "doughnut",
        data: { labels: Object.keys(pay), datasets: [{ data: Object.values(pay), backgroundColor: ["#F39C12","#3498DB","#9B59B6","#27AE60","#E74C3C"], borderWidth: 2, borderColor: "#fff" }] },
        options: { plugins: { title: { display: true, text: "Payment Status", font: { weight: "700" } }, legend: { position: "bottom" } }, cutout: "45%" },
      });
    }
    try {
      const v = await api("/api/reports/budget-variance");
      const c2 = document.getElementById("chart-fin-budget");
      if (c2 && window.Chart) {
        if (c2._chart) c2._chart.destroy();
        c2._chart = new Chart(c2, {
          type: "bar",
          data: {
            labels: (v.rows || []).map(r => r.budget_code),
            datasets: [
              { label: "Budgeted", data: (v.rows || []).map(r => r.budgeted), backgroundColor: "rgba(26,107,154,0.8)", borderRadius: 6 },
              { label: "Actual", data: (v.rows || []).map(r => r.actual), backgroundColor: "rgba(231,76,60,0.8)", borderRadius: 6 },
            ],
          },
          options: { plugins: { title: { display: true, text: "Budget vs Actual", font: { weight: "700" } } }, scales: { y: { beginAtZero: true } } },
        });
      }
    } catch (_) {}
  } catch (_) {}
}

// Hook showView
const ___sv = showView;
showView = function (name) {
  if (name === "inventory") name = "inventory-full";
  if (name === "assets") name = "assets-reg";
  if (name === "vendors") name = "vendors-full";
  ___sv(name);
  if (name === "bank-recon") loadBankRecon();
  if (name === "finance") loadFinanceDash();
  if (name === "inventory-full") loadInventory();
  if (name === "vendors-full") loadVendors();
};

// Voucher PDF from payment detail
window.downloadVoucher = async function (id) {
  try { await authDownload(`/api/reports/voucher/${id}/pdf`, `voucher_${id}.pdf`); }
  catch (ex) { alert(ex.message); }
};



/* ========== BOOT (must be last) ========== */
(function boot() {
  function goLanding() {
    try {
      hideSplash();
      showPage("landing-page");
      if (typeof showLoginCard === "function") showLoginCard();
    } catch (e) {
      console.error("boot landing", e);
      const s = document.getElementById("splash");
      if (s) s.style.display = "none";
      const lp = document.getElementById("landing-page");
      if (lp) { lp.classList.add("active"); lp.style.display = "block"; }
    }
  }
  async function start() {
    try {
      if (typeof runSplash === "function") {
        await runSplash();
      } else {
        hideSplash();
      }
      if (token && currentUser) {
        try {
          await api("/api/auth/me");
          enterApp();
          return;
        } catch {
          if (typeof logout === "function") logout(false);
        }
      }
      goLanding();
    } catch (e) {
      console.error("boot error", e);
      goLanding();
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
  // Ultimate failsafe
  setTimeout(goLanding, 3500);
})();
