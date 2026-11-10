/**
 * Original seated "study buddy" (a round bear) with a deterministic study routine:
 * write -> glance around -> write -> turn a page -> read -> sip a drink -> write.
 * Every pose is a function of the loop phase, so a rendered loop repeats exactly.
 */
import * as THREE from "three";

interface Pose {
  t: number;                         // 0..1 position in the routine
  pitch: number; yaw: number;        // head
  lean: number;                      // torso forward lean
  rs: number; re: number; rz: number;  // right arm: shoulder pitch, elbow, abduction
  ls: number; le: number; lz: number;  // left arm
  write: number;                     // 0..1 pencil scribbling amount
}
const P = (t: number, pitch: number, yaw: number, lean: number, r: [number, number, number], l: [number, number, number], write = 0): Pose =>
  ({ t, pitch, yaw, lean, rs: r[0], re: r[1], rz: r[2], ls: l[0], le: l[1], lz: l[2], write });

const WRITE_R: [number, number, number] = [-1.0, -0.75, -0.12], REST_L: [number, number, number] = [-0.95, -0.7, 0.14];
const ROUTINE: Pose[] = [
  P(0.00, 0.42, 0.00, 0.10, WRITE_R, REST_L, 1),
  P(0.24, 0.45, 0.04, 0.10, WRITE_R, REST_L, 1),
  P(0.29, 0.00, 0.55, 0.00, [-0.8, -0.9, -0.12], REST_L, 0),        // glance up and to the side
  P(0.37, 0.02, 0.45, 0.00, [-0.8, -0.9, -0.12], REST_L, 0),
  P(0.43, 0.40, 0.00, 0.10, WRITE_R, REST_L, 1),
  P(0.52, 0.44, 0.02, 0.10, WRITE_R, REST_L, 1),
  P(0.56, 0.38, -0.05, 0.12, [-0.9, -0.8, -0.12], [-1.45, -0.35, 0.32], 0),   // left hand lifts to turn the page
  P(0.60, 0.36, -0.08, 0.12, [-0.9, -0.8, -0.12], [-1.25, -0.9, -0.22], 0),   // ...and sweeps across
  P(0.64, 0.50, 0.00, 0.14, [-0.95, -0.75, -0.1], REST_L, 0),                  // read
  P(0.77, 0.52, 0.03, 0.14, [-0.95, -0.75, -0.1], REST_L, 0),
  P(0.82, 0.10, 0.00, 0.02, [-1.9, -1.55, -0.05], REST_L, 0),                  // sip
  P(0.88, 0.05, 0.00, 0.00, [-1.9, -1.55, -0.05], REST_L, 0),
  P(0.93, 0.40, 0.00, 0.10, WRITE_R, REST_L, 1),
  P(1.00, 0.42, 0.00, 0.10, WRITE_R, REST_L, 1),
];

const ss = (x: number) => x * x * (3 - 2 * x);
function sample(frac: number): Pose {
  let i = 0;
  while (i < ROUTINE.length - 2 && frac >= ROUTINE[i + 1].t) i++;
  const a = ROUTINE[i], b = ROUTINE[i + 1], k = ss(Math.min(1, Math.max(0, (frac - a.t) / (b.t - a.t))));
  const m = (x: number, y: number) => x + (y - x) * k;
  return { t: frac, pitch: m(a.pitch, b.pitch), yaw: m(a.yaw, b.yaw), lean: m(a.lean, b.lean),
    rs: m(a.rs, b.rs), re: m(a.re, b.re), rz: m(a.rz, b.rz), ls: m(a.ls, b.ls), le: m(a.le, b.le), lz: m(a.lz, b.lz), write: m(a.write, b.write) };
}

export interface StudentInputs {
  t: number; loopLen: number | null; w: (f: number) => number;
  reaction: number;      // 0..1 envelope of a one-shot reaction (stretch + yawn)
  look: number;          // 0..1 listening to heavy rain: looks aside more
  cold: number;          // 0..1 hunched and shivering
}

export class Student {
  readonly group = new THREE.Group();
  private torso: THREE.Mesh;
  private head = new THREE.Group();
  private eyes: THREE.Mesh[] = [];
  private mouth: THREE.Mesh;
  private body = new THREE.Group();
  private arm: { r: THREE.Group; re: THREE.Group; l: THREE.Group; le: THREE.Group };

  constructor(accent: number, scale = 1.15) {
    const fur = 0xc99a6b, belly = 0xf1dcc0;
    const sph = (r: number, c: number) => new THREE.Mesh(new THREE.SphereGeometry(r, 22, 16), new THREE.MeshStandardMaterial({ color: c, roughness: 0.9 }));
    this.torso = sph(0.3, fur); this.torso.scale.set(1, 1.1, 0.9); this.torso.position.y = 0.38; this.body.add(this.torso);
    const bl = sph(0.2, belly); bl.scale.set(1, 1.1, 0.5); bl.position.set(0, 0.36, 0.19); this.body.add(bl);
    const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.05, 10, 22), new THREE.MeshStandardMaterial({ color: accent, roughness: 0.8 }));
    scarf.rotation.x = Math.PI / 2; scarf.position.y = 0.66; this.body.add(scarf);
    // head
    const skull = sph(0.27, fur); this.head.add(skull);
    [-0.2, 0.2].forEach((x) => { const e = sph(0.09, fur); e.position.set(x, 0.22, 0); this.head.add(e); const ei = sph(0.05, 0xf1b6a8); ei.position.set(x, 0.22, 0.05); this.head.add(ei); });
    const muzzle = sph(0.11, belly); muzzle.position.set(0, -0.07, 0.22); muzzle.scale.set(1.2, 0.8, 0.8); this.head.add(muzzle);
    const nose = sph(0.032, 0x3a2a24); nose.position.set(0, -0.035, 0.32); this.head.add(nose);
    this.mouth = sph(0.045, 0x6b2f2a); this.mouth.position.set(0, -0.12, 0.3); this.mouth.scale.set(1, 0, 0.5); this.head.add(this.mouth);
    this.eyes = [-0.1, 0.1].map((x) => { const e = sph(0.034, 0x1e1a1a); e.position.set(x, 0.05, 0.245); this.head.add(e); return e; });
    [-0.15, 0.15].forEach((x) => { const c = sph(0.04, 0xf2a79a); c.position.set(x, -0.04, 0.23); c.scale.set(1, 0.6, 0.4); this.head.add(c); });
    this.head.position.y = 0.93; this.body.add(this.head);
    // arms: shoulder pivot -> upper arm -> elbow pivot -> forearm + hand (+ pencil in the right hand)
    const mkArm = (side: 1 | -1, withPencil: boolean) => {
      const sh = new THREE.Group(); sh.position.set(0.28 * side, 0.6, 0.04);
      const up = sph(0.075, fur); up.scale.set(1, 1.7, 1); up.position.y = -0.1; sh.add(up);
      const el = new THREE.Group(); el.position.y = -0.2; sh.add(el);
      const fo = sph(0.07, fur); fo.scale.set(1, 1.7, 1); fo.position.y = -0.1; el.add(fo);
      const hand = sph(0.075, fur); hand.position.y = -0.21; el.add(hand);
      if (withPencil) {
        const pen = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.2, 8), new THREE.MeshStandardMaterial({ color: 0xf2c94c }));
        pen.position.set(0, -0.27, 0.05); pen.rotation.x = -0.9; el.add(pen);
        const tip = new THREE.Mesh(new THREE.ConeGeometry(0.012, 0.04, 8), new THREE.MeshStandardMaterial({ color: 0x333333 }));
        tip.position.set(0, -0.35, 0.115); tip.rotation.x = -0.9 + Math.PI; el.add(tip);
      }
      this.body.add(sh);
      return { sh, el };
    };
    const r = mkArm(1, true), l = mkArm(-1, false);
    this.arm = { r: r.sh, re: r.el, l: l.sh, le: l.el };
    this.group.add(this.body);
    this.group.scale.setScalar(scale);
    this.group.traverse((o) => { o.castShadow = true; o.receiveShadow = true; });
  }

  animate(i: StudentInputs): void {
    const { t, loopLen, w } = i;
    const period = loopLen ?? 24;                      // one routine per loop (or per 24 s in the live viewer)
    const frac = ((t % period) + period) % period / period;
    const p = sample(frac);
    const m = i.reaction;                              // stretch / yawn overrides the routine while it plays
    const wr = p.write * (1 - m), wig = Math.sin(t * w(5.2));
    const hunch = i.cold;
    this.body.position.x = hunch * Math.sin(t * w(22)) * 0.006;
    this.body.rotation.x = (p.lean + 0.08 * hunch) * (1 - m * 0.8);
    this.torso.scale.y = 1.1 + Math.sin(t * w(1.5)) * 0.012;             // breathing
    const yaw = p.yaw * (1 - m) + i.look * 0.9 * Math.max(0, Math.sin(Math.PI * Math.min(1, frac * 3)) * 0.5 + 0.5) * (1 - m);
    this.head.rotation.set(p.pitch * (1 - m) - 0.3 * m + 0.05 * hunch + Math.sin(t * w(1.1)) * 0.015, yaw, Math.sin(t * w(0.9)) * 0.02);
    const mix = (a: number, b: number) => a * (1 - m) + b * m;
    this.arm.r.rotation.set(mix(p.rs + wr * wig * 0.05, -3.0), 0, mix(p.rz, -0.55));
    this.arm.re.rotation.set(mix(p.re + wr * Math.sin(t * w(5.2) + 1.3) * 0.09, -0.2), 0, 0);
    this.arm.l.rotation.set(mix(p.ls, -3.0), 0, mix(p.lz, 0.55));
    this.arm.le.rotation.set(mix(p.le, -0.2), 0, 0);
    const period2 = loopLen ? loopLen / Math.max(1, Math.round(loopLen / 4.4)) : 4.4;
    const blink = (t % period2) < 0.12 ? 0.1 : 1;
    this.eyes.forEach((e) => (e.scale.y = blink));
    this.mouth.scale.y = m > 0.15 ? 1.4 * m : 0;                          // yawn
  }
}
