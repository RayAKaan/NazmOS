import { WEAVE_HOOK_D, WEAVE_CHEVRON_D } from "./weave";

/**
 * WeaveSprite — mounts the WeaveTile SVG symbols ONCE (hidden) so any component can
 * reference them via `<use href="#weave-hook">` / `<use href="#weave-chevron">`.
 * Render a single <WeaveSprite/> at the app root (see src/app/layout.tsx).
 * §6: one shared sprite, never inline-duplicated per card instance.
 */
export function WeaveSprite() {
  return (
    <svg aria-hidden="true" width="0" height="0" style={{ position: "absolute" }} focusable="false">
      <defs>
        <symbol id="weave-hook" viewBox="0 0 24 24">
          <path d={WEAVE_HOOK_D} fill="none" stroke="currentColor" strokeWidth={2} />
        </symbol>
        <symbol id="weave-chevron" viewBox="0 0 12 12">
          <path d={WEAVE_CHEVRON_D} fill="none" stroke="currentColor" strokeWidth={2} />
        </symbol>
      </defs>
    </svg>
  );
}
