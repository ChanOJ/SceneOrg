/* Frame restore for /domage/ (loaded by its frameset and its inner pages).
 *
 * domage/index.htm is a frameset. A search engine or a bookmark can open an inner page on its own
 * (window.top === window.self): it is then reloaded inside the frameset, with itself in the right
 * frame, through the URL hash "#p=<encoded page URL>" read by the frameset page. A framed page never
 * redirects again (no loop). Same mechanism as the other archived sites, reduced to this one layout.
 */
(function () {
  "use strict";
  var FRAMESET = "/domage/index.htm";
  var FRAME = { "/domage/news.html": "home", "/domage/prods.html": "home", "/domage/members.html": "home",
                "/domage/links.html": "home", "/domage/mod.html": "niksrechts" };

  function norm(p) { return p.replace(/\/{2,}/g, "/").replace(/\/$/, "/index.htm").replace(/index\.html$/, "index.htm").toLowerCase(); }

  var hash = /^#p=(.+)$/.exec(location.hash);
  if (hash) {
    var enc = hash[1], target, a = document.createElement("a");
    try { target = decodeURIComponent(enc); } catch (e) { return; }
    if (!/^\/(?![\/\\])/.test(target)) return;
    a.href = target;
    if (a.protocol !== location.protocol || a.host !== location.host || norm(location.pathname) !== FRAMESET) return;
    var name = FRAME[norm(a.pathname)];
    if (!name) return;
    var apply = function () {
      var el = document.getElementsByName(name)[0];
      if (el) el.src = target;
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply);
    else apply();
  } else if (window.top === window.self && FRAME[norm(location.pathname)]) {
    location.replace(FRAMESET + "#p=" + encodeURIComponent(location.pathname));
  } else if (window.top !== window.self && FRAME[norm(location.pathname)] === "home") {
    // First click or key press in the content frame starts the module that lives in the other frame
    // (browsers block sound before a gesture; mod-player.js exposes startTune).
    var go = function () {
      try { window.parent.frames["niksrechts"].startTune(); } catch (e) { /* not loaded yet */ }
    };
    document.addEventListener("pointerdown", go, { once: true });
    document.addEventListener("keydown", go, { once: true });
  }
})();
