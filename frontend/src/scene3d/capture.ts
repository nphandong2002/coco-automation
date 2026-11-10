/**
 * Headless capture entry (capture.html). The render worker (Python + Chromium) drives it frame by
 * frame so the exact same scene engine that the dashboard shows is what gets rendered.
 *
 *   await coco3d.init({scene, modelUrl, width, height, loopSeconds})  -> {loopSeconds, placeholder, clips}
 *   coco3d.frame(dt, first)                                            -> base64 JPEG of the next frame
 */
import { SceneEngine } from "./engine";
import type { Scene3D } from "./types";

interface InitOptions { scene: Scene3D; modelUrl: string | null; width: number; height: number; loopSeconds: number }
interface InitResult { loopSeconds: number; placeholder: boolean; clips: string[] }

let engine: SceneEngine | null = null;

const api = {
  async init(o: InitOptions): Promise<InitResult> {
    const canvas = document.getElementById("c") as HTMLCanvasElement;
    engine?.dispose();
    let info: { clips: string[]; placeholder: boolean } = { clips: [], placeholder: true };
    engine = new SceneEngine(canvas, { interactive: false, preserveDrawingBuffer: true, pixelRatio: 1, onReady: (i) => { info = i; } });
    engine.resize(o.width, o.height);
    await engine.setScene(o.scene, o.modelUrl);
    // a .glb idle clip loops by itself: make the whole loop a whole number of idle cycles
    const idle = engine.idleDuration();
    let L = o.loopSeconds;
    if (idle && idle > 0.2) L = Math.max(1, Math.round(L / idle)) * idle;
    engine.setLoop(L);
    return { loopSeconds: L, placeholder: info.placeholder, clips: info.clips };
  },
  /** Advance by `dt` (not for the very first frame) and return the frame as base64 JPEG. */
  frame(dt: number, first: boolean): string {
    if (!engine) throw new Error("coco3d.init() not called");
    engine.advance(first ? 0 : dt);
    engine.render();
    const url = (document.getElementById("c") as HTMLCanvasElement).toDataURL("image/jpeg", 0.95);
    return url.slice(url.indexOf(",") + 1);
  },
};

declare global { interface Window { coco3d: typeof api; __coco3dReady?: boolean } }
window.coco3d = api;
window.__coco3dReady = true;
