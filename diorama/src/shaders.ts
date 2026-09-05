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

import { dbzColorGLSL, wColorGLSL } from "./colormap";

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

// PERF RULE (2026-09-05): every fetch in the fragment shaders is `textureLod(…, 0.0)`,
// never `texture(…)`. Implicit-LOD sampling needs screen-space derivatives, and on
// ANGLE's D3D11 backend a derivative-dependent fetch inside a per-pixel branch forces
// the compiler to FLATTEN that branch — so the 28-step sun march ran for every
// primary sample of every pixel in the box, cloud or not (measured: cost linear in
// sun steps on a completely EMPTY frame; 36 ms → 7 ms at 3200×1800 after the fix).
// All these textures have exactly one mip level, so LOD 0 is the identical texel
// filter and the image is bit-for-bit unchanged; only the branches become real.
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
uniform int   uSunSteps;      // secondary sun-march samples (?sun=, default 28)

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
  vec4 q = qDecode(textureLod(uVolA, uvw, 0.0) * 255.0);
  if (uMix > 0.0001) {
    q = mix(q, qDecode(textureLod(uVolB, uvw, 0.0) * 255.0), uMix);
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
  vec4 v = (uMix < 0.5 ? textureLod(uVolA, uvw, 0.0) : textureLod(uVolB, uvw, 0.0)) * 255.0;
  float sig = uExtScale * dot(uWeights, qDecode(v));
  return max(sig - 0.04, 0.0);
}

int gSunSamples = 0;         // cost diagnostic (?debug=cost): sun-march samples this pixel
float sunTau(vec3 p) {
  vec2 tb = rayBox(p, uSunDir, uBoxMin, uBoxMax);
  // ~15 km of occluder (× display scale) is plenty — capping it keeps the
  // steps dense where the shadow forms instead of across the whole box.
  float end = min(max(tb.y, 0.0), uShadowKm);
  int M = uSunSteps;
  float ds = end / float(M);
  float tau = 0.0;
  float s = ds * 0.5;
  for (int i = 0; i < 64; i++) {
    if (i >= M) break;
    tau += sigmaShadowAt(p + uSunDir * s) * ds;
    gSunSamples++;
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
float sunTransCache(vec3 p) {
  vec2 tb = rayBox(p, uSunDir, uBoxMin, uBoxMax);
  if (tb.y <= max(tb.x, 0.0)) return 1.0;
  vec3 q = p + uSunDir * max(tb.x, 0.0);
  vec3 uvw = clamp((q - uBoxMin) / (uBoxMax - uBoxMin), 0.0, 1.0);
  return uMix < 0.5 ? textureLod(uShadowA, uvw, 0.0).r : textureLod(uShadowB, uvw, 0.0).r;
}
float sunTrans(vec3 p) {
  if (uUseCache < 0.5) return exp(-sunTau(p));
  return sunTransCache(p);
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
uniform float uTonemap;       // 1 = AgX, 0 = ACES fit (?tm=aces)

uniform sampler3D uNoise;     // tileable RG value noise (R coarse, G fine)
uniform vec3  uSizeStorm;     // box size in storm km (display / sx) — noise coords
uniform float uErosion;       // 0..1 edge erosion strength (?er=)
uniform float uJitter;        // idle-accumulation ray-start offset, [0,1) (0 = live look)
uniform float uMsW;           // multi-scatter octave weight (?msw=0 → single scatter)
uniform float uMsA;           // per-octave optical-depth attenuation (?msa=)
uniform float uSilver;        // silver-lining forward-spike weight (?silver=0 off)
uniform float uRays;          // sunlit-haze SURFACE extinction, km^-1 (?rays=0 off)
uniform float uHazeH;         // haze scale height, storm-km (?rayh=): density ~ exp(-alt/H)
uniform float uCoreNorm;      // sigma → "coreness"; scales with sx so the same
                              // cloud erodes identically at any display scale
uniform vec4  uWeightsCld;    // uWeights with the rain plane zeroed
uniform vec4  uRainVeil;      // one-hot rain plane × veil extinction weight (?veil=)
// cross-section (slice 5a): a movable axis-aligned cut plane. uXsec = 0 off,
// else 1/2/3 for the x/y/z axis; uXpos = plane position 0..1 in box space;
// uXmax = field value mapped to the top of the colormap (hydrometeor mode).
// All zero ⇒ the shipped look is bit-unchanged.
uniform float uXsec;
uniform float uXpos;
uniform float uXmax;
// data layer: 0 = hydrometeor (the shipped look), 1 = dBZ radar diagnostic
// (5b), 2 = updraft w (T8). Drives BOTH the volume march (emissive radar/updraft
// MIP vs the cloud shading) and the cross-section cut-face source. dBZ reads its
// own plane (uDbzA); w reads uWA (signed decode, diverging palette).
uniform float uDebug;         // 0 off; 1 = cost heat map (sun-march samples per pixel)
uniform float uHazeCache;     // 1: haze-only samples read the baked sun cache (?hazelc=0 → live march)
uniform float uLayer;
uniform sampler3D uDbzA;      // dBZ diagnostic plane, nearest bound frame
uniform float uDbzThr;        // dBZ threshold: code 0 = below = empty air
uniform float uDbzMax;        // dBZ at code 255 (linear map top)
uniform sampler3D uWA;        // updraft w plane, nearest bound frame (T8)
uniform float uWScale;        // physical decode scale (m/s at code 255) = manifest scale
uniform float uWClip;         // colour-domain clip (m/s): |w|>=uWClip saturates
uniform float uWDead;         // deadband (m/s): |w|<uWDead is transparent
uniform float uWRamp;         // alpha ramp width (m/s) above the deadband
uniform sampler2D uCref;      // composite-reflectivity PLAN plane (T9): a 2D
                              // (NX,NY) map, decoded with uDbzThr/uDbzMax which
                              // cref shares with the 3D dbz layer by identity
                              // (CM1 cref == dbz.max(axis=0); webvol §15).
${VOL_COMMON}
${dbzColorGLSL()}
${wColorGLSL()}

// dBZ at p (box space), linear-decoded from the R8 plane. Code 0 → 0 (empty,
// NOT the palette floor). Nearest bound frame — dBZ steps are 12 s apart and
// the radar read tolerates it (slice-2 sun-march precedent).
float dbzAt(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  float v = textureLod(uDbzA, uvw, 0.0).r * 255.0;
  if (v < 0.5) return 0.0;
  return uDbzThr + (uDbzMax - uDbzThr) * ((v - 1.0) / 254.0);
}
// Signed vertical velocity w (m/s) at p, decoded from the R8 plane: byte 128 is
// EXACTLY 0, codes 1..255 span [-uWScale, +uWScale] (webvol signed-linear-uint8;
// value = (byte-128)/127*scale). Nearest bound frame like dbz.
float wAt(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  float v = textureLod(uWA, uvw, 0.0).r * 255.0;
  return (v - 128.0) / 127.0 * uWScale;
}
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
    vec2 nA = textureLod(uNoise, c, 0.0).rg;
    float ny = textureLod(uNoise, c + vec3(0.37, 0.71, 0.19), 0.0).r;
    float nz = textureLod(uNoise, c + vec3(0.61, 0.13, 0.47), 0.0).r;
    nFine = nA.g;
    vec3 warp = (vec3(nA.r, ny, nz) - 0.5) * (uErosion * 1.7);
    uvw += warp / uSizeStorm;
  }
  vec4 q = qDecode(textureLod(uVolA, uvw, 0.0) * 255.0);
  if (uMix > 0.0001) {
    q = mix(q, qDecode(textureLod(uVolB, uvw, 0.0) * 255.0), uMix);
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
    float v = textureLod(uNoise, vec3(pS.xy * 0.33, pS.z * 0.07 + uTime * 0.05), 0.0).r;
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
  vec4 galb = textureLod(uAlbedo, uv, 0.0);
  vec3 n = normalize(textureLod(uNormalTex, uv, 0.0).xyz * 2.0 - 1.0);
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

// -- cross-section field + colormap (slice 5a) ---------------------------------
// The sliced field is the RAW decoded data — NO erosion/veil noise, no phase
// shading: a cross-section must report what the simulation holds, not the
// beautified render. Hydrometeor mode returns total condensate in g/kg; the
// dBZ layer (5b) reads its own plane instead (handled at the sheet paint below,
// which switches palette + units with uLayer).
float xsecField(vec3 p) {
  vec3 uvw = (p - uBoxMin) / (uBoxMax - uBoxMin);
  vec4 q = qDecode(textureLod(uVolA, uvw, 0.0) * 255.0);
  if (uMix > 0.0001) q = mix(q, qDecode(textureLod(uVolB, uvw, 0.0) * 255.0), uMix);
  return (q.x + q.y + q.z + q.w) * 1000.0; // total condensate, g/kg
}

// viridis — perceptually uniform (Smith/van der Walt), Matt Zucker's polynomial
// fit; the SAME coefficients back the DOM legend in colormap.ts. Uniformity is
// deliberate: a rainbow map would paint bands the data does not contain.
vec3 viridis(float t) {
  t = clamp(t, 0.0, 1.0);
  const vec3 c0 = vec3(0.2777273272234177, 0.005407344544966578, 0.3340998053353061);
  const vec3 c1 = vec3(0.1050930431085774, 1.404613529898575, 1.384590162594685);
  const vec3 c2 = vec3(-0.3308618287255563, 0.214847559468213, 0.09509516302823659);
  const vec3 c3 = vec3(-4.634230498983486, -5.799100973351585, -19.33244095627987);
  const vec3 c4 = vec3(6.228269936347081, 14.17993336680509, 56.69055260068105);
  const vec3 c5 = vec3(4.776384997670288, -13.74514537774601, -65.35303263337234);
  const vec3 c6 = vec3(-5.435455855934631, 4.645852612178535, 26.3124352495832);
  return c0 + t * (c1 + t * (c2 + t * (c3 + t * (c4 + t * (c5 + t * c6)))));
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 ndc = uv * 2.0 - 1.0;
  ndc.x *= uRes.x / uRes.y;
  vec3 rd = normalize(uCamFwd + uFovTan * (ndc.x * uCamRight + ndc.y * uCamUp));
  vec3 ro = uCamPos;

  // staging surface from the g-buffer depth (d = 1 means backdrop); the
  // reconstruction (depth → eye z → ray distance) mirrors mat.ts, tested
  float d = textureLod(uDepthTex, uv, 0.0).r;
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

  // cross-section clip plane (slice 5a): cut away the camera-side half so the
  // storm's interior is exposed; the cut face itself is painted below in LDR.
  float t0o = t0, t1o = t1;   // storm span BEFORE clipping (for the sheet test)
  float tSheet = -1.0;
  if (uXsec > 0.5) {
    int a = int(uXsec + 0.5) - 1;             // 0=x 1=y 2=z
    float planeW = mix(uBoxMin[a], uBoxMax[a], uXpos);
    float roA = ro[a], rdA = rd[a];
    // keep the half on the FAR side of the plane from the camera (auto-facing:
    // the cut always turns toward the viewer as the camera orbits)
    float side = roA > planeW ? -1.0 : 1.0;   // keep side*(p[a]-planeW) >= 0
    if (abs(rdA) < 1e-6) {
      if (side * (roA - planeW) < 0.0) t1 = t0 - 1.0; // whole ray on the cut side
    } else {
      float tPlane = (planeW - roA) / rdA;
      if (side * rdA > 0.0) t0 = max(t0, tPlane);      // kept beyond the plane
      else                  t1 = min(t1, tPlane);      // kept before the plane
      // draw the sheet only where the plane truly cuts the storm and is not
      // hidden behind the staging surface
      if (tPlane > t0o && tPlane < t1o && tPlane < tSurf) tSheet = tPlane;
    }
  }

  // dBZ radar diagnostic (slice 5b): a max-intensity projection through the box
  // — the peak reflectivity along each VIEW RAY (view-dependent; it equals the
  // classic column-max "composite reflectivity" product only looking straight
  // down). No sun/scatter/haze: radar echo is emissive, not lit. Composited in
  // LDR after the tone map (below) so its colour equals the DOM legend exactly,
  // like the 5a cut-face sheet.
  float dbzPeak = 0.0;
  if (uLayer > 0.5 && uLayer < 1.5 && t1 > t0) {
    float N = uSteps;
    float dt = (t1 - t0) / N;
    float t = t0 + dt * fract(hash12(gl_FragCoord.xy) + uJitter);
    for (int i = 0; i < 512; i++) {
      if (float(i) >= N || t >= t1) break;
      dbzPeak = max(dbzPeak, dbzAt(ro + rd * t));
      t += dt;
    }
  }

  // updraft w (T8): a SIGNED max-|w| projection — the strongest vertical motion
  // along each VIEW RAY, keeping its sign (view-dependent, like the dbz MIP; a
  // ray grazing an updraft and an adjacent downdraft shows whichever core is
  // stronger). Init 0 so a ray through still air stays at the transparent
  // deadband. Emissive, composited in LDR below so its colour == the DOM legend.
  float wExt = 0.0;
  if (uLayer > 1.5 && uLayer < 2.5 && t1 > t0) {
    float N = uSteps;
    float dt = (t1 - t0) / N;
    float t = t0 + dt * fract(hash12(gl_FragCoord.xy) + uJitter);
    for (int i = 0; i < 512; i++) {
      if (float(i) >= N || t >= t1) break;
      float w = wAt(ro + rd * t);
      if (abs(w) > abs(wExt)) wExt = w;
      t += dt;
    }
  }

  vec3 acc = vec3(0.0);
  float T = 1.0;
  if (uLayer < 0.5 && t1 > t0) {
    float N = uSteps;
    float dt = (t1 - t0) / N;
    // per-pixel jitter, offset per accumulation pass so the grain averages out
    // when the view is held still (uJitter=0 ⇒ bit-for-bit the live image)
    float t = t0 + dt * fract(hash12(gl_FragCoord.xy) + uJitter);
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
    // sunlit-haze phase: strongly forward — a forward lobe is what makes the
    // shafts read as directional beams rather than a uniform glow.
    float phHaze = hg(cosSun, 0.6) * 4.0 * PI;
    for (int i = 0; i < 512; i++) {
      if (float(i) >= N || t >= t1) break;
      vec3 p = ro + rd * t;
      vec2 s2 = sigma2At(p);
      // altitude above the platter (uBoxMin.z is the ground datum) in storm-km,
      // then height-grade the sunlit haze: aerosol/air density falls off ~expo-
      // nentially with altitude (scale height uHazeH), so the box fills with
      // low gloom and clears aloft — a real vertical profile, not uniform soup.
      // Fading to ~0 near the top is ALSO what removes the boxy anvil-level glow
      // a constant term produced (haze no longer meets the box's top wall).
      vec3 nrm = (p - uBoxMin) / (uBoxMax - uBoxMin);
      float hfrac = clamp(nrm.z, 0.0, 1.0);
      // real haze has no walls — it thins to the horizon. The exp grade clears
      // the box TOP; without this the dense low deck would instead meet the box
      // SIDE walls and, backlit, glow as a hard rectangular rim (a lit box, not
      // atmosphere). Fade the haze toward the XY perimeter over a fixed margin
      // so the deck vanishes before every wall — the storm is centred, so the
      // under-anvil gloom this term is for is untouched.
      float edge = smoothstep(0.0, 0.16, min(min(nrm.x, 1.0 - nrm.x),
                                             min(nrm.y, 1.0 - nrm.y)));
      float haze = uRays * exp(-hfrac * uSizeStorm.z / uHazeH) * edge;
      float sig = s2.x + s2.y + haze;
      if (sig > 1e-4) {
        // Sun transmittance: the live 28-step march inside cloud/rain (the
        // baked half-res R8 cache stair-steps dense cores — see main.ts ?lc=),
        // but ONE cache fetch for haze-only samples. Open air is exactly where
        // the cache is faithful (T is smooth there), and the haze deck is where
        // most in-box samples live: measured 14.5 → ~6 ms at 3200×1800.
        float Tsun = (s2.x + s2.y > 1e-4 || uHazeCache < 0.5) ? sunTrans(p) : sunTransCache(p);
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
        // sunlit haze: the height-graded extinction (dense low, thin aloft), lit
        // only by the cached sun transmittance → bright where sun reaches the air,
        // dark under the anvil's shadow (crepuscular shafts + under-storm gloom).
        // Not gutted by powder (thin-air term), so it survives where step 2 warned.
        vec3 Sh = SUN_COL * (phHaze * Tsun) + AMB_HIGH * 0.3;
        vec3 S = (Sc * s2.x + Sr * s2.y + Sh * haze) / sig;
        float a = 1.0 - exp(-sig * dt);
        acc += T * a * S;
        T *= 1.0 - a;
        if (T < 0.004) break;
      }
      t += dt;
    }
  }

  vec3 col = acc + T * bg;

  // tone map (AgX or ACES fit) + gamma + a whisper of dither against banding
  col *= uExposure;
  if (uTonemap > 0.5) {
    // AgX (Sobotka; matrices/polynomial as in the three.js implementation).
    // Pipeline: inset matrix → log2 encode → sigmoid contrast → outset matrix
    // → back to linear; the shared gamma below then encodes for display. AgX
    // holds white on the bright sunlit cauliflower where the ACES fit tints
    // it orange near clipping (?tm=aces reverts).
    const mat3 AGX_IN = mat3(
      0.842479062253094,  0.0423282422610123, 0.0423756549057051,
      0.0784335999999992, 0.878468636469772,  0.0784336,
      0.0792237451477643, 0.0791661274605434, 0.879142973793104);
    const mat3 AGX_OUT = mat3(
       1.19687900512017,   -0.0528968517574562, -0.0529716355144438,
      -0.0980208811401368,  1.15190312990417,   -0.0980434501171241,
      -0.0990297440797205, -0.0989611768448433,  1.15107367264116);
    const float EV_MIN = -12.47393;
    const float EV_MAX = 4.026069;
    col = AGX_IN * col;
    col = clamp((log2(max(col, vec3(1e-10))) - EV_MIN) / (EV_MAX - EV_MIN), 0.0, 1.0);
    vec3 x2 = col * col;
    vec3 x4 = x2 * x2;
    col = 15.5 * x4 * x2 - 40.14 * x4 * col + 31.96 * x4
        - 6.868 * x2 * col + 0.4298 * x2 + 0.1191 * col - 0.00232;
    col = AGX_OUT * col;
    col = pow(max(col, vec3(0.0)), vec3(2.2)); // AgX outputs 2.2-encoded; back to linear
  } else {
    col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
  }
  col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
  col += (hash12(gl_FragCoord.xy + 0.5) - 0.5) / 255.0;

  // dBZ radar volume (slice 5b): composite the max-intensity projection over the
  // (cloudless) staging in LDR so its rainbow equals the DOM legend exactly.
  // Empty columns (dbzPeak==0) stay clear; weak echo edges fade in near the
  // threshold, strong cores read near-solid. Diagnostic, labeled in the HUD.
  if (uLayer > 0.5 && uLayer < 1.5 && dbzPeak > uDbzThr) {
    float a = smoothstep(uDbzThr, uDbzThr + 8.0, dbzPeak) * 0.92;
    col = mix(col, dbzColor(dbzPeak), a);
  }

  // updraft w volume (T8): composite the signed max-|w| projection in LDR so its
  // diverging colour equals the DOM legend. |w| below the deadband stays clear
  // (still air shows the diorama through it); alpha rises over uWRamp so weak
  // motion is faint and the storm core reads near-solid. Colour normalizes by
  // the FIXED clip (uWClip), so red = the same m/s in every scenario.
  if (uLayer > 1.5 && uLayer < 2.5 && abs(wExt) > uWDead) {
    float a = smoothstep(uWDead, uWDead + uWRamp, abs(wExt)) * 0.92;
    col = mix(col, wColor(clamp(wExt / uWClip, -1.0, 1.0)), a);
  }

  // composite reflectivity — the RADAR PLAN VIEW (T9). Distinct from the dBZ
  // layer above: that is a max along the VIEW RAY (changes as you orbit); this
  // is CM1's column-max cref, a VIEW-INDEPENDENT 2D map, painted flat on the
  // rendered ground where the ray hits land (d<1.0) inside the storm footprint.
  // Same NWS palette + (uDbzThr,uDbzMax) as the dbz layer — exact, not
  // approximate (cref shares the dbz scale by identity). LDR, so on-screen
  // colour == the DOM legend. Beyond the footprint / over sea it does not paint.
  if (uLayer > 2.5 && d < 1.0) {
    vec3 pG = ro + rd * tSurf;                       // the shaded surface point
    vec2 fuv = (pG.xy - uBoxMin.xy) / (uBoxMax.xy - uBoxMin.xy);
    if (fuv.x >= 0.0 && fuv.x <= 1.0 && fuv.y >= 0.0 && fuv.y <= 1.0) {
      float v = textureLod(uCref, fuv, 0.0).r * 255.0;
      if (v > 0.5) {                                 // code 0 = below threshold = no echo
        float dbz = uDbzThr + (uDbzMax - uDbzThr) * ((v - 1.0) / 254.0);
        float a = smoothstep(uDbzThr, uDbzThr + 8.0, dbz) * 0.92;
        col = mix(col, dbzColor(dbz), a);
      }
    }
  }

  // cross-section sheet: paint the false-color field on the cut face, in LDR so
  // the on-screen color equals the DOM legend exactly. Alpha rises with field
  // magnitude — empty air stays clear so the exposed interior shows through,
  // strong echo reads as a near-solid slab. Palette + units switch with uLayer:
  // viridis/(g/kg) for hydrometeors, the radar rainbow/(dBZ) for the dBZ layer.
  if (tSheet > 0.0) {
    vec3 pS = ro + rd * tSheet;
    if (uLayer > 0.5 && uLayer < 1.5) {
      float dbz = dbzAt(pS);
      if (dbz > uDbzThr) {
        float a = smoothstep(uDbzThr, uDbzThr + 8.0, dbz) * 0.95;
        col = mix(col, dbzColor(dbz), a);
      }
    } else if (uLayer > 1.5 && uLayer < 2.5) {
      float w = wAt(pS);
      if (abs(w) > uWDead) {
        float a = smoothstep(uWDead, uWDead + uWRamp, abs(w)) * 0.95;
        col = mix(col, wColor(clamp(w / uWClip, -1.0, 1.0)), a);
      }
    } else if (uLayer < 0.5) {
      // hydrometeor cut face only. cref (uLayer≈3) is a plan product with no
      // volumetric cross-section, so it matches nothing here (no viridis paint).
      float f = xsecField(pS);
      float tn = clamp(f / max(uXmax, 1e-3), 0.0, 1.0);
      float a = pow(tn, 0.6);   // lift thin echo without hiding the empty-air gaps
      col = mix(col, viridis(tn), a);
    }
  }
  if (uDebug > 0.5) {
    // cost heat map: black = no sun march, blue→green→red→white = more samples
    // (full scale 280 primary steps × uSunSteps). Presentation-only diagnostic.
    float c = float(gSunSamples) / (280.0 * float(uSunSteps));
    col = c < 0.02 ? vec3(0.0) : mix(mix(vec3(0.1, 0.2, 1.0), vec3(0.2, 1.0, 0.2), min(c * 4.0, 1.0)),
                                     mix(vec3(1.0, 0.2, 0.1), vec3(1.0), clamp(c * 2.0 - 1.0, 0.0, 1.0)), clamp(c * 4.0 - 1.0, 0.0, 1.0));
  }
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
uniform float uSplit;      // warm/cool split-tone strength (?split=0 off)

float cocAt(float y) {
  return uMaxRadius * smoothstep(uBand, uBand * 3.0, abs(y - uFocusY));
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float r = cocAt(uv.y);
  vec3 col;
  if (r < 0.5) {
    col = textureLod(uTex, uv, 0.0).rgb;
  } else {
    col = vec3(0.0);
    float wsum = 0.0;
    for (int i = -6; i <= 6; i++) {
      float o = float(i) / 6.0;
      float w = exp(-o * o * 2.2);
      col += textureLod(uTex, uv + uDir * (o * r) / uRes, 0.0).rgb * w;
      wsum += w;
    }
    col /= wsum;
  }
  if (uGrade > 0.5) {
    float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = clamp(mix(vec3(l), col, 1.13), 0.0, 1.0);
    // warm/cool split-tone: highlights toward storm-light warmth, shadows
    // toward blue-grey — luma-hinged so mid-grey stays neutral (?split=0 off)
    col += (l - 0.55) * vec3(0.045, 0.015, -0.045) * uSplit;
    col = clamp(col, 0.0, 1.0);
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
uniform float uXsec;       // cross-section axis (slice 5a): 0 off, else 1/2/3
uniform float uXpos;       // plane position 0..1 in box space
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

  // cross-section (slice 5a): a particle in the clipped-away camera-side half
  // would otherwise draw in front of the cut face — cull it with the SAME
  // auto-facing half-space the composite raymarch uses.
  if (uXsec > 0.5) {
    int xa = int(uXsec + 0.5) - 1;
    float planeW = mix(uBoxMin[xa], uBoxMax[xa], uXpos);
    float side = uCamPos[xa] > planeW ? -1.0 : 1.0;
    if (side * (head[xa] - planeW) < 0.0) {
      gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
      vUV = vec2(0.0);
      vTint = vec4(0.0);
      return;
    }
  }

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
  float d = textureLod(uDepthTex, gl_FragCoord.xy / uRes, 0.0).r;
  if (d < 1.0 && gl_FragCoord.z > d + 1e-5) discard;
  float lat = 1.0 - vUV.x * vUV.x;                                  // soft sides
  float lon = smoothstep(0.0, 0.15, vUV.y) * (1.0 - smoothstep(0.85, 1.0, vUV.y));
  float a = vTint.a * lat * lon;
  if (a < 0.003) discard;
  fragColor = vec4(vTint.rgb, a);
}
`;

// -- pass 4: FXAA (Lottes console variant) -------------------------------------
// The G-pass has no MSAA (getGL requests antialias:false, and the G-buffer is
// NEAREST-sampled), so staging silhouettes (mountains, towns, forest cones)
// alias. This runs LAST, after tilt-shift, on the final LDR image so it also
// smooths precip streak edges. Luma-directed 4-tap edge blur with a local-
// contrast gate: the composite's static 1/255 dither sits below the gate and is
// untouched (no crawling worms), and clouds are low-frequency so the gate leaves
// them alone — only geometric edges get smoothed.
export const FXAA_FRAG = `#version 300 es
precision highp float;
out vec4 fragColor;
uniform sampler2D uTex;
uniform vec2 uRes;

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

void main() {
  vec2 px = 1.0 / uRes;
  vec2 uv = gl_FragCoord.xy * px;
  vec3 cM = textureLod(uTex, uv, 0.0).rgb;
  float lM = luma(cM);
  float lN = luma(textureLod(uTex, uv + vec2(0.0,  px.y), 0.0).rgb);
  float lS = luma(textureLod(uTex, uv - vec2(0.0,  px.y), 0.0).rgb);
  float lE = luma(textureLod(uTex, uv + vec2(px.x, 0.0), 0.0).rgb);
  float lW = luma(textureLod(uTex, uv - vec2(px.x, 0.0), 0.0).rgb);
  float lMin = min(lM, min(min(lN, lS), min(lE, lW)));
  float lMax = max(lM, max(max(lN, lS), max(lE, lW)));
  if (lMax - lMin < max(0.0312, lMax * 0.125)) { fragColor = vec4(cM, 1.0); return; }
  float lNW = luma(textureLod(uTex, uv + vec2(-px.x,  px.y), 0.0).rgb);
  float lNE = luma(textureLod(uTex, uv + vec2( px.x,  px.y), 0.0).rgb);
  float lSW = luma(textureLod(uTex, uv + vec2(-px.x, -px.y), 0.0).rgb);
  float lSE = luma(textureLod(uTex, uv + vec2( px.x, -px.y), 0.0).rgb);
  vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
  float dirReduce = max((lNW + lNE + lSW + lSE) * 0.03125, 1.0 / 128.0);
  float rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + dirReduce);
  dir = clamp(dir * rcp, vec2(-8.0), vec2(8.0)) * px;
  vec3 a = 0.5 * (textureLod(uTex, uv + dir * (1.0 / 3.0 - 0.5), 0.0).rgb
                + textureLod(uTex, uv + dir * (2.0 / 3.0 - 0.5), 0.0).rgb);
  vec3 b = a * 0.5 + 0.25 * (textureLod(uTex, uv + dir * -0.5, 0.0).rgb
                           + textureLod(uTex, uv + dir *  0.5, 0.0).rgb);
  float lB = luma(b);
  fragColor = vec4((lB < lMin || lB > lMax) ? a : b, 1.0);
}
`;
