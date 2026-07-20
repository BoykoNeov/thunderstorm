// Cartographic scale bar for the diorama (slice 5c) — pure, unit-tested.
//
// The design doc (§7) originally asked the scale chip to read "diorama scale
// ≈ 1 : N". In a freely-orbited 3D scene there is no honest single N: it
// changes with every zoom, and deriving one from screen size needs the
// viewer's PHYSICAL display dimensions (the CSS pixel is defined as 1/96 in,
// which is nominal and wrong on most real monitors). A live scale bar carries
// the same teaching payload and stays true at any zoom, so it supersedes the
// ratio — see the design doc's 5c note.
//
// Two honesty constraints shape this module:
//   * Perspective ⇒ the bar is exact only at the look-at point's depth, so it
//     ships with an "at storm centre" caption rather than a whole-image claim.
//   * The storm draws at `?sx`× uniform magnification while the staging land
//     stays 1×, so a single bar cannot describe both. This one describes the
//     STORM: main.ts divides scene-km by the storm scale before calling in.

export interface ScaleBar {
  /** the round distance the bar spans, in real storm kilometres */
  km: number;
  /** how long to draw it, in CSS pixels */
  px: number;
  /** human label, e.g. "10 km" or "500 m" */
  label: string;
}

/** 1-2-5 ladder — the standard map-scale mantissas. */
const MANTISSAS = [1, 2, 5];

const format = (km: number): string =>
  km >= 1 ? `${Math.round(km)} km` : `${Math.round(km * 1000)} m`;

/**
 * Largest 1-2-5-ladder distance that fits within `maxPx` at this zoom.
 *
 * Choosing the bar length (rather than fixing the pixel width and printing
 * whatever odd number it works out to) is what keeps the label readable: the
 * bar breathes as you zoom, the number stays round.
 */
export function niceScaleBar(kmPerPx: number, maxPx: number): ScaleBar {
  if (!(kmPerPx > 0) || !(maxPx > 0) || !Number.isFinite(kmPerPx)) {
    return { km: 0, px: 0, label: "" };
  }
  const maxKm = kmPerPx * maxPx;
  const exp = Math.floor(Math.log10(maxKm));
  // 10^exp ≤ maxKm by construction, so `best` always starts valid.
  let best = 10 ** exp;
  for (const m of MANTISSAS) {
    const v = m * 10 ** exp;
    if (v <= maxKm && v > best) best = v;
  }
  return { km: best, px: best / kmPerPx, label: format(best) };
}
