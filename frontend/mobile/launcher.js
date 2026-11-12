// Banana English Android launcher: check the server, then open it in this WebView.
// The server URL comes from the build (config.js, BANANA_APP_URL) or from the learner, and is
// remembered on the phone. Only https:// is accepted (Android blocks cleartext traffic).
(function () {
  "use strict";
  var KEY = "banana-server-url";
  var TIMEOUT_MS = 10000;
  var $ = function (id) { return document.getElementById(id); };

  function normalize(value) {
    var text = String(value || "").trim();
    if (!text) return null;
    if (!/^[a-z]+:\/\//i.test(text)) text = "https://" + text;
    try {
      var url = new URL(text);
      if (url.protocol !== "https:") return null;
      return url.origin; // the app lives at the root of the server
    } catch (e) {
      return null;
    }
  }

  function stored() {
    try { return normalize(localStorage.getItem(KEY)); } catch (e) { return null; }
  }

  function remember(url) {
    try { localStorage.setItem(KEY, url); } catch (e) { /* private storage off: still works */ }
  }

  // Is the server up? The native HTTP plugin reads the status (no CORS); a plain no-cors fetch
  // only tells whether the host answers at all.
  function reachable(url) {
    var probe = url + "/api/v1/features";
    var http = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.CapacitorHttp;
    var check = http
      ? http.get({ url: probe, connectTimeout: TIMEOUT_MS, readTimeout: TIMEOUT_MS })
          .then(function (r) { return r.status >= 200 && r.status < 500; })
      : fetch(probe, { mode: "no-cors", cache: "no-store" }).then(function () { return true; });
    var timeout = new Promise(function (resolve) { setTimeout(function () { resolve(false); }, TIMEOUT_MS + 500); });
    return Promise.race([check, timeout]).catch(function () { return false; });
  }

  function showSetup(message, value) {
    $("connecting").hidden = true;
    $("setup").hidden = false;
    $("url").value = value || "";
    $("error").hidden = !message;
    $("error").textContent = message || "";
    $("url").focus();
  }

  var cancelled = false;
  function connect(url) {
    cancelled = false;
    $("setup").hidden = true;
    $("connecting").hidden = false;
    $("host").textContent = new URL(url).host;
    reachable(url).then(function (ok) {
      if (cancelled) return;
      if (ok) {
        remember(url);
        window.location.replace(url + "/");
      } else {
        showSetup("Cannot reach " + new URL(url).host + ". Check the address, or that the server is running.", url);
      }
    });
  }

  $("change").addEventListener("click", function () {
    cancelled = true;
    showSetup("", stored() || window.BANANA_APP_URL || "");
  });

  $("setup").addEventListener("submit", function (event) {
    event.preventDefault();
    var url = normalize($("url").value);
    if (!url) {
      showSetup("Enter an address that starts with https://", $("url").value);
      return;
    }
    connect(url);
  });

  // A new build with a new server URL wins over the one remembered from the previous build
  // (e.g. the quick tunnel replaced by a fixed link); a URL the learner typed is kept otherwise.
  var built = normalize(window.BANANA_APP_URL);
  try {
    if (built && localStorage.getItem("banana-built-url") !== built) {
      localStorage.setItem("banana-built-url", built);
      localStorage.removeItem(KEY);
    }
  } catch (e) { /* storage off: the built URL is used */ }
  var initial = stored() || built;
  if (initial) connect(initial);
  else showSetup("", "");
})();
