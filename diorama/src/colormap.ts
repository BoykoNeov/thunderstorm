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
