// Cross-section colormaps (slice 5a). The false-color sheet on the cut plane
// is painted in the shader; this TS mirror paints the DOM legend so the two are
// the SAME curve — a legend that disagrees with the image teaches a lie.
//
// viridis: the standard perceptually-uniform map (Nathaniel Smith & Stefan van
// der Walt). Polynomial fit by Matt Zucker — the identical coefficients live in
// shaders.ts `viridis()`. Perceptual uniformity matters here: a rainbow map
// invents banding/structure the data does not have, which would misteach. (The
// dBZ radar layer in 5b deliberately uses a rainbow map instead — there
// recognizability against real radar products IS the teaching goal.)

const C0 = [0.2777273272234177, 0.005407344544966578, 0.3340998053353061];
const C1 = [0.1050930431085774, 1.404613529898575, 1.384590162594685];
const C2 = [-0.3308618287255563, 0.214847559468213, 0.09509516302823659];
const C3 = [-4.634230498983486, -5.799100973351585, -19.33244095627987];
const C4 = [6.228269936347081, 14.17993336680509, 56.69055260068105];
const C5 = [4.776384997670288, -13.74514537774601, -65.35303263337234];
const C6 = [-5.435455855934631, 4.645852612178535, 26.3124352495832];

/** viridis(t), t in [0,1] → [r,g,b] each in [0,1]. Matches the GLSL mirror. */
export function viridis(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  const ch = (i: number) =>
    C0[i] + x * (C1[i] + x * (C2[i] + x * (C3[i] + x * (C4[i] + x * (C5[i] + x * C6[i])))));
  return [
    Math.min(1, Math.max(0, ch(0))),
    Math.min(1, Math.max(0, ch(1))),
    Math.min(1, Math.max(0, ch(2))),
  ];
}

/** A CSS `linear-gradient(...)` stop list sampling the map — for a legend bar. */
export function cssGradientStops(steps = 8): string {
  const parts: string[] = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const [r, g, b] = viridis(t);
    const to255 = (v: number) => Math.round(v * 255);
    parts.push(`rgb(${to255(r)},${to255(g)},${to255(b)}) ${Math.round(t * 100)}%`);
  }
  return parts.join(", ");
}

// -- dBZ radar reflectivity palette (slice 5b) --------------------------------
// Deliberately a RAINBOW map, not perceptually-uniform viridis: recognizability
// against real NWS/NEXRAD radar products IS the teaching goal (the green →
// yellow → red → magenta signature is what a viewer already reads as "a storm on
// radar"). The stops below anchor the recognizable ramp; the GLSL `dbzColor()`
// in shaders.ts interpolates the SAME table so on-screen colour == this legend.
// Units are dBZ; the domain runs from the manifest threshold to vmax.
const DBZ_STOPS: { dbz: number; rgb: [number, number, number] }[] = [
  { dbz: 5, rgb: [0.0, 0.93, 0.93] }, // cyan — lightest detectable echo
  { dbz: 15, rgb: [0.0, 0.0, 0.96] }, // blue
  { dbz: 20, rgb: [0.0, 0.9, 0.0] }, // green — light rain
  { dbz: 35, rgb: [1.0, 1.0, 0.0] }, // yellow — moderate
  { dbz: 45, rgb: [1.0, 0.55, 0.0] }, // orange
  { dbz: 50, rgb: [0.95, 0.0, 0.0] }, // red — heavy core
  { dbz: 60, rgb: [0.7, 0.0, 0.0] }, // dark red
  { dbz: 65, rgb: [1.0, 0.0, 1.0] }, // magenta — hail-sized echo
  { dbz: 72, rgb: [1.0, 1.0, 1.0] }, // white — extreme
];

/** dbzColor(dBZ) → [r,g,b] each in [0,1]. Piecewise-linear over DBZ_STOPS;
 *  clamps below the first / above the last stop. Matches the GLSL mirror. */
export function dbzColor(dbz: number): [number, number, number] {
  if (dbz <= DBZ_STOPS[0].dbz) return DBZ_STOPS[0].rgb;
  const last = DBZ_STOPS[DBZ_STOPS.length - 1];
  if (dbz >= last.dbz) return last.rgb;
  for (let i = 1; i < DBZ_STOPS.length; i++) {
    const b = DBZ_STOPS[i];
    if (dbz <= b.dbz) {
      const a = DBZ_STOPS[i - 1];
      const f = (dbz - a.dbz) / (b.dbz - a.dbz);
      return [
        a.rgb[0] + f * (b.rgb[0] - a.rgb[0]),
        a.rgb[1] + f * (b.rgb[1] - a.rgb[1]),
        a.rgb[2] + f * (b.rgb[2] - a.rgb[2]),
      ];
    }
  }
  return last.rgb;
}

/** GLSL source for the dbzColor ramp — literally the DBZ_STOPS table unrolled
 *  as a running (prev colour, prev dBZ) chain, so the shader and this module's
 *  piecewise-linear interpolation cannot drift. Emitted into shaders.ts. */
export function dbzColorGLSL(): string {
  const c = (rgb: [number, number, number]) => `vec3(${rgb.map((v) => v.toFixed(4)).join(", ")})`;
  const body: string[] = [];
  DBZ_STOPS.forEach((s, i) => {
    if (i === 0) {
      body.push(`  if (d <= ${s.dbz.toFixed(1)}) return ${c(s.rgb)};`);
      body.push(`  vec3 prev = ${c(s.rgb)}; float pd = ${s.dbz.toFixed(1)};`);
    } else {
      const gap = (s.dbz - DBZ_STOPS[i - 1].dbz).toFixed(1);
      body.push(`  if (d <= ${s.dbz.toFixed(1)}) return mix(prev, ${c(s.rgb)}, (d - pd) / ${gap});`);
      body.push(`  prev = ${c(s.rgb)}; pd = ${s.dbz.toFixed(1)};`);
    }
  });
  body.push(`  return prev;`);
  return `vec3 dbzColor(float d) {\n${body.join("\n")}\n}`;
}

/** A CSS gradient stop list for the dBZ legend bar, sampled over [lo, hi] dBZ. */
export function dbzCssGradientStops(lo: number, hi: number, steps = 16): string {
  const parts: string[] = [];
  for (let i = 0; i < steps; i++) {
    const f = i / (steps - 1);
    const [r, g, b] = dbzColor(lo + f * (hi - lo));
    const to255 = (v: number) => Math.round(v * 255);
    parts.push(`rgb(${to255(r)},${to255(g)},${to255(b)}) ${Math.round(f * 100)}%`);
  }
  return parts.join(", ");
}
