/**
 * Headless capture entry (capture.html). The render worker (Python + Chromium) drives it frame by
 * frame so the exact same scene engine that the dashboard shows is what gets rendered.
 *
 *   await coco3d.init({scene, modelUrl, width, height, loopSeconds})  -> {loopSeconds, placeholder, clips}
 *   coco3d.frame(dt, first)                                            -> base64 JPEG of the next frame
 */
import { SceneEngine } from "./engine";
import type { Scene3D } from "./types";

interface InitOptions {
  scene: Scene3D; modelUrl: string | null; width: number; height: number; loopSeconds: number;
  reserveEvent?: boolean;                      // make the loop long enough to hold a break_time reaction
  exactLoop?: boolean;                         // use loopSeconds as is (variant loops must match the base loop)
  event?: { name: "break_time"; at: number } | null;
}
interface InitResult { loopSeconds: number; placeholder: boolean; clips: string[]; eventFits: boolean }
const EVENT_TAIL = 1.5;   // seconds of calm after a reaction so the loop ends in the idle pose

let engine: SceneEngine | null = null;

const api = {
  async init(o: InitOptions): Promise<InitResult> {
    const canvas = document.getElementById("c") as HTMLCanvasElement;
    engine?.dispose();
    let info: { clips: string[]; placeholder: boolean } = { clips: [], placeholder: true };
    engine = new SceneEngine(canvas, { interactive: false, preserveDrawingBuffer: true, pixelRatio: 1, onReady: (i) => { info = i; } });
    engine.resize(o.width, o.height);
    engine.setStateMode(true);
    await engine.setScene(o.scene, o.modelUrl);
    // a .glb idle clip loops by itself: make the whole loop a whole number of idle cycles
    const idle = engine.idleDuration();
    const reaction = engine.reactionDuration("break_time") ?? 0;
    const needed = o.reserveEvent || o.event ? reaction + (o.event?.at ?? 0.5) + EVENT_TAIL : 0;
    let L = o.loopSeconds;
    if (!o.exactLoop) {
      const target = Math.max(L, needed);
      L = idle && idle > 0.2 ? Math.max(1, (needed > L ? Math.ceil : Math.round)(target / idle - 1e-6)) * idle : target;
    }
    engine.setLoop(L);
    const fits = !o.event || (reaction > 0 && needed <= L + 1e-6);
    if (o.event && fits) engine.scheduleEvent(o.event.name, o.event.at);
    return { loopSeconds: L, placeholder: info.placeholder, clips: info.clips, eventFits: fits };
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
