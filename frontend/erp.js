async function erpFetch(path, options = {}) {
  const headers = Object.assign({ Authorization: "Bearer " + ((localStorage.getItem("km_token")||localStorage.getItem("token")) || "") }, options.headers || {});
  const res = await fetch(path, Object.assign({}, options, { headers }));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

document.getElementById("switch-to-owner")?.addEventListener("click", (e) => {
  e.preventDefault();
  document.getElementById("login-card").style.display = "none";
  document.getElementById("register-card").style.display = "none";
  document.getElementById("owner-card").style.display = "block";
});
document.getElementById("switch-owner-login")?.addEventListener("click", (e) => {
  e.preventDefault();
  document.getElementById("owner-card").style.display = "none";
  document.getElementById("login-card").style.display = "block";
});
document.getElementById("owner-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("owner-error");
  err.style.display = "none";
  const body = new URLSearchParams();
  body.set("username", document.getElementById("owner-username").value.trim());
  body.set("password", document.getElementById("owner-password").value);
  const res = await fetch("/api/auth/login", { method: "POST", body });
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.detail || "Owner login failed";
    err.style.display = "block";
    return;
  }
  localStorage.setItem("km_token", data.access_token);
  localStorage.setItem("km_user", JSON.stringify(data.user));
  /* stay on page; general_admin.js / app.js enterApp handles navigation */
if (typeof enterApp === "function" && window.currentUser) enterApp();
else location.reload();
});

async function loadCurrencyBoard() {
  const el = document.getElementById("currency-board");
  if (!el || !(localStorage.getItem("km_token")||localStorage.getItem("token"))) return;
  try {
    const data = await erpFetch("/api/erp/currencies");
    const rates = data.rates.map((r) => `<tr><td>${r.base}</td><td>${r.quote}</td><td>${r.rate}</td><td>${r.date}</td></tr>`).join("");
    el.innerHTML = `<p>${data.currencies.map((c) => c.code + " " + c.symbol).join(" · ")}</p>
      <table class="data-table"><thead><tr><th>From</th><th>To</th><th>Rate</th><th>Date</th></tr></thead><tbody>${rates}</tbody></table>`;
  } catch (ex) {
    el.innerHTML = `<p class="hint">${ex.message}</p>`;
  }
}

async function loadTaskBoard() {
  const el = document.getElementById("task-board");
  if (!el || !(localStorage.getItem("km_token")||localStorage.getItem("token"))) return;
  try {
    const rows = await erpFetch("/api/erp/tasks");
    el.innerHTML = `<table class="data-table"><thead><tr><th>Task</th><th>Status</th><th>Tries</th><th></th></tr></thead><tbody>${
      rows.map((t) => `<tr><td>${t.title}</td><td>${t.status}</td><td>${t.attempts}</td><td>
        <button class="btn btn-sm" onclick="actTask(${t.id}, 'start')">Start</button>
        <button class="btn btn-sm" onclick="actTask(${t.id}, 'complete')">Complete</button>
        <button class="btn btn-sm" onclick="actTask(${t.id}, 'retry')">Retry</button>
      </td></tr>`).join("")
    }</tbody></table>`;
  } catch (ex) {
    el.innerHTML = `<p class="hint">${ex.message}</p>`;
  }
}

async function actTask(id, action) {
  try {
    await erpFetch(`/api/erp/tasks/${id}/act`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    loadTaskBoard();
  } catch (ex) {
    alert(ex.message);
  }
}

const _show = window.showView;
window.showView = function (name) {
  if (typeof _show === "function") _show(name);
  if (name === "currency") loadCurrencyBoard();
  if (name === "tasks") loadTaskBoard();
};
