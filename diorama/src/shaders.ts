// GLSL, three passes (slice 3):
//   1. G-pass — rasterize the low-poly staging mesh (island/water/base wall)
//      into albedo+material, flat normal, and a real depth buffer.
//   2. Composite — fullscreen raymarch of the storm volume over the staging:
//      surface pixels are shaded here (so the storm's shadow march darkens
//      the toy landscape), background is a pastel gradient, then tone map.
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

// -- pass 2: volume raymarch + surface shading + background --------------------

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

uniform sampler2D uAlbedo;    // g-buffer: staging albedo + material flag
uniform sampler2D uNormalTex; // g-buffer: flat face normal
uniform sampler2D uDepthTex;  // g-buffer: depth (ray-distance reconstruction)
uniform float uNear;
uniform float uFar;
uniform float uTime;          // wall seconds — water ripple only, never physics

uniform vec4  uThr;           // per-plane decode: q = thr * exp(k * (v255 - 1))
uniform vec4  uK;
uniform vec4  uWeights;       // per-species extinction weights
uniform float uExtScale;      // km^-1 per weighted (kg/kg)
uniform float uSteps;         // primary march step count
uniform float uExposure;

const float PI = 3.14159265;

// -- palette (placeholder; owner tunes by eye) ---------------------------------
const vec3 SUN_COL      = vec3(1.00, 0.95, 0.87) * 3.6;
const vec3 BG_TOP       = vec3(0.58, 0.73, 0.88);  // pastel backdrop, upper
const vec3 BG_HORIZON   = vec3(0.95, 0.94, 0.91);
const vec3 BG_LOW       = vec3(0.72, 0.78, 0.85);  // soft blue wash below
const vec3 AMB_HIGH     = vec3(0.38, 0.48, 0.60);  // sky light on upper cloud
const vec3 AMB_LOW      = vec3(0.14, 0.17, 0.22);  // bounce light near base
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

// -- background: pastel gradient, not a physical sky ---------------------------
vec3 background(vec3 rd) {
  vec3 col = mix(BG_HORIZON, BG_TOP, smoothstep(-0.02, 0.55, rd.z));
  col = mix(col, BG_LOW, smoothstep(-0.08, -0.55, rd.z));
  float s = max(dot(rd, uSunDir), 0.0);
  col += vec3(1.0, 0.9, 0.75) * pow(s, 9.0) * 0.07; // faint warm cast, no sun disc
  return col;
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
  float shadow = exp(-sunTau(p));
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
