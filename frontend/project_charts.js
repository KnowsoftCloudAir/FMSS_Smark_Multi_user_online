/**
 * Project financial analysis charts (Chart.js).
 * Requires Chart.js loaded on the page:
 *   <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
 *
 * Usage:
 *   showProjectAnalysis(projectId)
 * Expects containers:
 *   #proj-budget-chart, #proj-expense-chart, #proj-trend-chart
 *   #proj-analysis-summary
 */
(function () {
  const API = window.API || "";
  let charts = {};

  function money(n, symbol) {
    const s = symbol || "₦";
    return s + " " + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  async function fetchCharts(projectId) {
    const token = localStorage.getItem("km_token");
    const res = await fetch(API + `/api/projects/${projectId}/charts`, {
      headers: { Authorization: "Bearer " + token },
    });
    if (!res.ok) throw new Error("Could not load project charts");
    return res.json();
  }

  async function fetchAnalysis(projectId) {
    const token = localStorage.getItem("km_token");
    const res = await fetch(API + `/api/projects/${projectId}/analysis`, {
      headers: { Authorization: "Bearer " + token },
    });
    if (!res.ok) throw new Error("Could not load analysis");
    return res.json();
  }

  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      delete charts[key];
    }
  }

  window.showProjectAnalysis = async function (projectId) {
    const summary = document.getElementById("proj-analysis-summary");
    if (summary) summary.innerHTML = "Loading analysis…";

    try {
      const [analysis, chartData] = await Promise.all([
        fetchAnalysis(projectId),
        fetchCharts(projectId),
      ]);

      if (summary) {
        const statusColor =
          analysis.status === "over_budget"
            ? "#c0392b"
            : analysis.status === "at_risk"
            ? "#d35400"
            : "#27ae60";
        summary.innerHTML = `
          <div class="proj-kpis">
            <div class="kpi"><span class="kpi-label">Budget</span><strong>${money(analysis.budget_ceiling)}</strong></div>
            <div class="kpi"><span class="kpi-label">Spent</span><strong>${money(analysis.spent)}</strong></div>
            <div class="kpi"><span class="kpi-label">Committed</span><strong>${money(analysis.committed)}</strong></div>
            <div class="kpi"><span class="kpi-label">Remaining</span><strong>${money(analysis.remaining)}</strong></div>
            <div class="kpi"><span class="kpi-label">Burn rate</span><strong>${analysis.burn_rate_pct}%</strong></div>
            <div class="kpi"><span class="kpi-label">Status</span><strong style="color:${statusColor}">${analysis.status.replace("_", " ")}</strong></div>
          </div>
          <p class="hint">${analysis.ifrs_note || ""}</p>
        `;
      }

      if (typeof Chart === "undefined") {
        console.warn("Chart.js not loaded");
        return;
      }

      // Budget vs Actual — bar
      destroyChart("budget");
      const bCtx = document.getElementById("proj-budget-chart");
      if (bCtx) {
        charts.budget = new Chart(bCtx, {
          type: "bar",
          data: {
            labels: chartData.budget_vs_actual.labels,
            datasets: [
              {
                label: "Amount",
                data: chartData.budget_vs_actual.data,
                backgroundColor: ["#3498db", "#e74c3c", "#f39c12", "#2ecc71"],
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false }, title: { display: true, text: "Budget vs Actual" } },
          },
        });
      }

      // Expense breakdown — doughnut
      destroyChart("expense");
      const eCtx = document.getElementById("proj-expense-chart");
      if (eCtx) {
        charts.expense = new Chart(eCtx, {
          type: "doughnut",
          data: {
            labels: chartData.expense_breakdown.labels,
            datasets: [
              {
                data: chartData.expense_breakdown.data,
                backgroundColor: [
                  "#1abc9c", "#3498db", "#9b59b6", "#e67e22", "#e74c3c",
                  "#2ecc71", "#f1c40f", "#34495e", "#16a085", "#2980b9",
                ],
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { title: { display: true, text: "Expense breakdown" } },
          },
        });
      }

      // Monthly trend — line
      destroyChart("trend");
      const tCtx = document.getElementById("proj-trend-chart");
      if (tCtx) {
        charts.trend = new Chart(tCtx, {
          type: "line",
          data: {
            labels: chartData.monthly_trend.labels,
            datasets: [
              {
                label: "Spend",
                data: chartData.monthly_trend.data,
                borderColor: "#2980b9",
                backgroundColor: "rgba(41,128,185,0.15)",
                fill: true,
                tension: 0.3,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { title: { display: true, text: "Monthly spend trend" } },
          },
        });
      }
    } catch (ex) {
      if (summary) summary.innerHTML = `<p style="color:#c00">${ex.message}</p>`;
      console.error(ex);
    }
  };
})();
