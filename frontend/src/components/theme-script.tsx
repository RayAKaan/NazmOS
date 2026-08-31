// Full theme control (System / Light / Dark) applied pre-hydration so there is no flash
// of the wrong theme. Mirrors the ThemeToggle's persisted contract via `nazmos-theme`
// ("light" | "dark" | "system"). System mode reacts live to OS preference changes.
// Also applies the `arabic-font` class whenever the doc is RTL so IBM Plex Sans Arabic
// is used for Arabic text (it is swapped into the body stack in globals.css).
const THEME_SNIPPET = `(function(){
  try {
    function applyTheme(mode){
      var m = mode || "system";
      var dark = m === "dark" || (m === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.classList.toggle("dark", dark);
    }
    var stored = null;
    try { stored = localStorage.getItem("nazmos-theme"); } catch(e){}
    applyTheme(stored);
    if (stored === "system" || stored === null) {
      if (window.matchMedia) {
        window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function(e){
          if (localStorage.getItem("nazmos-theme") === "system") { applyTheme("system"); }
        });
      }
    }
    if (document.documentElement.lang === "ar") { document.documentElement.classList.add("arabic-font"); }
  } catch(e){}
})();`;

export function ThemeScript() {
  // Inline <script> (not next/script) so it runs synchronously in <head> before first paint,
  // matching the existing locale script in layout.tsx and avoiding any theme flash.
  return <script id="theme-script" dangerouslySetInnerHTML={{ __html: THEME_SNIPPET }} />;
}
