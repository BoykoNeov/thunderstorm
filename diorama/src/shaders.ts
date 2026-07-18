// GLSL, three passes (slice 3):
//   1. G-pass — rasterize the low-poly staging mesh (land/water/base wall)
//      into albedo+material, flat normal, and a real depth buffer.
//   2. Composite — fullscreen raymarch of the storm volume over the staging:
//      surface pixels are shaded here (so the storm's shadow march darkens
//      the toy landscape), background is a real horizon (dark storm sky over
//      an infinite sea, the slab floating above it), then tone map.
//   3. Tilt-shift — separable variable-radius blur keyed to a horizontal
//      focus band + a light toy grade (the classic miniature cue).
//
// Volume lighting model (design doc §5.1): single scattering with a real
// secondary march toward the sun at every primary sample (self-shadowing),
// dual-lobe Henyey–Greenstein phase, a height-graded ambient term so shadowed
// bases read blue-grey rather than black, and a "powder" darkening at dense
// cores. Extinction is physical-per-species: the four RGBA planes decode back
// to mixing ratios (kg/kg) and combine with per-species weights — the same
// weights the UE material uses (docs/phase1-svt-custom-material-2026-07-16.md).
//
// Two presentation layers on top of the data (never physics — they modulate
// how the 250 m field LOOKS, not what it says):
//  - detail erosion: tileable value noise erodes the cloud EDGE extinction,
//    adding sub-voxel structure the grid can't carry — without it trilinear
//    sampling shows the voxel lattice as smooth blocky facets. Cores are
//    untouched (erosion weight → 0 with density), so opacity/shape hold.
//  - rain veil: the rain channel is split out of the cloud sum and rendered
//    as a darker translucent curtain, modulated by vertically-stretched noise
//    scrolling downward — the "gray sheets of distant rain" read. The streak
//    particles (pass 2.5) stay; the veil is what distance actually looks like.

export const VERT = `#version 300 es
void main() {
  float x = float((gl_VertexID << 1) & 2);
  float y = float(gl_VertexID & 2);
  gl_Position = vec4(x * 2.0 - 1.0, y * 2.0 - 1.0, 0.0, 1.0);
}
`;

// -- pass 1: staging-mesh G-pass ---------------------------------------------

export const GEO_VERT = `#version 300 es
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec3 aColor;
layout(location = 3) in float aMat;

uniform mat4 uViewProj;

out vec3 vNormal;
out vec3 vColor;
flat out float vMat;

void main() {
  vNormal = aNormal;
  vColor = aColor;
  vMat = aMat;
  gl_Position = uViewProj * vec4(aPos, 1.0);
}
`;

export const GEO_FRAG = `#version 300 es
precision highp float;

in vec3 vNormal;
in vec3 vColor;
flat in float vMat;

layout(location = 0) out vec4 oAlbedo; // rgb albedo, a = material (0 land, 1 water)
layout(location = 1) out vec4 oNormal; // flat face normal, packed *0.5+0.5

void main() {
  oAlbedo = vec4(vColor, vMat);
  oNormal = vec4(normalize(vNormal) * 0.5 + 0.5, 1.0);
}
`;

// -- shared volume-sampling chunk ----------------------------------------------
// Uniform declarations + decode/extinction/occlusion marches, interpolated into
// BOTH the composite fragment shader and the precipitation vertex shader (which
// gates particle spawn on the same resident 3D textures). One definition, one
// set of uniform names — main.ts sets them per program.

const VOL_COMMON = `
uniform vec3  uSunDir;        // unit, toward the sun
uniform vec3  uCamPos;
uniform vec3  uBoxMin;        // volume bounds, km (display scale pre-applied)
uniform vec3  uBoxMax;
uniform sampler3D uVolA;      // frame i0
uniform sampler3D uVolB;      // frame i1 (temporal crossfade partner)
uniform float uMix;           // fractional storm time between the two frames
uniform vec4  uThr;           // per-plane decode: q = thr * exp(k * (v255 - 1))
uniform vec4  uK;
uniform vec4  uWeights;       // per-species extinction weights
uniform float uExtScale;      // km^-1 per weighted (kg/kg)
uniform float uShadowKm;      // sun-march occluder cap, km (scales with sx)

const float PI = 3.14159265;

vec2 rayBox(vec3 ro, vec3 rd, vec3 bmin, vec3 bmax) {
  vec3 inv = 1.0 / rd;
  vec3 a = (bmin - ro) * inv;
  vec3 b = (bmax - ro) * inv;
  vec3 lo = min(a, b), hi = max(a, b);
  return vec2(max(max(lo.x, lo.y), lo.z), min(min(hi.x, hi.y), hi.z));
}

// decode log-uint8 codes back to mixing ratios; codes < ~0.5 are "empty"
vec4 qDecode(vec4 v255) {
  return uThr * exp(uK * (v255 - 1.0)) * step(0.5, v255);
}

float sigmaAt(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  // temporal crossfade: decode each frame, then mix — mixing ratios are
  // linear quantities, so the blend happens in q space, not code space
  vec4 q = qDecode(texture(uVolA, uvw) * 255.0);
  if (uMix > 0.0001) {
    q = mix(q, qDecode(texture(uVolB, uvw) * 255.0), uMix);
  }
  float sig = uExtScale * dot(uWeights, q);
  // trim the faint decode halo so edges stay cloud, not fog (keeps the anvil:
  // its sigma is well above this floor)
  return max(sig - 0.04, 0.0);
}

// Shadow-march sampling skips the crossfade and reads the nearest frame:
// self-shadow differences between two adjacent 12 s frames are imperceptible,
// and the ~28 secondary samples per primary sample dominate fetch cost —
// single-fetch here nearly halves the whole march during playback.
float sigmaShadowAt(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  vec4 v = (uMix < 0.5 ? texture(uVolA, uvw) : texture(uVolB, uvw)) * 255.0;
  float sig = uExtScale * dot(uWeights, qDecode(v));
  return max(sig - 0.04, 0.0);
}

float sunTau(vec3 p) {
  vec2 tb = rayBox(p, uSunDir, uBoxMin, uBoxMax);
  // ~15 km of occluder (× display scale) is plenty — capping it keeps the
  // steps dense where the shadow forms instead of across the whole box.
  float end = min(max(tb.y, 0.0), uShadowKm);
  const int M = 28;
  float ds = end / float(M);
  float tau = 0.0;
  float s = ds * 0.5;
  for (int i = 0; i < M; i++) {
    tau += sigmaShadowAt(p + uSunDir * s) * ds;
    if (tau > 9.0) break;
    s += ds;
  }
  return tau;
}

// Coarse directional optical depth for the particle pass (per-vertex budget:
// a handful of steps, nearest-frame sampling — tint/attenuation, not imagery).
float tauDir(vec3 p, vec3 dir, float maxKm, int steps) {
  vec2 tb = rayBox(p, dir, uBoxMin, uBoxMax);
  float end = min(max(tb.y, 0.0), maxKm);
  float ds = end / float(steps);
  float tau = 0.0;
  float s = ds * 0.5;
  for (int i = 0; i < 16; i++) {
    if (i >= steps) break;
    tau += sigmaShadowAt(p + dir * s) * ds;
    if (tau > 9.0) break;
    s += ds;
  }
  return tau;
}

uniform sampler3D uShadowA;   // baked sun transmittance, frame i0 (unit 6)
uniform sampler3D uShadowB;   // frame i1 (unit 7)
uniform float uUseCache;      // ?lc=0 falls back to the live march

// Sun transmittance at p — one fetch from the baked cache, nearest frame
// (exactly the sigmaShadowAt policy: crossfading shadows is imperceptible).
// Points OUTSIDE the box advance to the sun ray's box entry: the cache voxel
// there already integrates the remaining path to the sun. Rays that miss the
// box are unshadowed.
float sunTrans(vec3 p) {
  if (uUseCache < 0.5) return exp(-sunTau(p));
  vec2 tb = rayBox(p, uSunDir, uBoxMin, uBoxMax);
  if (tb.y <= max(tb.x, 0.0)) return 1.0;
  vec3 q = p + uSunDir * max(tb.x, 0.0);
  vec3 uvw = clamp((q - uBoxMin) / (uBoxMax - uBoxMin), 0.0, 1.0);
  return uMix < 0.5 ? texture(uShadowA, uvw).r : texture(uShadowB, uvw).r;
}
`;

// -- pass 0 (upload-time): sun-transmittance bake ------------------------------
// One fullscreen draw per z-slice of the cache; framebufferTextureLayer selects
// the slice. Runs once per brick upload — never per rendered frame. Reuses
// VOL_COMMON; uMix defaults to 0 so sunTau's sigmaShadowAt reads only uVolA
// (the brick being baked).
export const BAKE_FRAG = `#version 300 es
precision highp float;
precision highp sampler3D;
out vec4 fragColor;
uniform vec2  uCacheXY;  // cache slice resolution, texels
uniform float uSliceZ;   // normalized z of this slice's texel centers
${VOL_COMMON}
void main() {
  vec3 uvw = vec3(gl_FragCoord.xy / uCacheXY, uSliceZ);
  vec3 p = mix(uBoxMin, uBoxMax, uvw);
  fragColor = vec4(exp(-sunTau(p)), 0.0, 0.0, 1.0);
}
`;

// -- pass 2: volume raymarch + surface shading + background --------------------

export const FRAG = `#version 300 es
precision highp float;
precision highp sampler3D;

out vec4 fragColor;

uniform vec2  uRes;
uniform vec3  uCamRight;
uniform vec3  uCamUp;
uniform vec3  uCamFwd;
uniform float uFovTan;        // tan(fovY/2)

uniform sampler2D uAlbedo;    // g-buffer: staging albedo + material flag
uniform sampler2D uNormalTex; // g-buffer: flat face normal
uniform sampler2D uDepthTex;  // g-buffer: depth (ray-distance reconstruction)
uniform float uNear;
uniform float uFar;
uniform float uTime;          // wall seconds — water ripple only, never physics

uniform float uSteps;         // primary march step count
uniform float uExposure;

uniform sampler3D uNoise;     // tileable RG value noise (R coarse, G fine)
uniform vec3  uSizeStorm;     // box size in storm km (display / sx) — noise coords
uniform float uErosion;       // 0..1 edge erosion strength (?er=)
uniform float uMsW;           // multi-scatter octave weight (?msw=0 → single scatter)
uniform float uMsA;           // per-octave optical-depth attenuation (?msa=)
uniform float uSilver;        // silver-lining forward-spike weight (?silver=0 off)
uniform float uCoreNorm;      // sigma → "coreness"; scales with sx so the same
                              // cloud erodes identically at any display scale
uniform vec4  uWeightsCld;    // uWeights with the rain plane zeroed
uniform vec4  uRainVeil;      // one-hot rain plane × veil extinction weight (?veil=)
${VOL_COMMON}
// -- palette (placeholder; owner tunes by eye) ---------------------------------
const vec3 SUN_COL      = vec3(1.00, 0.95, 0.87) * 3.6;
// NOTE: these are pre-tonemap linear values — ACES + gamma lifts them a lot,
// so "dark" here must be numerically much smaller than the target screen grey
const vec3 BG_TOP       = vec3(0.035, 0.045, 0.075); // dark slate zenith — storm sky
const vec3 BG_HAZE      = vec3(0.10, 0.11, 0.13);    // dark-grey horizon haze band
const vec3 SEA_DEEP     = vec3(0.02, 0.05, 0.08);    // open sea under the slab
const float SEA_Z       = -6.0;                    // km; below the slab bottom
const vec3 AMB_HIGH     = vec3(0.38, 0.48, 0.60);  // sky light on upper cloud
const vec3 AMB_LOW      = vec3(0.14, 0.17, 0.22);  // bounce light near base
const vec3 CLOUD_ALB    = vec3(0.93, 0.94, 0.96);
const vec3 RAIN_ALB     = vec3(0.55, 0.60, 0.68);  // veil: darker, cooler

// Extinction split for the primary march: x = cloud/ice/graupel de-blocked by
// noise (domain warp + edge modulation), y = rain veil with falling-sheet
// modulation. The shadow marches keep the plain sigmaShadowAt — noise there
// costs 28× per sample and self-shadow differences are imperceptible.
vec2 sigma2At(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  vec3 pS = uvw * uSizeStorm;
  // Domain warp — THE de-blocking step: bend the sample position with smooth
  // vector noise (~2 km wavelength, ~1.5-voxel amplitude) so the trilinear
  // iso-surfaces stop being voxel-aligned. Magnitude modulation alone cannot
  // remove the lattice facets/striping; moving the lookup can. The fine
  // octave rides along for the edge wisps below.
  float nFine = 0.5;
  if (uErosion > 0.001) {
    vec3 c = pS * 0.125;
    vec2 nA = texture(uNoise, c).rg;
    float ny = texture(uNoise, c + vec3(0.37, 0.71, 0.19)).r;
    float nz = texture(uNoise, c + vec3(0.61, 0.13, 0.47)).r;
    nFine = nA.g;
    vec3 warp = (vec3(nA.r, ny, nz) - 0.5) * (uErosion * 1.7);
    uvw += warp / uSizeStorm;
  }
  vec4 q = qDecode(texture(uVolA, uvw) * 255.0);
  if (uMix > 0.0001) {
    q = mix(q, qDecode(texture(uVolB, uvw) * 255.0), uMix);
  }
  float sigC = max(uExtScale * dot(uWeightsCld, q) - 0.04, 0.0);
  if (sigC > 1e-4) {
    // near-zero-mean wisp modulation at cloud edges, fading out in cores —
    // NOT a subtractive erode: that deletes thin extended features (the anvil
    // is optically thin everywhere and vanished under it)
    float core = min(sigC * uCoreNorm, 1.0);
    float e = uErosion * (1.0 - core);
    if (e > 0.001) {
      sigC *= max(1.0 + e * (2.2 * nFine - 1.25), 0.0);
    }
  }
  float sigR = uExtScale * dot(uRainVeil, q);
  if (sigR > 1e-4) {
    // vertically-stretched sheets, scrolling down on wall time (presentation,
    // like the water ripples — storm time at 300× would strobe)
    float v = texture(uNoise, vec3(pS.xy * 0.33, pS.z * 0.07 + uTime * 0.05)).r;
    sigR *= 0.15 + 1.7 * v * v; // squared: crisper sheet/gap contrast
  }
  return vec2(sigC, sigR);
}

float hg(float c, float g) {
  float g2 = g * g;
  return (1.0 - g2) / (4.0 * PI * pow(1.0 + g2 - 2.0 * g * c, 1.5));
}

// -- background: a real horizon — dark storm sky over an infinite sea ----------
// The sea plane sits below the slab bottom, so the diorama still reads as a
// floating slab; distance fog pulls the sea into the haze band exactly at
// rd.z = 0, so sky and sea meet seamlessly at the horizon line.
vec3 background(vec3 rd) {
  float s = max(dot(rd, uSunDir), 0.0);
  if (rd.z >= 0.0) {
    // tight gradient: the default view only sees a few degrees of sky, so the
    // dark zenith has to arrive fast or the whole strip reads as flat haze
    vec3 col = mix(BG_HAZE, BG_TOP, pow(smoothstep(0.0, 0.22, rd.z), 0.8));
    col += vec3(1.0, 0.9, 0.75) * pow(s, 9.0) * 0.07; // warm cast, no sun disc
    return col;
  }
  float t = (SEA_Z - uCamPos.z) / rd.z; // camera is always above the sea plane
  // fog is capped below 1 so the sea keeps some colour at grazing angles —
  // that residual is what draws the horizon line (fully honest fog erases it)
  float fog = (1.0 - exp(-t * 0.0025)) * 0.78;
  vec3 rr = vec3(rd.x, rd.y, -rd.z);    // mirror off the flat sea
  vec3 sea = SEA_DEEP + SUN_COL * pow(max(dot(rr, uSunDir), 0.0), 60.0) * 0.05;
  return mix(sea, BG_HAZE, fog);
}

// -- staging surface ------------------------------------------------------------
// big soft toy-scale ripples; analytic gradient of a few sine waves (km, wall s)
vec2 waveGrad(vec2 xy) {
  float t = uTime * 0.8;
  vec2 g = vec2(0.0);
  g += cos(dot(xy, vec2(5.1, 1.6)) + t * 1.3) * vec2(5.1, 1.6) * 0.0050;
  g += cos(dot(xy, vec2(-3.7, 4.4)) + t * 1.7) * vec2(-3.7, 4.4) * 0.0035;
  g += cos(dot(xy, vec2(1.8, -7.1)) + t * 2.3) * vec2(1.8, -7.1) * 0.0022;
  return g;
}

vec3 shadeSurface(vec2 uv, vec3 p, vec3 rd) {
  vec4 galb = texture(uAlbedo, uv);
  vec3 n = normalize(texture(uNormalTex, uv).xyz * 2.0 - 1.0);
  // the storm's shadow sweeping the toy landscape — the miniature illusion's
  // highest-value effect (design doc §5.2)
  float shadow = sunTrans(p);
  if (galb.a > 0.5) {
    // water: rippled normal, fresnel reflection of the backdrop, sun glint;
    // ripples fade with camera distance so they never moiré at long range
    vec2 g = waveGrad(p.xy) * clamp(50.0 / length(p - uCamPos), 0.25, 1.0);
    n = normalize(vec3(-g.x, -g.y, 1.0));
    vec3 rr = reflect(rd, n);
    rr.z = abs(rr.z);
    float fres = 0.04 + 0.4 * pow(1.0 - max(dot(n, -rd), 0.0), 5.0);
    vec3 col = galb.rgb * (SUN_COL * (0.32 * max(dot(n, uSunDir), 0.0) * shadow) + AMB_HIGH * 0.5);
    col = mix(col, background(rr), fres);
    float glint = pow(max(dot(rr, uSunDir), 0.0), 100.0);
    col += SUN_COL * glint * shadow * 0.2;
    return col;
  }
  // land / base wall: flat-shaded lambert + hemispheric ambient
  float ndl = max(dot(n, uSunDir), 0.0);
  vec3 amb = mix(AMB_LOW, AMB_HIGH, n.z * 0.5 + 0.5) * 0.6;
  return galb.rgb * (SUN_COL * (ndl * shadow) * 0.36 + amb);
}

float hash12(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 ndc = uv * 2.0 - 1.0;
  ndc.x *= uRes.x / uRes.y;
  vec3 rd = normalize(uCamFwd + uFovTan * (ndc.x * uCamRight + ndc.y * uCamUp));
  vec3 ro = uCamPos;

  // staging surface from the g-buffer depth (d = 1 means backdrop); the
  // reconstruction (depth → eye z → ray distance) mirrors mat.ts, tested
  float d = texture(uDepthTex, uv).r;
  float tSurf = 1e9;
  vec3 bg;
  if (d < 1.0) {
    float ndcz = 2.0 * d - 1.0;
    float ze = (2.0 * uNear * uFar) / (uFar + uNear - ndcz * (uFar - uNear));
    tSurf = ze / dot(rd, uCamFwd);
    bg = shadeSurface(uv, ro + rd * tSurf, rd);
  } else {
    bg = background(rd);
  }

  // volume interval, clipped by the staging surface
  vec2 tb = rayBox(ro, rd, uBoxMin, uBoxMax);
  float t0 = max(tb.x, 0.0);
  float t1 = min(tb.y, tSurf);

  vec3 acc = vec3(0.0);
  float T = 1.0;
  if (t1 > t0) {
    float N = uSteps;
    float dt = (t1 - t0) / N;
    float t = t0 + dt * hash12(gl_FragCoord.xy);
    float cosSun = dot(rd, uSunDir);
    // multi-scatter octaves (Wrenninge-style): octave i sees optical depth
    // scaled by uMsA^i (pow of the cached transmittance) and phase eccentricity
    // scaled by MS_B^i (higher orders are more isotropic). The dual lobe is the
    // slice-3 one: a hard forward lobe starves every sun-at-the-side view.
    const float MS_B = 0.6;
    float ph0 = mix(hg(cosSun, -0.2), hg(cosSun, 0.45), 0.65) * 4.0 * PI;
    float ph1 = mix(hg(cosSun, -0.2 * MS_B), hg(cosSun, 0.45 * MS_B), 0.65) * 4.0 * PI;
    float ph2 = mix(hg(cosSun, -0.2 * MS_B * MS_B), hg(cosSun, 0.45 * MS_B * MS_B), 0.65) * 4.0 * PI;
    // renormalize so uMsW does not change overall brightness, only shadow lift
    float msNorm = 1.0 / (1.0 + uMsW + uMsW * uMsW);
    // silver lining: a narrow forward spike, added to the cloud source as a
    // pure additive rim AFTER msNorm and powder (see the loop) — those two
    // terms exist to balance/darken the diffuse body and would gut exactly the
    // thin sun-facing edges this accent targets (~6x). Gated by Tsun below, so
    // thin high-transmittance edges bloom while self-shadowed cores (Tsun→0)
    // stay dark and cannot blow out.
    float silverPh = hg(cosSun, 0.92) * 4.0 * PI * uSilver;
    for (int i = 0; i < 512; i++) {
      if (float(i) >= N || t >= t1) break;
      vec3 p = ro + rd * t;
      vec2 s2 = sigma2At(p);
      float sig = s2.x + s2.y;
      if (sig > 1e-4) {
        float Tsun = sunTrans(p);
        float hfrac = clamp((p.z - uBoxMin.z) / (uBoxMax.z - uBoxMin.z), 0.0, 1.0);
        vec3 amb = mix(AMB_LOW, AMB_HIGH, hfrac) * (0.25 + 0.45 * hfrac);
        float powder = 1.0 - 0.7 * exp(-s2.x * 1.2);
        // sum the octaves: each deeper order attenuates the sun path less
        // (pow of Tsun toward 1) and phases flatter — that is the creamy lift
        // in the shadowed cores that single scattering renders black.
        float ms = (ph0 * Tsun
                  + uMsW * ph1 * pow(Tsun, uMsA)
                  + uMsW * uMsW * ph2 * pow(Tsun, uMsA * uMsA)) * msNorm;
        vec3 Sc = CLOUD_ALB * (SUN_COL * (ms * powder) + amb);
        // silver rim: unattenuated by msNorm/powder, gated by sun transmittance
        Sc += CLOUD_ALB * SUN_COL * (silverPh * Tsun);
        // rain: dimmer sun response, mostly ambient — a gray translucent veil
        vec3 Sr = RAIN_ALB * (SUN_COL * (ms * 0.55) + amb);
        vec3 S = (Sc * s2.x + Sr * s2.y) / sig;
        float a = 1.0 - exp(-sig * dt);
        acc += T * a * S;
        T *= 1.0 - a;
        if (T < 0.004) break;
      }
      t += dt;
    }
  }

  vec3 col = acc + T * bg;

  // tone map (ACES fit) + gamma + a whisper of dither against banding
  col *= uExposure;
  col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
  col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
  col += (hash12(gl_FragCoord.xy + 0.5) - 0.5) / 255.0;
  fragColor = vec4(col, 1.0);
}
`;

// -- pass 3: tilt-shift depth-of-field (run twice: horizontal, then vertical) --
// The classic miniature cue: a sharp horizontal focus band through the diorama,
// blur ramping up above and below it. Screen-space, LDR, variable-radius
// separable Gaussian. The final (vertical) pass also applies a light toy grade:
// small saturation push + gentle vignette.

export const POST_FRAG = `#version 300 es
precision highp float;

out vec4 fragColor;

uniform sampler2D uTex;
uniform vec2  uRes;
uniform vec2  uDir;        // (1,0) horizontal pass, (0,1) vertical pass
uniform float uFocusY;     // normalized screen y of the focus line
uniform float uBand;       // half-width of the fully sharp band
uniform float uMaxRadius;  // blur radius ceiling, px
uniform float uGrade;      // 1 on the final pass: saturation + vignette

float cocAt(float y) {
  return uMaxRadius * smoothstep(uBand, uBand * 3.0, abs(y - uFocusY));
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float r = cocAt(uv.y);
  vec3 col;
  if (r < 0.5) {
    col = texture(uTex, uv).rgb;
  } else {
    col = vec3(0.0);
    float wsum = 0.0;
    for (int i = -6; i <= 6; i++) {
      float o = float(i) / 6.0;
      float w = exp(-o * o * 2.2);
      col += texture(uTex, uv + uDir * (o * r) / uRes).rgb * w;
      wsum += w;
    }
    col /= wsum;
  }
  if (uGrade > 0.5) {
    float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = clamp(mix(vec3(l), col, 1.13), 0.0, 1.0);
    vec2 v = uv - 0.5;
    col *= 1.0 - 0.16 * dot(v, v);
  }
  fragColor = vec4(col, 1.0);
}
`;

// -- pass 2.5: precipitation particles (slice 4) --------------------------------
// Instanced quads — rain streaks and hail pellets. Everything happens in the
// vertex shader against the SAME resident volume textures the raymarch uses
// (design doc §5.3: no CPU readback): the near-surface field of the species
// gates spawn density; a coarse sun march tints the particle by the storm's
// own shadow; a coarse view march fades particles behind/inside the cloud so
// streaks never glow through an opaque core. Fall animation runs on WALL time
// (like the water ripples — presentation, never physics) and mirrors
// precip.ts fallCycle/cycleFade, which carry the unit tests.

export const PRECIP_VERT = `#version 300 es
precision highp float;
precision highp sampler3D;

layout(location = 0) in vec4 aInst; // u, v within footprint; phase; jitter

uniform mat4  uViewProj;
uniform float uTimeWall;   // wall seconds
uniform vec2  uTilt;       // horizontal slope of the fall axis (wind-shear cue)
uniform float uFallSpeed;  // km/s of display space (pre-scaled by sx)
uniform float uLen;        // streak length along the fall axis, km (pre-scaled)
uniform float uHalfWidth;  // km — screen presence, deliberately NOT scaled
uniform float uZTop;       // top of the fall cycle, km (pre-scaled)
uniform float uGateZ;      // normalized texture z of the near-surface gate
uniform vec4  uGateMask;   // selects the species plane (dot with decoded q)
uniform float uQFloor;     // kg/kg where particles start appearing
uniform float uQFull;      // kg/kg of full population
uniform float uMaxR;       // spawn radius cap, km — rain stays on the diorama
uniform vec3  uColor;
uniform float uAlphaMax;
${VOL_COMMON}
out vec2 vUV;              // x: -1..1 across the streak, y: 0..1 along it
flat out vec4 vTint;       // rgb tint, a peak alpha

void main() {
  vec2 xy = mix(uBoxMin.xy, uBoxMax.xy, aInst.xy);
  float phase = aInst.z;
  float jit = aInst.w;

  // near-surface gate, crossfaded exactly like the raymarch's sigmaAt
  vec3 guvw = vec3(aInst.xy, uGateZ);
  float qA = dot(qDecode(texture(uVolA, guvw) * 255.0), uGateMask);
  float qB = dot(qDecode(texture(uVolB, guvw) * 255.0), uGateMask);
  float q = mix(qA, qB, uMix);
  // population thinning: each instance has a fixed jitter threshold, so the
  // LOCAL count follows the field smoothly instead of stepping on/off
  float dens = smoothstep(uQFloor, uQFull, q);
  if (dens <= jit || length(xy) > uMaxR) {
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0); // degenerate: clipped away
    vUV = vec2(0.0);
    vTint = vec4(0.0);
    return;
  }

  // cyclic fall (mirrors precip.ts fallCycle; unit-tested there)
  float speed = uFallSpeed * (0.85 + 0.3 * jit);
  float f = fract(uTimeWall * speed / uZTop + phase);
  vec3 head = vec3(xy, uZTop - f * uZTop);

  // ends-of-cycle fade (mirrors precip.ts cycleFade)
  float fade = smoothstep(0.0, 0.1, f) * (1.0 - smoothstep(0.85, 1.0, f));

  // quad corner from gl_VertexID: (0,0)(1,0)(1,1) (0,0)(1,1)(0,1)
  int vid = gl_VertexID;
  vec2 corner = vec2(
    (vid == 1 || vid == 2 || vid == 4) ? 1.0 : 0.0,
    (vid == 2 || vid == 4 || vid == 5) ? 1.0 : 0.0);
  float cx = corner.x * 2.0 - 1.0;

  vec3 axis = normalize(vec3(uTilt, -1.0));
  vec3 toCam = normalize(uCamPos - head);
  vec3 side = normalize(cross(axis, toCam));
  vec3 p = head + axis * (corner.y * uLen) + side * (cx * uHalfWidth * (0.8 + 0.4 * jit));

  // lit by the storm itself: sun shadow tints, view-path extinction hides
  // particles under/behind an opaque core (coarse marches — tint, not imagery).
  // Both sample the streak's LOWER third — the part that hangs below the cloud
  // base; measured at the head, a streak emerging from the base gets the
  // inside-the-cloud optical depth and the whole curtain vanishes.
  vec3 pLow = head + axis * (0.7 * uLen);
  float light = mix(0.35, 1.0, sunTrans(pLow));
  float tView = exp(-tauDir(pLow, toCam, 3.0 * uShadowKm, 12));

  vUV = vec2(cx, corner.y);
  vTint = vec4(uColor * light, uAlphaMax * (0.55 + 0.45 * dens) * tView * fade);
  gl_Position = uViewProj * vec4(p, 1.0);
}
`;

export const PRECIP_FRAG = `#version 300 es
precision highp float;

in vec2 vUV;
flat in vec4 vTint;

uniform sampler2D uDepthTex; // g-buffer depth — manual occlusion by the staging
uniform vec2  uRes;

out vec4 fragColor;

void main() {
  // same viewProj as the G-pass, so window depths compare directly
  float d = texture(uDepthTex, gl_FragCoord.xy / uRes).r;
  if (d < 1.0 && gl_FragCoord.z > d + 1e-5) discard;
  float lat = 1.0 - vUV.x * vUV.x;                                  // soft sides
  float lon = smoothstep(0.0, 0.15, vUV.y) * (1.0 - smoothstep(0.85, 1.0, vUV.y));
  float a = vTint.a * lat * lon;
  if (a < 0.003) discard;
  fragColor = vec4(vTint.rgb, a);
}
`;
