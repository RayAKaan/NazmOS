/**
 * §3 WeaveTile geometry — Gulf shemagh hook motif, abstracted (never the black-and-white
 * Palestinian keffiyeh pattern; see brief §1). Single source for both the live `<use>`
 * symbol (WeaveSprite) and the CSS-mask data-URI background (§6 perf: no per-instance
 * inline SVG bloat, no DOM grid of `<use>` elements).
 *
 * Geometry is direction-agnostic (symmetric hook / chevron), so RTL needs no mirroring (§7).
 */

/** Hook motif: two 90° arcs forming a rotated "S" — 2px stroke, no fill, centered in 24×24. */
export const WEAVE_HOOK_D = "M 12 4 C 19 4 19 12 12 12 C 5 12 5 20 12 20";

/** Chevron border motif: single zigzag, 2px, 45°/-45° alternating, 12px period. */
export const WEAVE_CHEVRON_D = "M 0 3 L 6 9 L 12 3";

/**
 * 24×48 field tile (two rows): odd row hook +45°, even row -45° → woven-cross illusion
 * without literal fabric texture. `stroke="black"` only feeds the mask's alpha channel —
 * the real colour comes from CSS `--weave-accent` via `background-color`, never baked in.
 */
const FIELD_MASK_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="48" viewBox="0 0 24 48">' +
  '<g fill="none" stroke="black" stroke-width="2">' +
  `<path transform="rotate(45 12 12)" d="${WEAVE_HOOK_D}"/>` +
  `<path transform="translate(0 24) rotate(-45 12 12)" d="${WEAVE_HOOK_D}"/>` +
  "</g></svg>";

/** Chevron tile (12×12) for ChevronDivider, as a mask data-URI. */
const CHEVRON_MASK_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">' +
  `<g fill="none" stroke="black" stroke-width="2"><path d="${WEAVE_CHEVRON_D}"/></g></svg>`;

function svgToDataUri(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

/** CSS `url("data:image/svg+xml,...")` mask for the full-bleed field pattern. */
export const WEAVE_FIELD_MASK_URL = `url("${svgToDataUri(FIELD_MASK_SVG)}")`;

/** CSS mask URL for the repeating chevron divider tile. */
export const WEAVE_CHEVRON_MASK_URL = `url("${svgToDataUri(CHEVRON_MASK_SVG)}")`;

/** §3 colour → CSS variable mapping (inherits the theme, never hardcoded per instance). */
export function weaveAccent(color: "gold" | "teal"): string {
  return color === "teal" ? "var(--weave-accent-teal)" : "var(--weave-accent)";
}
