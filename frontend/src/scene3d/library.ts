/** "Library" scene: an original cozy study library seen from a raised, dollhouse-style camera. */
import * as THREE from "three";
import type { PickTarget } from "./types";
import { beamTexture, box, flagstoneTexture, mat, plankTexture, rng, rugTexture, wallTexture } from "./look";

export const LIB_ROOM = { w: 7.2, d: 6.0, h: 3.4, back: -3 };

export interface LibCtx {
  root: THREE.Group;
  pickable: (obj: THREE.Object3D, target: PickTarget) => void;
  noCast: (obj: THREE.Object3D) => void;       // structure that must not shadow the room (walls)
}
export interface LibResult {
  seat: THREE.Vector3;                          // where the student sits (world)
  lampPos: THREE.Vector3;
  rain: { x: number; width: number; y: number; z: number };
}

const BOOK_COLORS = [0xb4483f, 0x3f6fa8, 0x4f8a5b, 0xd6a043, 0xe8dcc4, 0x7a4d8e, 0xc9693c, 0x2f4f6f, 0x8a6a45, 0xd98a9a];

function bookshelf(ctx: LibCtx, wood: number, length: number, height: number, seed: number): THREE.Group {
  const g = new THREE.Group(), rand = rng(seed), depth = 0.5, rows = 5;
  g.add(box(length, height, 0.06, 0x6b4527, 0, height / 2, -depth / 2 + 0.03));                 // back panel
  [-length / 2, length / 2].forEach((x) => g.add(box(0.07, height, depth, wood, x, height / 2, 0)));
  const rowH = (height - 0.12) / rows;
  for (let i = 0; i <= rows; i++) g.add(box(length, 0.06, depth, wood, 0, 0.06 + i * rowH, 0));
  g.add(box(length + 0.1, 0.08, depth + 0.1, wood, 0, height + 0.04, 0));                       // crown
  const books: { x: number; y: number; w: number; h: number; d: number; c: number }[] = [];
  for (let r = 0; r < rows; r++) {
    let x = -length / 2 + 0.1;
    const base = 0.09 + r * rowH;
    while (x < length / 2 - 0.2) {
      if (rand() < 0.07) { x += 0.18 + rand() * 0.18; continue; }                                 // gap
      const w = 0.05 + rand() * 0.07, h = rowH * (0.62 + rand() * 0.3), d = 0.28 + rand() * 0.1;
      books.push({ x: x + w / 2, y: base + h / 2, w, h, d, c: BOOK_COLORS[Math.floor(rand() * BOOK_COLORS.length)] });
      x += w + 0.004;
    }
  }
  const inst = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial({ roughness: 0.8, flatShading: true }), books.length);
  const m4 = new THREE.Matrix4(), col = new THREE.Color();
  books.forEach((b, i) => {
    m4.compose(new THREE.Vector3(b.x, b.y, 0.02), new THREE.Quaternion(), new THREE.Vector3(b.w, b.h, b.d));
    inst.setMatrixAt(i, m4); inst.setColorAt(i, col.setHex(b.c));
  });
  g.add(inst);
  void ctx;
  return g;
}

function pottedPlant(x: number, z: number, s: number, seed: number): THREE.Group {
  const g = new THREE.Group(), rand = rng(seed);
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.2 * s, 0.15 * s, 0.3 * s, 14), mat(0xc2703d, { flatShading: false }));
  pot.position.y = 0.15 * s; g.add(pot);
  for (let i = 0; i < 9; i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry((0.13 + rand() * 0.07) * s, 10, 8), mat([0x4f9a52, 0x5fae5a, 0x3f8a4a][i % 3], { flatShading: false }));
    leaf.scale.y = 1.4; leaf.position.set((rand() - 0.5) * 0.3 * s, (0.5 + rand() * 0.5) * s, (rand() - 0.5) * 0.3 * s); g.add(leaf);
  }
  g.position.set(x, 0, z);
  return g;
}

export function buildLibrary(ctx: LibCtx): LibResult {
  const { w, d, h, back } = LIB_ROOM, r = ctx.root, wall = 0xf0dfc2;
  // ---- floor (flagstones) and a round rug
  const floor = new THREE.Mesh(new THREE.BoxGeometry(w, 0.1, d), new THREE.MeshStandardMaterial({ map: flagstoneTexture(0xd9a46a, [w / 2.4, d / 2.4]), roughness: 0.9 }));
  floor.position.set(0, -0.05, back + d / 2); r.add(floor);
  const rug = new THREE.Mesh(new THREE.CircleGeometry(1.5, 48), new THREE.MeshStandardMaterial({ map: rugTexture(0xb9503f, 0xf0d9a0), roughness: 1 }));
  rug.rotation.x = -Math.PI / 2; rug.position.set(0.2, 0.012, 1.5); r.add(rug);

  // ---- walls (side walls + back wall with three grid windows). No ceiling and no front wall: open to the camera.
  const wallMat = () => new THREE.MeshStandardMaterial({ map: wallTexture(wall, [3, 1.5]), roughness: 0.95 });
  const wallBox = (bw: number, bh: number, bd: number, x: number, y: number, z: number) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), wallMat()); m.position.set(x, y, z); ctx.noCast(m); r.add(m); return m;
  };
  wallBox(0.1, h, d, -w / 2, h / 2, back + d / 2); wallBox(0.1, h, d, w / 2, h / 2, back + d / 2);
  const winX = [-2.3, 0, 2.3], winW = 1.5, winH = 1.8, sill = 1.0, wt = 0.14;
  wallBox(w, sill, wt, 0, sill / 2, back); wallBox(w, h - (sill + winH), wt, 0, sill + winH + (h - sill - winH) / 2, back);
  const edges = [-w / 2, ...winX.flatMap((x) => [x - winW / 2, x + winW / 2]), w / 2];
  for (let i = 0; i < edges.length; i += 2) wallBox(edges[i + 1] - edges[i], winH, wt, (edges[i] + edges[i + 1]) / 2, sill + winH / 2, back);
  // wainscot
  [[0, back + 0.1, w, 0.05], [-w / 2 + 0.08, back + d / 2, 0.05, d], [w / 2 - 0.08, back + d / 2, 0.05, d]].forEach(([x, z, bw, bd]) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(bw, 0.85, bd), new THREE.MeshStandardMaterial({ map: plankTexture(0xa56d3e, [bw > bd ? bw / 1.4 : 1, bw > bd ? 1 : bd / 1.4]), roughness: 0.85 }));
    m.position.set(x, 0.425, z); ctx.noCast(m); r.add(m);
  });
  r.add(box(w, 0.06, 0.12, 0x6b4527, 0, 0.88, back + 0.1));

  // ---- windows: frame, mullion grid, pickable glass, sill planter, light shaft
  winX.forEach((x, i) => {
    const y = sill + winH / 2, f = 0x7a4a2a;
    r.add(box(winW + 0.16, 0.08, 0.2, f, x, sill + winH + 0.04, back + 0.03), box(winW + 0.2, 0.1, 0.28, f, x, sill - 0.05, back + 0.08));
    r.add(box(0.08, winH, 0.2, f, x - winW / 2, y, back + 0.03), box(0.08, winH, 0.2, f, x + winW / 2, y, back + 0.03));
    for (let k = 1; k < 4; k++) r.add(box(0.035, winH, 0.08, f, x - winW / 2 + (winW / 4) * k, y, back + 0.03));
    for (let k = 1; k < 5; k++) r.add(box(winW, 0.035, 0.08, f, x, sill + (winH / 5) * k, back + 0.03));
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(winW, winH), new THREE.MeshStandardMaterial({ color: 0xdff0ff, transparent: true, opacity: 0.1, roughness: 0.1 }));
    glass.position.set(x, y, back + 0.07); ctx.pickable(glass, "window"); r.add(glass);
    const planter = box(0.9, 0.16, 0.2, 0xa45f35, x, sill + 0.03, back + 0.17); r.add(planter);
    const rand = rng(40 + i);
    for (let k = 0; k < 7; k++) { const l = new THREE.Mesh(new THREE.SphereGeometry(0.09 + rand() * 0.04, 8, 6), mat([0x58a85a, 0x6dbb62, 0x4a9650][k % 3], { flatShading: false })); l.position.set(x - 0.36 + k * 0.12, sill + 0.22 + rand() * 0.06, back + 0.17); r.add(l); }
    const shaft = new THREE.Mesh(new THREE.PlaneGeometry(winW * 0.95, 4.3), new THREE.MeshBasicMaterial({ map: beamTexture(), color: 0xfff0c4, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false }));
    shaft.position.set(x + 0.25, sill + winH / 2 - 1.0, back + 1.4); shaft.rotation.x = -1.0; shaft.userData.shaft = true; ctx.noCast(shaft); r.add(shaft);
  });
  const clock = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.06, 28), mat(0xf6efe0, { flatShading: false }));
  clock.rotation.x = Math.PI / 2; clock.position.set(1.15, 2.55, back + 0.12); r.add(clock);
  r.add(box(0.02, 0.2, 0.02, 0x333333, 1.15, 2.6, back + 0.16), box(0.15, 0.02, 0.02, 0x333333, 1.2, 2.55, back + 0.16));

  // ---- bookshelves flanking the room, a rolling ladder, plants
  const sh = (x: number, rotY: number, seed: number) => { const g = bookshelf(ctx, 0x8a5a36, 4.6, 2.7, seed); g.position.set(x, 0, -0.4); g.rotation.y = rotY; r.add(g); };
  sh(-w / 2 + 0.35, Math.PI / 2, 11); sh(w / 2 - 0.35, -Math.PI / 2, 23);
  const ladder = new THREE.Group();
  [-0.22, 0.22].forEach((x) => ladder.add(box(0.05, 2.6, 0.05, 0xb98a55, x, 1.3, 0)));
  for (let k = 0; k < 8; k++) ladder.add(box(0.44, 0.04, 0.05, 0xb98a55, 0, 0.3 + k * 0.3, 0));
  ladder.position.set(w / 2 - 0.95, 0, 0.9); ladder.rotation.set(-0.18, -Math.PI / 2, 0); r.add(ladder);
  r.add(pottedPlant(-w / 2 + 0.7, back + 0.6, 1.5, 3), pottedPlant(w / 2 - 0.7, back + 0.6, 1.3, 4), pottedPlant(-2.6, 2.4, 1.1, 5));

  // ---- reading table with books, mug, plant, lamp
  const T = { x: 0, z: -0.4 };
  r.add(box(2.6, 0.07, 1.0, 0xb07a45, T.x, 0.78, T.z));
  [[-1.2, -0.4], [1.2, -0.4], [-1.2, 0.4], [1.2, 0.4]].forEach(([dx, dz]) => r.add(box(0.08, 0.76, 0.08, 0x8a5a36, T.x + dx, 0.38, T.z + dz)));
  r.add(box(0.5, 0.025, 0.36, 0xc54f43, 0.05, 0.83, T.z - 0.36), box(0.46, 0.03, 0.32, 0xf7f1e0, 0.05, 0.855, T.z - 0.36));  // open book
  r.add(box(0.4, 0.14, 0.3, 0x3f6fa8, -0.7, 0.88, T.z - 0.05), box(0.38, 0.1, 0.28, 0xd6a043, -0.7, 0.99, T.z - 0.05));          // stacked books
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.055, 0.1, 14), mat(0xf6efe0, { flatShading: false })); mug.position.set(0.55, 0.86, T.z - 0.3); r.add(mug);
  const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.045, 0.11, 12), mat(0xd97a5a, { flatShading: false })); cup.position.set(-0.2, 0.87, T.z - 0.25); r.add(cup);
  r.add(pottedPlant(1.0, T.z - 0.2, 0.45, 8).translateY(0.815));
  // lamp (pickable, drives the warm point light)
  const lamp = new THREE.Group();
  lamp.add(box(0.16, 0.03, 0.16, 0x2a4a3a, 0, 0.015, 0), box(0.025, 0.36, 0.025, 0x2a4a3a, 0, 0.2, 0));
  const shade = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.16, 14, 1, true), new THREE.MeshStandardMaterial({ color: 0x2f7a55, emissive: 0xffd8a0, emissiveIntensity: 1, side: THREE.DoubleSide }));
  shade.position.y = 0.42; shade.userData.lampBulb = true; lamp.add(shade);
  lamp.position.set(-0.95, 0.815, T.z - 0.15); ctx.pickable(lamp, "lamp"); r.add(lamp);

  // ---- chairs: student's chair behind the table, two guest chairs in front
  const chair = (x: number, z: number, faceZ: number) => {
    const c = new THREE.Group();
    c.add(box(0.5, 0.06, 0.5, 0xc98a4b, 0, 0.45, 0), box(0.5, 0.5, 0.05, 0xc98a4b, 0, 0.74, -0.22 * faceZ));
    [[-0.2, -0.2], [0.2, -0.2], [-0.2, 0.2], [0.2, 0.2]].forEach(([dx, dz]) => c.add(box(0.05, 0.43, 0.05, 0x8a5a36, dx, 0.215, dz)));
    c.position.set(x, 0, z); r.add(c);
  };
  chair(0, T.z - 0.85, -1); chair(-0.8, T.z + 0.95, 1); chair(0.9, T.z + 0.95, 1);
  // ---- pendant lamps
  [-1.7, 0, 1.7].forEach((x) => {
    r.add(box(0.015, 1.0, 0.015, 0x222222, x, h - 0.5, T.z));
    const b = new THREE.Mesh(new THREE.SphereGeometry(0.16, 14, 10), new THREE.MeshBasicMaterial({ color: 0xffe3ad })); b.position.set(x, h - 1.08, T.z); r.add(b);
  });
  return {
    seat: new THREE.Vector3(0, 0.48, T.z - 0.88),
    lampPos: new THREE.Vector3(-0.95, 1.3, T.z - 0.1),
    rain: { x: 0, width: w, y: sill + winH / 2, z: back },
  };
}
