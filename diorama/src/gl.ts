// Thin WebGL2 helpers — context, program compilation, fullscreen draw, and the
// volume 3D texture. No engine, no abstraction beyond what this app uses.

export function getGL(canvas: HTMLCanvasElement): WebGL2RenderingContext {
  const gl = canvas.getContext("webgl2", { antialias: false, depth: false, alpha: false });
  if (!gl) throw new Error("WebGL2 is not available in this browser");
  return gl;
}

export function compileProgram(gl: WebGL2RenderingContext, vs: string, fs: string): WebGLProgram {
  const sh = (type: number, src: string) => {
    const s = gl.createShader(type)!;
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      throw new Error(`shader compile:\n${gl.getShaderInfoLog(s)}`);
    }
    return s;
  };
  const p = gl.createProgram()!;
  gl.attachShader(p, sh(gl.VERTEX_SHADER, vs));
  gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(`program link:\n${gl.getProgramInfoLog(p)}`);
  }
  return p;
}

/** RGBA8 3D texture with trilinear filtering (the volume brick). */
export function createVolumeTexture(
  gl: WebGL2RenderingContext,
  nx: number,
  ny: number,
  nz: number,
): WebGLTexture {
  const tex = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.texStorage3D(gl.TEXTURE_3D, 1, gl.RGBA8, nx, ny, nz);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE);
  return tex;
}

/** Small tileable RG8 3D value-noise texture (REPEAT, trilinear) — detail
 *  erosion + rain-veil modulation in the volume march (noise3d.ts bakes it). */
export function createNoiseTexture(
  gl: WebGL2RenderingContext,
  size: number,
  data: Uint8Array,
): WebGLTexture {
  const tex = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.texStorage3D(gl.TEXTURE_3D, 1, gl.RG8, size, size, size);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.REPEAT);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texSubImage3D(gl.TEXTURE_3D, 0, 0, 0, 0, size, size, size, gl.RG, gl.UNSIGNED_BYTE, data);
  return tex;
}

export function uploadVolume(
  gl: WebGL2RenderingContext,
  tex: WebGLTexture,
  nx: number,
  ny: number,
  nz: number,
  data: Uint8Array,
): void {
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texSubImage3D(gl.TEXTURE_3D, 0, 0, 0, 0, nx, ny, nz, gl.RGBA, gl.UNSIGNED_BYTE, data);
}

/** One clip-space triangle covering the screen; no buffers needed. */
export function drawFullscreen(gl: WebGL2RenderingContext): void {
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

// -- staging-mesh + render-target helpers (slice 3) ---------------------------

export interface MeshVAO {
  vao: WebGLVertexArrayObject;
  count: number;
}

/** Static VAO for the staging triangle soup: pos(3) normal(3) color(3) mat(1). */
export function createMeshVAO(gl: WebGL2RenderingContext, data: Float32Array): MeshVAO {
  const vao = gl.createVertexArray()!;
  gl.bindVertexArray(vao);
  const vbo = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  const stride = 10 * 4;
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, stride, 12);
  gl.enableVertexAttribArray(2);
  gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 24);
  gl.enableVertexAttribArray(3);
  gl.vertexAttribPointer(3, 1, gl.FLOAT, false, stride, 36);
  gl.bindVertexArray(null);
  return { vao, count: data.length / 10 };
}

/** Static per-instance VAO for the precip pass: one vec4 attribute, divisor 1.
 *  Quad corners come from gl_VertexID; draw with drawArraysInstanced(…, 6, count). */
export function createInstancedVAO(gl: WebGL2RenderingContext, data: Float32Array): MeshVAO {
  const vao = gl.createVertexArray()!;
  gl.bindVertexArray(vao);
  const vbo = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 16, 0);
  gl.vertexAttribDivisor(0, 1);
  gl.bindVertexArray(null);
  return { vao, count: data.length / 4 };
}

export interface GBuffer {
  fbo: WebGLFramebuffer;
  albedo: WebGLTexture; // rgb albedo, a material flag
  normal: WebGLTexture; // xyz*0.5+0.5
  depth: WebGLTexture; // DEPTH_COMPONENT24, sampled for ray reconstruction
  dispose(): void;
}

function tex2D(gl: WebGL2RenderingContext, w: number, h: number, fmt: number, filter: number): WebGLTexture {
  const t = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texStorage2D(gl.TEXTURE_2D, 1, fmt, w, h);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}

/** MRT target for the staging-mesh pass (albedo + normal + real depth). */
export function createGBuffer(gl: WebGL2RenderingContext, w: number, h: number): GBuffer {
  const albedo = tex2D(gl, w, h, gl.RGBA8, gl.NEAREST);
  const normal = tex2D(gl, w, h, gl.RGBA8, gl.NEAREST);
  const depth = tex2D(gl, w, h, gl.DEPTH_COMPONENT24, gl.NEAREST);
  const fbo = gl.createFramebuffer()!;
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, albedo, 0);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT1, gl.TEXTURE_2D, normal, 0);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, depth, 0);
  gl.drawBuffers([gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1]);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
    throw new Error("g-buffer framebuffer incomplete");
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return {
    fbo,
    albedo,
    normal,
    depth,
    dispose() {
      gl.deleteFramebuffer(fbo);
      gl.deleteTexture(albedo);
      gl.deleteTexture(normal);
      gl.deleteTexture(depth);
    },
  };
}

export interface ColorTarget {
  fbo: WebGLFramebuffer;
  tex: WebGLTexture;
  dispose(): void;
}

/** Plain RGBA8 color target (composite output / blur ping-pong). */
export function createColorTarget(gl: WebGL2RenderingContext, w: number, h: number): ColorTarget {
  const tex = tex2D(gl, w, h, gl.RGBA8, gl.LINEAR);
  const fbo = gl.createFramebuffer()!;
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
    throw new Error("color target framebuffer incomplete");
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return {
    fbo,
    tex,
    dispose() {
      gl.deleteFramebuffer(fbo);
      gl.deleteTexture(tex);
    },
  };
}
