import * as THREE from "three";

/**
 * Fallback figure built from primitives, used only when
 * /models/human_twin.glb (exported by blender/build_human_twin.py) is missing.
 * It uses the same part names and pivots as the Blender asset, so the
 * animation code does not care which one is loaded.
 *
 * Convention (same as the GLB): metres, Y up, subject faces +Z,
 * subject's left is +X, feet at y = 0.
 */
export function buildProceduralTwin(): THREE.Group {
  const root = new THREE.Group();
  root.name = "HumanTwin";
  const mat = new THREE.MeshStandardMaterial();

  const part = (name: string, pivot: [number, number, number]) => {
    const g = new THREE.Group();
    g.name = name;
    g.position.set(...pivot);
    root.add(g);
    return g;
  };
  const mesh = (
    parent: THREE.Object3D,
    geo: THREE.BufferGeometry,
    at: [number, number, number],
    scale: [number, number, number] = [1, 1, 1],
    rotZ = 0,
  ) => {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(...at);
    m.scale.set(...scale);
    m.rotation.z = rotZ;
    parent.add(m);
    return m;
  };

  const head = part("Head", [0, 1.47, 0]);
  mesh(head, new THREE.SphereGeometry(0.105, 32, 24), [0, 0.165, 0], [0.88, 1.1, 0.95]);
  mesh(head, new THREE.CylinderGeometry(0.05, 0.06, 0.12, 20), [0, 0.02, 0]);

  const torso = part("Torso", [0, 1.0, 0]);
  mesh(torso, new THREE.CapsuleGeometry(0.15, 0.36, 8, 24), [0, 0.17, 0], [1.25, 1, 0.68]);
  mesh(torso, new THREE.SphereGeometry(0.16, 24, 16), [0, -0.07, 0], [1.08, 0.8, 0.7]);

  for (const [side, sx] of [["L", 1], ["R", -1]] as const) {
    const arm = part(`Arm_${side}`, [0.2 * sx, 1.39, 0]);
    mesh(arm, new THREE.CapsuleGeometry(0.045, 0.24, 6, 16), [0.022 * sx, -0.14, 0], [1, 1, 1], 0.08 * sx);
    mesh(arm, new THREE.CapsuleGeometry(0.037, 0.24, 6, 16), [0.065 * sx, -0.39, 0.005], [1, 1, 1], 0.05 * sx);
    mesh(arm, new THREE.SphereGeometry(0.045, 16, 12), [0.085 * sx, -0.56, 0.01], [0.8, 1.2, 0.6]);

    const leg = part(`Leg_${side}`, [0.095 * sx, 0.9, 0]);
    mesh(leg, new THREE.CapsuleGeometry(0.07, 0.34, 6, 16), [0.004 * sx, -0.2, 0]);
    mesh(leg, new THREE.CapsuleGeometry(0.05, 0.36, 6, 16), [0.005 * sx, -0.6, 0]);
    mesh(leg, new THREE.SphereGeometry(0.06, 16, 12), [0.005 * sx, -0.86, 0.04], [0.75, 0.5, 1.6]);

    const lung = part(`Lung_${side}`, [0.08 * sx, 1.29, -0.005]);
    mesh(lung, new THREE.SphereGeometry(0.075, 24, 16), [0.002 * sx, 0.0, 0], [0.85, 1.55, 0.9]);
  }

  const heart = part("Heart", [0.03, 1.26, 0.06]);
  mesh(heart, new THREE.SphereGeometry(0.045, 24, 16), [-0.005, 0.01, 0], [1, 1.05, 0.9]);
  mesh(heart, new THREE.ConeGeometry(0.035, 0.07, 16), [0.012, -0.04, 0], [1, 1, 0.9], 0.5);

  return root;
}
