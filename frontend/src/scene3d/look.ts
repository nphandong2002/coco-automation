/** Shared "cozy game" look: procedural textures (no external files => nothing to license) and a soft vignette. */
import * as THREE from "three";

export function rng(seed: number) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

function canvasTexture(size: number, draw: (g: CanvasRenderingContext2D, s: number) => void, repeat: [number, number]): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  draw(c.getContext("2d")!, size);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(...repeat);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

const hex = (n: number) => "#" + n.toString(16).padStart(6, "0");
function shade(color: number, k: number): string {
  const r = Math.min(255, Math.round(((color >> 16) & 255) * k)), g = Math.min(255, Math.round(((color >> 8) & 255) * k)), b = Math.min(255, Math.round((color & 255) * k));
  return `rgb(${r},${g},${b})`;
}

/** Irregular flagstone paving (Voronoi-like cells with mortar gaps), warm tones. */
export function flagstoneTexture(base: number, repeat: [number, number], seed = 3): THREE.CanvasTexture {
  return canvasTexture(512, (g, s) => {
    const rand = rng(seed), pts: [number, number][] = [];
    for (let i = 0; i < 34; i++) pts.push([rand() * s, rand() * s]);
    const img = g.createImageData(s, s);
    const tones = pts.map(() => 0.88 + rand() * 0.24);
    const step = 2;
    for (let y = 0; y < s; y += step) for (let x = 0; x < s; x += step) {
      let d1 = 1e9, d2 = 1e9, k = 0;
      for (let i = 0; i < pts.length; i++) for (const ox of [-s, 0, s]) for (const oy of [-s, 0, s]) {
        const dx = x - (pts[i][0] + ox), dy = y - (pts[i][1] + oy), d = dx * dx + dy * dy;
        if (d < d1) { d2 = d1; d1 = d; k = i; } else if (d < d2) d2 = d;
      }
      const edge = Math.sqrt(d2) - Math.sqrt(d1);                    // distance to the cell border
      const mortar = edge < 3.2 ? 0.55 : edge < 6 ? 0.9 + (edge - 3.2) * 0.04 : 1;
      const n = 0.96 + ((x * 7 + y * 13) % 11) * 0.007;
      const f = tones[k] * mortar * n;
      const r = Math.min(255, ((base >> 16) & 255) * f), gg = Math.min(255, ((base >> 8) & 255) * f), b = Math.min(255, (base & 255) * f);
      for (let yy = 0; yy < step; yy++) for (let xx = 0; xx < step; xx++) {
        const o = ((y + yy) * s + (x + xx)) * 4; img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b; img.data[o + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
  }, repeat);
}

/** Wooden planks. */
export function plankTexture(base: number, repeat: [number, number], seed = 5): THREE.CanvasTexture {
  return canvasTexture(512, (g, s) => {
    const rand = rng(seed), n = 8, h = s / n;
    for (let i = 0; i < n; i++) {
      g.fillStyle = shade(base, 0.9 + rand() * 0.2);
      g.fillRect(0, i * h, s, h);
      g.strokeStyle = "rgba(60,35,20,0.16)";
      for (let k = 0; k < 6; k++) { g.beginPath(); const y = i * h + rand() * h; g.moveTo(0, y); g.bezierCurveTo(s * 0.3, y + rand() * 5 - 2, s * 0.7, y + rand() * 5 - 2, s, y); g.stroke(); }
      g.fillStyle = "rgba(40,22,12,0.5)"; g.fillRect(0, i * h, s, 2);
      const cut = rand() * s; g.fillRect(cut, i * h, 2, h);
    }
  }, repeat);
}

/** Soft plaster wall with a subtle vertical wallpaper stripe. */
export function wallTexture(base: number, repeat: [number, number]): THREE.CanvasTexture {
  return canvasTexture(256, (g, s) => {
    g.fillStyle = hex(base); g.fillRect(0, 0, s, s);
    for (let x = 0; x < s; x += 32) { g.fillStyle = "rgba(255,255,255,0.07)"; g.fillRect(x, 0, 16, s); }
    const rand = rng(9);
    for (let i = 0; i < 400; i++) { g.fillStyle = `rgba(0,0,0,${rand() * 0.025})`; g.fillRect(rand() * s, rand() * s, 2, 2); }
  }, repeat);
}

/** Round patterned rug (concentric rings + dots). */
export function rugTexture(base: number, accent: number): THREE.CanvasTexture {
  return canvasTexture(512, (g, s) => {
    g.fillStyle = hex(base); g.fillRect(0, 0, s, s);
    const c = s / 2;
    [[0.48, accent], [0.4, base], [0.34, accent], [0.26, base]].forEach(([r, col]) => { g.fillStyle = typeof col === "number" ? hex(col) : "#fff"; g.beginPath(); g.arc(c, c, (r as number) * s, 0, Math.PI * 2); g.fill(); });
    g.fillStyle = "rgba(255,255,255,0.55)";
    for (let i = 0; i < 16; i++) { const a = (i / 16) * Math.PI * 2; g.beginPath(); g.arc(c + Math.cos(a) * 0.37 * s, c + Math.sin(a) * 0.37 * s, 7, 0, Math.PI * 2); g.fill(); }
  }, [1, 1]);
}

/** Radial darkening at the screen corners; attached to the camera so it is identical in the viewer and in renders. */
export class Vignette {
  readonly mesh: THREE.Mesh;
  private dist = 0.5;
  constructor(strength = 0.38) {
    const c = document.createElement("canvas"); c.width = c.height = 256;
    const g = c.getContext("2d")!;
    const grad = g.createRadialGradient(128, 128, 60, 128, 128, 182);
    grad.addColorStop(0, "rgba(20,10,5,0)"); grad.addColorStop(0.62, "rgba(20,10,5,0)"); grad.addColorStop(1, `rgba(20,10,5,${strength})`);
    g.fillStyle = grad; g.fillRect(0, 0, 256, 256);
    const tex = new THREE.CanvasTexture(c);
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false, fog: false, toneMapped: false }));
    this.mesh.renderOrder = 999; this.mesh.frustumCulled = false; this.mesh.position.set(0, 0, -this.dist);
  }
  fit(cam: THREE.PerspectiveCamera): void {
    const h = 2 * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2) * this.dist;
    this.mesh.scale.set(h * cam.aspect * 1.02, h * 1.02, 1);
  }
}

/** Soft sunbeam: bright at the window, fading away and toward the sides. */
export function beamTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas"); c.width = 64; c.height = 256;
  const g = c.getContext("2d")!;
  const v = g.createLinearGradient(0, 0, 0, 256); v.addColorStop(0, "rgba(255,255,255,0.9)"); v.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = v; g.fillRect(0, 0, 64, 256);
  g.globalCompositeOperation = "destination-in";
  const h = g.createLinearGradient(0, 0, 64, 0); h.addColorStop(0, "rgba(0,0,0,0)"); h.addColorStop(0.25, "rgba(0,0,0,1)"); h.addColorStop(0.75, "rgba(0,0,0,1)"); h.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = h; g.fillRect(0, 0, 64, 256);
  return new THREE.CanvasTexture(c);
}

// ------------------------------------------------------------------ small mesh helpers shared by scene builders
export const mat = (color: number, extra: THREE.MeshStandardMaterialParameters = {}) =>
  new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.02, flatShading: true, ...extra });

export function box(w: number, h: number, d: number, color: number, x: number, y: number, z: number, extra: THREE.MeshStandardMaterialParameters = {}) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, extra));
  m.position.set(x, y, z);
  return m;
}
