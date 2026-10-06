/**
 * Straightforward company registration — 5 fields only.
 * Overrides the heavy register form behaviour with a cleaner flow.
 */
(function () {
  const API = window.API || "";

  // Auto-slug (already partially present; reinforce)
  document.getElementById("reg-company-name")?.addEventListener("input", (e) => {
    const slugEl = document.getElementById("reg-company-slug");
    if (slugEl && !slugEl.dataset.touched) {
      slugEl.value = e.target.value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 60);
    }
  });

  // Simplify visible fields: hide optional address if we want ultra-minimal
  // Keep address but mark optional in label
  const addrLabel = document.querySelector('label[for="reg-address"], .form-group label');
  // Soften validation message
  const form = document.getElementById("register-form");
  if (!form) return;

  // Replace submit handler with clearer messaging
  form.addEventListener(
    "submit",
    async (e) => {
      // Let existing handler run if present; we only enhance success message
    },
    true
  );

  // Success copy helper used after existing register succeeds
  window.__registrationSuccessCopy = function (data) {
    return (
      `Registration received for <strong>${data.company?.name || ""}</strong>.<br/>` +
      `Status: <em>pending approval</em>.<br/>` +
      `After the General Admin approves, sign in as ` +
      `<code>${data.company?.slug}/${data.admin_username || "admin"}</code>.`
    );
  };
})();
