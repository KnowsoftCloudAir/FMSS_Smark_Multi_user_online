// FMS Smart — PWA registration
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function (e) {
        console.warn("SW register failed", e);
      });
    });
  }
  // Install prompt helper
  let deferred;
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferred = e;
    var btn = document.getElementById("installBtn");
    if (btn) btn.style.display = "inline-block";
  });
  window.fmsInstall = function () {
    if (!deferred) return;
    deferred.prompt();
    deferred.userChoice.finally(function () { deferred = null; });
  };
})();
