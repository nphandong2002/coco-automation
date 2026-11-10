/**
 * Framework-free three.js scene engine. Used by the React viewer now and by the headless frame
 * capture in the render worker next: everything advances through `advance(dt)` from fixed inputs
 * (seeded randomness, no wall-clock reads), so stepping with a fixed dt is reproducible.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Environment3D, PickTarget, Preset, ReactionTrigger, Scene3D, TimeOfDay } from "./types";

interface PresetStyle {
  wall: number; floor: number; accent: number; wood: number;
  window: [number, number]; outside: "hills" | "city" | "trees" | "street";
  props: Array<"desk" | "shelf" | "rug" | "counter" | "pendants">;
}
const STYLES: Record<Preset, PresetStyle> = {
  cozy_room: { wall: 0xf3d9dc, floor: 0xb98a63, accent: 0xf08ca4, wood: 0x8a5a3c, window: [1.3, 1.0], outside: "hills", props: ["desk", "shelf", "rug"] },
  rainy_window: { wall: 0xb8c4d6, floor: 0x7a6a62, accent: 0x7aa2e3, wood: 0x5b4a44, window: [2.2, 1.4], outside: "city", props: ["desk", "rug"] },
  forest_cabin: { wall: 0xa9744a, floor: 0x7b5233, accent: 0xe2a14a, wood: 0x5a3a22, window: [1.2, 1.0], outside: "trees", props: ["shelf", "rug"] },
  cafe: { wall: 0xf1e4d0, floor: 0x9b7556, accent: 0xd9825b, wood: 0x6b4a33, window: [1.8, 1.2], outside: "street", props: ["counter", "pendants"] },
};
const SKY: Record<TimeOfDay, { sky: number; ambient: number; ambientI: number; sun: number; sunI: number; stars: boolean }> = {
  day: { sky: 0xbfe3ff, ambient: 0xffffff, ambientI: 1.0, sun: 0xfff2d6, sunI: 1.4, stars: false },
  dusk: { sky: 0xe8906a, ambient: 0xffc9a8, ambientI: 0.75, sun: 0xff9a5c, sunI: 0.8, stars: false },
  night: { sky: 0x0b1226, ambient: 0x7f93d6, ambientI: 0.6, sun: 0x8da0e6, sunI: 0.55, stars: true },
};

function rng(seed: number) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const mat = (color: number, extra: THREE.MeshStandardMaterialParameters = {}) =>
  new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.02, flatShading: true, ...extra });
function box(w: number, h: number, d: number, color: number, x: number, y: number, z: number, extra: THREE.MeshStandardMaterialParameters = {}) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, extra));
  m.position.set(x, y, z);
  return m;
}

const RAIN_MAX = 1400;
const ROOM = { w: 4.4, d: 4.2, h: 2.7, back: -2 };

export interface EngineOptions {
  interactive?: boolean;                 // orbit + picking (dashboard); false for headless capture
  preserveDrawingBuffer?: boolean;       // needed to read pixels
  pixelRatio?: number;                   // default min(devicePixelRatio, 2); capture uses 1
  onEnvChange?: (env: Environment3D) => void;   // user clicked a window/fireplace/lamp
  onPick?: (t: PickTarget | null) => void;
  onHover?: (t: PickTarget | null) => void;
  onReady?: (info: { clips: string[]; placeholder: boolean }) => void;
}

export class SceneEngine {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(45, 16 / 9, 0.05, 100);
  controls: OrbitControls | null = null;
  private cfg: Scene3D | null = null;
  private env: Environment3D | null = null;
  private time = 0;
  private loopLen: number | null = null;   // seconds; when set every motion is periodic with this length
  private raf = 0;
  private last = 0;
  private loadToken = 0;

  // dynamic parts
  private root = new THREE.Group();
  private ambient = new THREE.AmbientLight();
  private sun = new THREE.DirectionalLight();
  private lampLight = new THREE.PointLight(0xffd29a, 1.6, 7, 1.6);
  private fireLight = new THREE.PointLight(0xff7a2a, 2, 6, 1.6);
  private flames: THREE.Mesh[] = [];
  private rain: THREE.LineSegments | null = null;
  private rainSeeds: Float32Array = new Float32Array(0);
  private lampBulb: THREE.Mesh | null = null;
  private stars: THREE.Points | null = null;
  private pickables: THREE.Object3D[] = [];
  private raycaster = new THREE.Raycaster();
  private hover: PickTarget | null = null;

  // character
  private charGroup = new THREE.Group();
  private mixer: THREE.AnimationMixer | null = null;
  private clips = new Map<string, THREE.AnimationClip>();
  private idleAction: THREE.AnimationAction | null = null;
  private placeholder: { body: THREE.Object3D; head: THREE.Object3D; arm: THREE.Object3D; eyes: THREE.Object3D[] } | null = null;
  private reactionT = -1;        // seconds since a placeholder reaction started (-1 = none)
  private lookWindow = 0;        // 0..1 head turned toward the window
  private cold = 0;              // 0..1 hunched/shivering when the fireplace is out
  private stateMode = false;     // render mode: env reactions are steady STATES (looped), not one-shot events
  private pending: { name: ReactionTrigger; at: number } | null = null;

  constructor(private canvas: HTMLCanvasElement, private opts: EngineOptions = {}) {
    this.renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, alpha: false, preserveDrawingBuffer: !!opts.preserveDrawingBuffer, powerPreference: "low-power",
    });
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.setPixelRatio(opts.pixelRatio ?? Math.min(window.devicePixelRatio || 1, 2));
    const fill = new THREE.DirectionalLight(0xfff0e0, 0.55);   // soft front light so characters stay readable at night
    fill.position.set(1.5, 2.5, 4);
    this.scene.add(this.root, this.ambient, this.sun, fill);
    if (opts.interactive) {
      this.controls = new OrbitControls(this.camera, canvas);
      this.controls.enableDamping = true;
      this.controls.maxPolarAngle = Math.PI * 0.52;
      this.controls.minDistance = 0.8;
      this.controls.maxDistance = 9;
      canvas.addEventListener("pointerdown", this.onDown);
      canvas.addEventListener("pointermove", this.onMove);
    }
  }

  // ------------------------------------------------------------------ public API
  async setScene(cfg: Scene3D, modelUrl?: string | null): Promise<void> {
    const token = ++this.loadToken;
    this.cfg = structuredClone(cfg);
    this.env = { ...cfg.environment };
    this.time = 0; this.reactionT = -1; this.pending = null;
    this.lookWindow = cfg.environment.rain >= 0.7 ? 1 : 0; this.cold = cfg.environment.fireplace ? 0 : 1;
    this.disposeRoot();
    this.buildRoom(cfg.preset);
    this.applyEnvironment();
    this.applyCamera(cfg.camera.position, cfg.camera.target, cfg.camera.fov);
    await this.buildCharacter(cfg, modelUrl ?? null, token);
  }

  setEnvironment(env: Environment3D): void {
    if (!this.env) return;
    const prev = this.env;
    this.env = { ...env };
    this.applyEnvironment();
    if (env.rain >= 0.7 && prev.rain < 0.7) this.trigger("rain_heavy");
    if (!env.fireplace && prev.fireplace) this.trigger("fire_out");
    if (env.time_of_day !== prev.time_of_day) this.rebuildSkyOnly();
  }

  trigger(name: ReactionTrigger): void {
    const clipName = this.cfg?.character.reactions[name];
    if (this.mixer && clipName && this.clips.has(clipName)) {
      const action = this.mixer.clipAction(this.clips.get(clipName)!);
      action.reset().setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
      action.fadeIn(0.2).play();
      this.idleAction?.fadeOut(0.2);
      const done = (e: { action: THREE.AnimationAction }) => {
        if (e.action !== action) return;
        this.mixer!.removeEventListener("finished", done as never);
        action.fadeOut(0.25);
        if (this.idleAction) {   // resume idle at the phase it would have had: keeps rendered loops seamless
          const d = this.idleAction.getClip().duration;
          this.idleAction.reset(); this.idleAction.time = this.time % d; this.idleAction.fadeIn(0.25).play();
        }
      };
      this.mixer.addEventListener("finished", done as never);
    } else if (this.placeholder && (name === "click" || name === "break_time")) {
      this.reactionT = 0;
    }
  }

  currentCamera() {
    const t = this.controls?.target ?? new THREE.Vector3(...(this.cfg?.camera.target ?? [0, 0.9, 0]));
    const r = (n: number) => Math.round(n * 100) / 100;
    return {
      position: [r(this.camera.position.x), r(this.camera.position.y), r(this.camera.position.z)] as [number, number, number],
      target: [r(t.x), r(t.y), r(t.z)] as [number, number, number], fov: this.camera.fov,
    };
  }

  resize(w: number, h: number): void {
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  /** Advance the simulation by `dt` seconds (fixed steps => reproducible). */
  advance(dt: number): void {
    this.time += dt;
    const t = this.time, env = this.env;
    if (!env) return;
    if (this.pending && t >= this.pending.at) { const n = this.pending.name; this.pending = null; this.trigger(n); }
    // fire: layered sines (no randomness at runtime)
    const flick = 0.82 + 0.18 * (Math.sin(t * this.w(13.1)) + Math.sin(t * this.w(7.3) + 1.7) + Math.sin(t * this.w(23.9) + 4.1)) / 3;
    if (env.fireplace) {
      this.fireLight.intensity = 2.2 * flick;
      this.flames.forEach((f, i) => { f.scale.set(1 + 0.12 * Math.sin(t * this.w(9) + i * 2), flick * (0.9 + 0.25 * Math.sin(t * this.w(11) + i)), 1); f.rotation.y = t * this.w(0.6) + i; });
    }
    this.updateRain(t, env);
    if (this.mixer) this.mixer.update(dt);
    this.updatePlaceholder(dt, t, env);
    this.controls?.update();
  }

  /** Make all motion periodic with `seconds` (frame N == frame 0) so the rendered clip loops seamlessly. */
  setLoop(seconds: number | null): void { this.loopLen = seconds && seconds > 0 ? seconds : null; }
  /** Length of the idle animation clip of a loaded .glb (null for the built-in character). */
  /** Render mode: steady environment reactions (heavy rain / fire out) loop as the ambient animation. */
  setStateMode(on: boolean): void { this.stateMode = on; }
  /** Fire `name` once when the simulation clock reaches `at` seconds (used by the render worker). */
  scheduleEvent(name: ReactionTrigger, at: number): void { this.pending = { name, at }; }
  /** How long the reaction for `name` takes (clip length, or 1.6 s for the built-in character). */
  reactionDuration(name: ReactionTrigger): number | null {
    const c = this.cfg?.character.reactions[name];
    if (this.mixer && c && this.clips.has(c)) return this.clips.get(c)!.duration;
    return this.placeholder && (name === "click" || name === "break_time") ? 1.6 : null;
  }
  idleDuration(): number | null { return this.idleAction ? this.idleAction.getClip().duration : null; }
  /** Angular frequency rounded so that a whole number of cycles fits the loop. */
  private w(f: number): number {
    if (!this.loopLen) return f;
    const k = 2 * Math.PI / this.loopLen;
    return Math.max(1, Math.round(f / k)) * k;
  }

  render(): void { this.renderer.render(this.scene, this.camera); }

  start(): void {
    if (this.raf) return;
    this.last = performance.now();
    const loop = (now: number) => {
      this.raf = requestAnimationFrame(loop);
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      this.advance(dt);
      this.render();
    };
    this.raf = requestAnimationFrame(loop);
  }
  stop(): void { cancelAnimationFrame(this.raf); this.raf = 0; }

  dispose(): void {
    this.stop();
    this.loadToken++;
    this.canvas.removeEventListener("pointerdown", this.onDown);
    this.canvas.removeEventListener("pointermove", this.onMove);
    this.controls?.dispose();
    this.disposeRoot();
    this.renderer.dispose();
  }

  // ------------------------------------------------------------------ room
  private disposeRoot(): void {
    const kill = (o: THREE.Object3D) => o.traverse((c) => {
      const m = c as THREE.Mesh;
      m.geometry?.dispose?.();
      const mt = m.material as THREE.Material | THREE.Material[] | undefined;
      (Array.isArray(mt) ? mt : mt ? [mt] : []).forEach((x) => { (x as THREE.MeshStandardMaterial).map?.dispose?.(); x.dispose(); });
    });
    kill(this.root); kill(this.charGroup);
    this.root.clear(); this.charGroup.clear();
    this.scene.remove(this.charGroup, this.lampLight, this.fireLight);
    this.flames = []; this.pickables = []; this.rain = null; this.stars = null; this.lampBulb = null;
    this.mixer = null; this.idleAction = null; this.clips.clear(); this.placeholder = null;
  }

  private pickable(obj: THREE.Object3D, target: PickTarget): void { obj.userData.pick = target; this.pickables.push(obj); }

  private buildRoom(preset: Preset): void {
    const s = STYLES[preset], { w, d, h, back } = ROOM;
    const r = this.root;
    r.add(box(w, 0.1, d, s.floor, 0, -0.05, back + d / 2));                               // floor
    r.add(box(0.1, h, d, s.wall, -w / 2, h / 2, back + d / 2), box(0.1, h, d, s.wall, w / 2, h / 2, back + d / 2)); // side walls
    r.add(box(w, 0.12, 0.1, s.wood, 0, 0.06, back + 0.06));                                 // skirting
    r.add(box(w, 0.1, d, s.wall, 0, h + 0.05, back + d / 2));                                // ceiling
    // back wall with a window opening
    const [ww, wh] = s.window, wx = -0.6, wy = 1.55, wt = 0.14;
    const L = wx - ww / 2 + w / 2, R = w / 2 - (wx + ww / 2), bz = back;
    r.add(box(L, h, wt, s.wall, -w / 2 + L / 2, h / 2, bz), box(R, h, wt, s.wall, w / 2 - R / 2, h / 2, bz));
    r.add(box(ww, wy - wh / 2, wt, s.wall, wx, (wy - wh / 2) / 2, bz), box(ww, h - (wy + wh / 2), wt, s.wall, wx, wy + wh / 2 + (h - wy - wh / 2) / 2, bz));
    // window frame + glass (glass is pickable: toggles rain)
    const frame = new THREE.Group();
    frame.add(box(ww + 0.12, 0.06, 0.1, s.wood, wx, wy + wh / 2, bz + 0.03), box(ww + 0.12, 0.06, 0.1, s.wood, wx, wy - wh / 2, bz + 0.03),
      box(0.06, wh, 0.1, s.wood, wx - ww / 2, wy, bz + 0.03), box(0.06, wh, 0.1, s.wood, wx + ww / 2, wy, bz + 0.03),
      box(0.04, wh, 0.06, s.wood, wx, wy, bz + 0.03), box(ww, 0.04, 0.06, s.wood, wx, wy, bz + 0.03));
    r.add(frame);
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(ww, wh), new THREE.MeshStandardMaterial({ color: 0xcfe6ff, transparent: true, opacity: 0.14, roughness: 0.1 }));
    glass.position.set(wx, wy, bz + 0.05);
    this.pickable(glass, "window"); r.add(glass);
    this.buildOutside(s, wx, bz);
    // fireplace on the back wall (right of the window)
    this.buildFireplace(s, 1.45, bz + 0.2);
    if (s.props.includes("desk")) this.buildDesk(s, -1.25, back + 1.3);
    if (s.props.includes("shelf")) this.buildShelf(s, -w / 2 + 0.22, back + 1.4);
    if (s.props.includes("rug")) { const rug = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.1, 0.02, 32), mat(s.accent)); rug.position.set(0.4, 0.01, back + 2.1); r.add(rug); }
    if (s.props.includes("counter")) this.buildCounter(s, -w / 2 + 0.5, back + 2.0);
    if (s.props.includes("pendants")) [-1.4, 0, 1.4].forEach((x) => this.addPendant(x));
    this.buildLamp(s, s.props.includes("desk") ? -1.25 : 1.9, s.props.includes("desk") ? back + 1.3 : back + 1.2);
    this.rebuildSkyOnly();
    this.buildRain(wx, ww, bz);
    this.scene.add(this.fireLight, this.lampLight);
  }

  private buildOutside(s: PresetStyle, wx: number, bz: number): void {
    const g = new THREE.Group(); g.name = "outside";
    const rand = rng(7);
    const z = bz - 3;
    const add = (m: THREE.Object3D) => g.add(m);
    if (s.outside === "hills") {
      [[-4, 0x2c3d57, 2.6], [1.5, 0x34486a, 3.2], [6, 0x2a3a55, 2.2]].forEach(([x, c, r], i) => { const m = new THREE.Mesh(new THREE.SphereGeometry(r as number, 20, 12), mat(c as number)); m.position.set(wx + (x as number), -0.6, z - i); add(m); });
    } else if (s.outside === "trees") {
      for (let i = 0; i < 22; i++) { const tx = wx + (rand() - 0.5) * 9, tz = z - rand() * 4, th = 1.4 + rand() * 1.4;
        const tr = new THREE.Mesh(new THREE.ConeGeometry(0.5 + rand() * 0.3, th, 6), mat(0x1f4d36 + Math.floor(rand() * 0x101000))); tr.position.set(tx, th / 2 - 0.3, tz); add(tr); }
    } else {
      for (let i = 0; i < 18; i++) { const bw = 0.5 + rand() * 0.7, bh = 1 + rand() * 3, m = box(bw, bh, 0.5, s.outside === "city" ? 0x23304a : 0x6b5a4c, wx + (i - 9) * 0.7, bh / 2 - 0.4, z - rand() * 2);
        add(m);
        if (s.outside === "city") for (let k = 0; k < 4; k++) { const wn = box(0.08, 0.1, 0.02, 0xffd98a, m.position.x + (rand() - 0.5) * bw * 0.7, m.position.y + (rand() - 0.5) * bh * 0.8, m.position.z + 0.27, { emissive: 0xffd98a, emissiveIntensity: 1.4 }); wn.userData.night = true; add(wn); } }
    }
    this.root.add(g);
  }

  /** (Re)creates the sky backdrop + stars; cheap, called when the time of day changes. */
  private rebuildSkyOnly(): void {
    this.root.getObjectByName("sky")?.removeFromParent();
    if (this.stars) { this.stars.removeFromParent(); this.stars = null; }
    const tod = this.env?.time_of_day ?? "night", sky = SKY[tod];
    const g = new THREE.Group(); g.name = "sky";
    const dome = new THREE.Mesh(new THREE.PlaneGeometry(60, 30), new THREE.MeshBasicMaterial({ color: sky.sky, fog: false }));
    dome.position.set(0, 6, ROOM.back - 8); g.add(dome);
    if (sky.stars) {
      const rand = rng(11), pos = new Float32Array(300 * 3);
      for (let i = 0; i < 300; i++) { pos[i * 3] = (rand() - 0.5) * 40; pos[i * 3 + 1] = 2 + rand() * 10; pos[i * 3 + 2] = ROOM.back - 7.5; }
      const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      this.stars = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.06, fog: false })); g.add(this.stars);
    }
    this.root.add(g);
    this.root.getObjectByName("outside")?.traverse((o) => { if (o.userData.night) o.visible = tod !== "day"; });
  }

  private buildFireplace(s: PresetStyle, x: number, z: number): void {
    const g = new THREE.Group();
    const stone = 0x6e6a70;
    g.add(box(1.3, 1.1, 0.5, stone, x, 0.55, z), box(1.5, 0.1, 0.62, s.wood, x, 1.15, z));
    const hole = box(0.8, 0.62, 0.3, 0x1a1210, x, 0.4, z + 0.16); g.add(hole);
    for (let i = 0; i < 3; i++) { const f = new THREE.Mesh(new THREE.ConeGeometry(0.16 - i * 0.03, 0.42 - i * 0.06, 5),
      new THREE.MeshBasicMaterial({ color: [0xff6a1f, 0xffa133, 0xffd86b][i], transparent: true, opacity: 0.92, blending: THREE.AdditiveBlending, depthWrite: false }));
      f.position.set(x + (i - 1) * 0.16, 0.42 + i * 0.03, z + 0.2); this.flames.push(f); g.add(f); }
    g.add(box(0.6, 0.07, 0.07, 0x4a2f1c, x, 0.2, z + 0.22));
    this.fireLight.position.set(x, 0.6, z + 0.55);
    this.pickable(g, "fireplace"); this.root.add(g);
  }

  private buildDesk(s: PresetStyle, x: number, z: number): void {
    const g = new THREE.Group();
    g.add(box(1.5, 0.06, 0.75, s.wood, x, 0.74, z));
    [[-0.68, -0.32], [0.68, -0.32], [-0.68, 0.32], [0.68, 0.32]].forEach(([dx, dz]) => g.add(box(0.06, 0.72, 0.06, s.wood, x + dx, 0.36, z + dz)));
    g.add(box(0.42, 0.03, 0.3, 0x2a2a30, x + 0.1, 0.78, z), box(0.42, 0.28, 0.02, 0x3b4a66, x + 0.1, 0.93, z - 0.15, { emissive: 0x4d6fb8, emissiveIntensity: 0.35 }));
    g.add(box(0.28, 0.05, 0.2, 0xe9e1cf, x - 0.45, 0.8, z + 0.05), box(0.16, 0.12, 0.16, s.accent, x + 0.55, 0.83, z + 0.12)); // book + mug
    g.add(box(0.5, 0.05, 0.5, s.accent, x, 0.45, z + 0.65), box(0.5, 0.45, 0.05, s.accent, x, 0.7, z + 0.9)); // chair
    this.root.add(g);
  }
  private buildShelf(s: PresetStyle, x: number, z: number): void {
    const g = new THREE.Group(); const rand = rng(5);
    g.add(box(0.35, 2.0, 1.2, s.wood, x, 1.0, z));
    for (let row = 0; row < 4; row++) for (let i = 0; i < 6; i++) g.add(box(0.2, 0.28 + rand() * 0.1, 0.07, [0xd96c6c, 0x6c9bd9, 0xe3c46b, 0x7cc59a, 0xb08ae0][Math.floor(rand() * 5)], x + 0.06, 0.3 + row * 0.45, z - 0.5 + i * 0.19));
    this.root.add(g);
  }
  private buildCounter(s: PresetStyle, x: number, z: number): void {
    const g = new THREE.Group();   // along the left wall so it never blocks the window
    g.add(box(0.6, 1.0, 2.4, s.wood, x, 0.5, z), box(0.7, 0.06, 2.5, 0xe8dcc8, x, 1.03, z));
    for (let i = 0; i < 4; i++) g.add(box(0.1, 0.1, 0.1, 0xffffff, x + 0.05, 1.12, z - 0.8 + i * 0.5));
    g.add(box(0.3, 0.35, 0.5, 0x3a3a3a, x - 0.05, 1.22, z + 0.85));
    this.root.add(g);
  }
  private addPendant(x: number): void {
    const c = box(0.02, 0.8, 0.02, 0x222222, x, ROOM.h - 0.4, ROOM.back + 1.5); const b = new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffe2a8 }));
    b.position.set(x, ROOM.h - 0.85, ROOM.back + 1.5); this.root.add(c, b);
  }
  private buildLamp(s: PresetStyle, x: number, z: number): void {
    const g = new THREE.Group();
    const onDesk = s.props.includes("desk"), by = onDesk ? 0.77 : 0;
    g.add(box(0.14, 0.03, 0.14, 0x2a2a2a, x - 0.55, by + 0.02, z - 0.1), box(0.03, 0.4, 0.03, 0x2a2a2a, x - 0.55, by + 0.22, z - 0.1));
    const bulb = new THREE.Mesh(new THREE.ConeGeometry(0.14, 0.18, 12, 1, true), new THREE.MeshStandardMaterial({ color: s.accent, emissive: 0xffd29a, emissiveIntensity: 1, side: THREE.DoubleSide }));
    bulb.position.set(x - 0.55, by + 0.46, z - 0.1); this.lampBulb = bulb; g.add(bulb);
    this.lampLight.position.set(x - 0.55, by + 0.42, z - 0.05);
    this.pickable(g, "lamp"); this.root.add(g);
  }

  // ------------------------------------------------------------------ environment
  private applyEnvironment(): void {
    const env = this.env!, sky = SKY[env.time_of_day];
    this.ambient.color.set(sky.ambient); this.ambient.intensity = sky.ambientI;
    this.sun.color.set(sky.sun); this.sun.intensity = sky.sunI; this.sun.position.set(-3, 5, 2);
    this.scene.background = new THREE.Color(sky.sky);
    this.scene.fog = env.fog > 0.02 ? new THREE.FogExp2(sky.sky, 0.02 + env.fog * 0.06) : null;
    this.fireLight.visible = env.fireplace;
    this.flames.forEach((f) => (f.visible = env.fireplace));
    this.lampLight.visible = env.lamp;
    if (this.lampBulb) (this.lampBulb.material as THREE.MeshStandardMaterial).emissiveIntensity = env.lamp ? 1.1 : 0;
    if (this.rain) this.rain.geometry.setDrawRange(0, Math.floor(env.rain * RAIN_MAX) * 2);
    if (this.rain) (this.rain.material as THREE.LineBasicMaterial).color.set(env.time_of_day === "night" ? 0x9fb4e8 : 0xcfdcf5);
  }

  private buildRain(wx: number, ww: number, bz: number): void {
    const rand = rng(3), seeds = new Float32Array(RAIN_MAX * 4);
    for (let i = 0; i < RAIN_MAX; i++) { seeds[i * 4] = wx + (rand() - 0.5) * (ww + 6); seeds[i * 4 + 1] = rand(); seeds[i * 4 + 2] = bz - 0.3 - rand() * 4.5; seeds[i * 4 + 3] = 0.8 + rand() * 0.6; }
    this.rainSeeds = seeds;
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(RAIN_MAX * 6), 3));
    this.rain = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x9fb4e8, transparent: true, opacity: 0.55, fog: false }));
    this.rain.frustumCulled = false; this.root.add(this.rain);
  }

  private updateRain(t: number, env: Environment3D): void {
    if (!this.rain) return;
    const pos = (this.rain.geometry.getAttribute("position") as THREE.BufferAttribute), arr = pos.array as Float32Array, s = this.rainSeeds;
    const H = 8, slant = env.wind * 0.5, speed = 7 + env.rain * 6, n = Math.floor(env.rain * RAIN_MAX);
    for (let i = 0; i < n; i++) {
      const x = s[i * 4], z = s[i * 4 + 2], v = s[i * 4 + 3];
      let vs = speed * v;
      if (this.loopLen) vs = Math.max(1, Math.round(this.loopLen * vs / H)) * H / this.loopLen;   // whole number of falls per loop
      const y = ((s[i * 4 + 1] * H - t * vs) % H + H) % H - 0.5;
      const len = 0.25 + env.rain * 0.25;
      const o = i * 6; arr[o] = x + slant * (y / H) * 3; arr[o + 1] = y; arr[o + 2] = z; arr[o + 3] = arr[o] - slant * 0.12; arr[o + 4] = y + len; arr[o + 5] = z;
    }
    pos.needsUpdate = true;
  }

  // ------------------------------------------------------------------ character
  private async buildCharacter(cfg: Scene3D, url: string | null, token: number): Promise<void> {
    const c = cfg.character;
    this.charGroup = new THREE.Group();
    this.charGroup.position.set(...c.position);
    this.charGroup.rotation.y = THREE.MathUtils.degToRad(c.rotation_y);
    let clipNames: string[] = [], isPlaceholder = true;
    if (url) {
      try {
        const gltf = await new GLTFLoader().loadAsync(url);
        if (token !== this.loadToken) return;
        const model = gltf.scene;
        const box3 = new THREE.Box3().setFromObject(model), size = box3.getSize(new THREE.Vector3());
        const k = (1.1 * c.scale) / Math.max(0.001, size.y);
        model.scale.setScalar(k);
        const b2 = new THREE.Box3().setFromObject(model);
        model.position.y -= b2.min.y; model.position.x -= (b2.min.x + b2.max.x) / 2; model.position.z -= (b2.min.z + b2.max.z) / 2;
        this.charGroup.add(model);
        this.pickable(this.charGroup, "character");
        gltf.animations.forEach((a) => this.clips.set(a.name || `clip_${this.clips.size}`, a));
        clipNames = [...this.clips.keys()];
        if (clipNames.length) {
          this.mixer = new THREE.AnimationMixer(model);
          const r = c.reactions, env = cfg.environment;
          const ambient = !this.stateMode ? null
            : (!env.fireplace && r.fire_out && this.clips.get(r.fire_out)) || (env.rain >= 0.7 && r.rain_heavy && this.clips.get(r.rain_heavy)) || null;
          const idle = ambient || (c.idle_animation && this.clips.get(c.idle_animation)) || this.clips.get(clipNames.find((n) => /idle|breath|stand/i.test(n)) ?? clipNames[0])!;
          this.idleAction = this.mixer.clipAction(idle).play();
        }
        isPlaceholder = false;
      } catch (e) {
        console.error("Không tải được model 3D", e);
      }
    }
    if (isPlaceholder) this.buildPlaceholder();
    this.scene.add(this.charGroup);
    this.opts.onReady?.({ clips: clipNames, placeholder: isPlaceholder });
  }

  /** Built-in stand-in character: a round bear-like figure. Not a user asset; replaced by a .glb when chosen. */
  private buildPlaceholder(): void {
    const accent = STYLES[this.cfg!.preset].accent, fur = 0xc99a6b;
    const g = this.charGroup, sc = this.cfg!.character.scale;
    const body = new THREE.Group(), head = new THREE.Group(), arm = new THREE.Group();
    const sph = (r: number, color: number) => new THREE.Mesh(new THREE.SphereGeometry(r, 20, 14), mat(color, { flatShading: false }));
    const torso = sph(0.3, fur); torso.scale.set(1, 1.15, 0.9); torso.position.y = 0.4; body.add(torso);
    const belly = sph(0.2, 0xf1dcc0); belly.position.set(0, 0.38, 0.17); belly.scale.set(1, 1.1, 0.6); body.add(belly);
    const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.05, 8, 20), mat(accent)); scarf.rotation.x = Math.PI / 2; scarf.position.y = 0.68; body.add(scarf);
    [-0.14, 0.14].forEach((x) => { const f = sph(0.09, fur); f.position.set(x, 0.07, 0.08); f.scale.set(1, 0.7, 1.3); body.add(f); });
    const skull = sph(0.26, fur); head.add(skull);
    [-0.19, 0.19].forEach((x) => { const e = sph(0.09, fur); e.position.set(x, 0.22, 0); head.add(e); const ei = sph(0.05, 0xf1b6a8); ei.position.set(x, 0.22, 0.05); head.add(ei); });
    const muzzle = sph(0.1, 0xf1dcc0); muzzle.position.set(0, -0.06, 0.22); muzzle.scale.set(1.2, 0.8, 0.8); head.add(muzzle);
    const nose = sph(0.03, 0x3a2a24); nose.position.set(0, -0.03, 0.31); head.add(nose);
    const eyes = [-0.09, 0.09].map((x) => { const e = sph(0.03, 0x1e1a1a); e.position.set(x, 0.05, 0.235); head.add(e); return e; });
    head.position.y = 0.98; body.add(head);
    const upper = sph(0.075, fur); upper.scale.set(1, 1.6, 1); upper.position.y = -0.09; arm.add(upper); arm.position.set(0.28, 0.62, 0); body.add(arm);
    const armL = sph(0.075, fur); armL.scale.set(1, 1.6, 1); armL.position.set(-0.3, 0.5, 0); armL.rotation.z = 0.25; body.add(armL);
    g.add(body); g.scale.setScalar(sc);
    this.placeholder = { body, head, arm, eyes };
    this.pickable(g, "character");
  }

  private updatePlaceholder(dt: number, t: number, env: Environment3D): void {
    const p = this.placeholder; if (!p) return;
    let hop = 0, wave = 0, m = 0;     // m = 0..1 reaction envelope (eases in and out, so it never snaps)
    if (this.reactionT >= 0) {
      this.reactionT += dt; const k = this.reactionT;
      if (k > 1.6) this.reactionT = -1;
      else { m = Math.min(1, k / 0.2, (1.6 - k) / 0.3); hop = Math.abs(Math.sin(k * Math.PI * 2)) * 0.12 * m; wave = Math.sin(k * 14) * 0.5 + 1.6; }
    }
    const coldWant = env.fireplace ? 0 : 1;                  // fire out: hunches and shivers
    this.cold += (coldWant - this.cold) * Math.min(1, dt * 2.5);
    p.body.position.y = hop + Math.sin(t * this.w(1.6)) * 0.012;
    p.body.position.x = this.cold * Math.sin(t * this.w(22)) * 0.006;
    p.head.position.y = 0.98 - 0.06 * this.cold;
    const rest = -0.25 + Math.sin(t * this.w(1.6)) * 0.04;
    p.arm.rotation.z = rest * (1 - m) + -wave * m;
    const want = env.rain >= 0.7 ? 1 : 0;                    // heavy rain: looks toward the window
    this.lookWindow += (want - this.lookWindow) * Math.min(1, dt * 2.5);
    p.head.rotation.y = this.lookWindow * 0.6 + Math.sin(t * this.w(0.5)) * 0.05;
    p.head.rotation.z = Math.sin(t * this.w(0.9)) * 0.03;
    const period = this.loopLen ? this.loopLen / Math.max(1, Math.round(this.loopLen / 4.2)) : 4.2;
    const blink = (t % period) < 0.12 ? 0.1 : 1;            // deterministic blink every ~4.2 s
    p.eyes.forEach((e) => (e.scale.y = blink));
  }

  // ------------------------------------------------------------------ camera + picking
  private applyCamera(pos: [number, number, number], target: [number, number, number], fov: number): void {
    this.camera.position.set(...pos); this.camera.fov = fov; this.camera.updateProjectionMatrix();
    if (this.controls) { this.controls.target.set(...target); this.controls.update(); } else this.camera.lookAt(...target);
  }
  private pickAt(e: PointerEvent): PickTarget | null {
    const r = this.canvas.getBoundingClientRect();
    this.raycaster.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), this.camera);
    const hit = this.raycaster.intersectObjects(this.pickables, true)[0];
    let o: THREE.Object3D | null = hit?.object ?? null;
    while (o) { if (o.userData.pick) return o.userData.pick as PickTarget; o = o.parent; }
    return null;
  }
  private downAt = { x: 0, y: 0 };
  private onDown = (e: PointerEvent) => {
    this.downAt = { x: e.clientX, y: e.clientY };
    const up = (u: PointerEvent) => {
      this.canvas.removeEventListener("pointerup", up);
      if (Math.hypot(u.clientX - this.downAt.x, u.clientY - this.downAt.y) > 5) return;   // it was an orbit drag
      this.onClick(this.pickAt(u));
    };
    this.canvas.addEventListener("pointerup", up);
  };
  private onMove = (e: PointerEvent) => {
    const t = this.pickAt(e);
    if (t !== this.hover) { this.hover = t; this.canvas.style.cursor = t ? "pointer" : "grab"; this.opts.onHover?.(t); }
  };
  private onClick(t: PickTarget | null): void {
    this.opts.onPick?.(t);
    if (!t || !this.env) return;
    const env = { ...this.env };
    if (t === "window") env.rain = env.rain > 0.05 ? 0 : 0.85;
    else if (t === "fireplace") env.fireplace = !env.fireplace;
    else if (t === "lamp") env.lamp = !env.lamp;
    else { this.trigger("click"); return; }
    this.setEnvironment(env);
    this.opts.onEnvChange?.(env);
  }
}
