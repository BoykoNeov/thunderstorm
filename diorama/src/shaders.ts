// GLSL. One fullscreen pass raymarches the storm volume over a flat ground
// plane and a pastel sky (slice 1 staging; the low-poly island is slice 3).
//
// Lighting model (design doc §5.1): single scattering with a real secondary
// march toward the sun at every primary sample (self-shadowing), dual-lobe
// Henyey–Greenstein phase, a height-graded ambient term so shadowed bases read
// blue-grey rather than black, and a "powder" darkening at dense cores.
// Extinction is physical-per-species: the four RGBA planes decode back to
// mixing ratios (kg/kg) and combine with per-species weights — the same
// weights the UE material uses (docs/phase1-svt-custom-material-2026-07-16.md).

export const VERT = `#version 300 es
void main() {
  float x = float((gl_VertexID << 1) & 2);
  float y = float(gl_VertexID & 2);
  gl_Position = vec4(x * 2.0 - 1.0, y * 2.0 - 1.0, 0.0, 1.0);
}
`;

export const FRAG = `#version 300 es
precision highp float;
precision highp sampler3D;

out vec4 fragColor;

uniform vec2  uRes;
uniform vec3  uCamPos;
uniform vec3  uCamRight;
uniform vec3  uCamUp;
uniform vec3  uCamFwd;
uniform float uFovTan;        // tan(fovY/2)

uniform vec3  uSunDir;        // unit, toward the sun
uniform vec3  uBoxMin;        // volume bounds, km (z-exaggeration pre-applied)
uniform vec3  uBoxMax;
uniform sampler3D uVolA;      // frame i0
uniform sampler3D uVolB;      // frame i1 (temporal crossfade partner)
uniform float uMix;           // fractional storm time between the two frames

uniform vec4  uThr;           // per-plane decode: q = thr * exp(k * (v255 - 1))
uniform vec4  uK;
uniform vec4  uWeights;       // per-species extinction weights
uniform float uExtScale;      // km^-1 per weighted (kg/kg)
uniform float uSteps;         // primary march step count
uniform float uExposure;

const float PI = 3.14159265;

// -- palette (placeholder; owner tunes by eye in slice 3) --------------------
const vec3 SUN_COL      = vec3(1.00, 0.95, 0.87) * 3.6;
const vec3 SKY_ZENITH   = vec3(0.36, 0.56, 0.76);
const vec3 SKY_HORIZON  = vec3(0.74, 0.83, 0.84);
const vec3 AMB_HIGH     = vec3(0.38, 0.48, 0.60);  // sky light on upper cloud
const vec3 AMB_LOW      = vec3(0.14, 0.17, 0.22);  // bounce light near base
const vec3 GROUND_ALB   = vec3(0.22, 0.34, 0.16);  // muted sage
const vec3 CLOUD_ALB    = vec3(0.93, 0.94, 0.96);

// -- geometry -----------------------------------------------------------------
vec2 rayBox(vec3 ro, vec3 rd, vec3 bmin, vec3 bmax) {
  vec3 inv = 1.0 / rd;
  vec3 a = (bmin - ro) * inv;
  vec3 b = (bmax - ro) * inv;
  vec3 lo = min(a, b), hi = max(a, b);
  return vec2(max(max(lo.x, lo.y), lo.z), min(min(hi.x, hi.y), hi.z));
}

// -- volume sampling ----------------------------------------------------------
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
  // 15 km of occluder is plenty — capping it keeps the steps dense where the
  // shadow actually forms instead of spreading them across the whole box.
  float end = min(max(tb.y, 0.0), 15.0);
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

float hg(float c, float g) {
  float g2 = g * g;
  return (1.0 - g2) / (4.0 * PI * pow(1.0 + g2 - 2.0 * g * c, 1.5));
}

// -- background ---------------------------------------------------------------
vec3 sky(vec3 rd) {
  float h = clamp(rd.z, 0.0, 1.0);
  vec3 col = mix(SKY_HORIZON, SKY_ZENITH, pow(h, 0.55));
  float s = max(dot(rd, uSunDir), 0.0);
  col += vec3(1.0, 0.92, 0.78) * (pow(s, 700.0) * 3.0 + pow(s, 8.0) * 0.06);
  return col;
}

vec3 groundShade(vec3 gp, float dist) {
  float shadow = exp(-sunTau(gp));
  float ndl = max(uSunDir.z, 0.0);
  vec3 col = GROUND_ALB * (SUN_COL * (shadow * ndl) * 0.8 + AMB_HIGH * 0.35);
  // aerial perspective so the plane recedes instead of ending in a hard line
  float f = 1.0 - exp(-dist * 0.004);
  return mix(col, SKY_HORIZON, f);
}

float hash12(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 ndc = (gl_FragCoord.xy / uRes) * 2.0 - 1.0;
  ndc.x *= uRes.x / uRes.y;
  vec3 rd = normalize(uCamFwd + uFovTan * (ndc.x * uCamRight + ndc.y * uCamUp));
  vec3 ro = uCamPos;

  // background: ground plane at z = 0, else sky
  float tg = (rd.z < -1e-5) ? -ro.z / rd.z : 1e9;
  vec3 bg = (tg < 1e8) ? groundShade(ro + rd * tg, tg) : sky(rd);

  // volume interval, clipped by the ground hit
  vec2 tb = rayBox(ro, rd, uBoxMin, uBoxMax);
  float t0 = max(tb.x, 0.0);
  float t1 = min(tb.y, tg);

  vec3 acc = vec3(0.0);
  float T = 1.0;
  if (t1 > t0) {
    float N = uSteps;
    float dt = (t1 - t0) / N;
    float t = t0 + dt * hash12(gl_FragCoord.xy);
    float cosSun = dot(rd, uSunDir);
    // moderately-peaked dual lobe: side-lit cloud still receives real phase
    // weight (a hard 0.65 forward lobe starves every sun-at-the-side view)
    float phase = mix(hg(cosSun, -0.2), hg(cosSun, 0.45), 0.65) * 4.0 * PI;
    for (int i = 0; i < 512; i++) {
      if (float(i) >= N || t >= t1) break;
      vec3 p = ro + rd * t;
      float sig = sigmaAt(p);
      if (sig > 1e-4) {
        float shadow = exp(-sunTau(p));
        float hfrac = clamp((p.z - uBoxMin.z) / (uBoxMax.z - uBoxMin.z), 0.0, 1.0);
        vec3 amb = mix(AMB_LOW, AMB_HIGH, hfrac) * (0.25 + 0.45 * hfrac);
        float powder = 1.0 - 0.7 * exp(-sig * 1.2);
        vec3 S = CLOUD_ALB * (SUN_COL * (shadow * phase * powder) + amb);
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
