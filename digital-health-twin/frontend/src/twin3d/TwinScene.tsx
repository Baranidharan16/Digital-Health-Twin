import { ContactShadows, Html, Line, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";
import type { TwinStatePayload } from "../api/types";
import { heartbeatShape, visualsFor, type TwinVisuals } from "../lib/twinVisuals";
import { buildProceduralTwin } from "./proceduralTwin";

const MODEL_URL = "/models/human_twin.glb";

interface Props {
  payload: TwinStatePayload | null;
  showLabels?: boolean;
  xray?: boolean;
  height?: number | string;
}

export function TwinScene({ payload, showLabels = true, xray = false, height = "100%" }: Props) {
  const reduceMotion = usePrefersReducedMotion();
  return (
    <div className="twin-canvas" style={{ height }}>
      <Canvas
        camera={{ position: [0, 1.0, 4.3], fov: 30 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        aria-label="3D digital twin of the subject"
        role="img"
      >
        <ambientLight intensity={0.85} />
        <directionalLight position={[2.5, 4, 3]} intensity={1.4} />
        <directionalLight position={[-3, 2, -2]} intensity={0.5} color="#cfe0ea" />
        <CalibrationPlate />
        <ContactShadows position={[0, 0.002, 0]} opacity={0.35} scale={3} blur={2.4} far={2} />
        <ModelBoundary fallback={<Figure source={null} payload={payload} showLabels={showLabels} xray={xray} still={reduceMotion} />}>
          <Suspense fallback={null}>
            <GltfFigure payload={payload} showLabels={showLabels} xray={xray} still={reduceMotion} />
          </Suspense>
        </ModelBoundary>
        <OrbitControls
          target={[0, 0.86, 0]}
          enablePan={false}
          minDistance={2}
          maxDistance={6}
          minPolarAngle={0.5}
          maxPolarAngle={1.75}
        />
      </Canvas>
    </div>
  );
}

// ---------------------------------------------------------------- model load
class ModelBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

type FigureProps = { payload: TwinStatePayload | null; showLabels: boolean; xray: boolean; still: boolean };

function GltfFigure(props: FigureProps) {
  const { scene } = useGLTF(MODEL_URL);
  return <Figure source={scene} {...props} />;
}

// ------------------------------------------------------------------ materials
function skinMaterial(): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    color: "#AFC1CC",
    roughness: 0.3,
    metalness: 0.05,
    transparent: true,
    opacity: 0.2,
    depthWrite: false,
  });
  // Fresnel rim: silhouettes read clearly while organs stay visible inside.
  mat.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <opaque_fragment>",
      `float rim = 1.0 - abs(dot(normalize(normal), normalize(vViewPosition)));
       diffuseColor.a = clamp(diffuseColor.a + pow(rim, 2.4) * 0.6, 0.0, 1.0);
       #include <opaque_fragment>`,
    );
  };
  return mat;
}

const organMaterial = (color: string) =>
  new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0, emissive: "#000000" });

// ---------------------------------------------------------------- the figure
function Figure({ source, payload, showLabels, xray, still }: FigureProps & { source: THREE.Object3D | null }) {
  const root = useMemo(() => (source ? source.clone(true) : buildProceduralTwin()), [source]);
  const posture = useRef<THREE.Group>(null);
  const bed = useRef<THREE.Mesh>(null);
  const visuals: TwinVisuals | null = payload ? visualsFor(payload) : null;
  const vRef = useRef(visuals);
  vRef.current = visuals;

  const parts = useMemo(() => {
    const get = (n: string) => root.getObjectByName(n) ?? new THREE.Object3D();
    const mats = {
      skin: skinMaterial(),
      head: skinMaterial(),
      heart: organMaterial("#C2474F"),
      lungs: organMaterial("#D99AA0"),
    };
    const assign = (obj: THREE.Object3D, mat: THREE.Material) =>
      obj.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          const mesh = o as THREE.Mesh;
          mesh.material = mat;
          mesh.renderOrder = mat.transparent ? 2 : 1;
        }
      });
    const p = {
      head: get("Head"),
      torso: get("Torso"),
      armL: get("Arm_L"),
      armR: get("Arm_R"),
      legL: get("Leg_L"),
      legR: get("Leg_R"),
      heart: get("Heart"),
      lungL: get("Lung_L"),
      lungR: get("Lung_R"),
    };
    [p.torso, p.armL, p.armR, p.legL, p.legR].forEach((o) => assign(o, mats.skin));
    assign(p.head, mats.head);
    assign(p.heart, mats.heart);
    [p.lungL, p.lungR].forEach((o) => assign(o, mats.lungs));
    return { ...p, mats };
  }, [root]);

  useEffect(() => {
    parts.mats.skin.opacity = xray ? 0.06 : 0.2;
    parts.mats.head.opacity = xray ? 0.06 : 0.2;
  }, [xray, parts]);

  const clock = useRef({ beat: 0, breath: 0, stride: 0, lying: 0 });
  const tmp = useMemo(() => ({ c: new THREE.Color(), base: new THREE.Color("#AFC1CC") }), []);

  useFrame((_, delta) => {
    const v = vRef.current;
    if (!v || !posture.current) return;
    const dt = Math.min(delta, 0.05);
    const c = clock.current;
    const motion = still ? 0.25 : 1;
    c.beat += (dt * v.heartBpm) / 60;
    c.breath += (dt * v.breathsPerMin) / 60;
    c.stride += dt * v.cadenceHz * Math.PI * 2;
    c.lying += ((v.lying ? 1 : 0) - c.lying) * Math.min(1, dt * 2.5);

    // Heart: pulse at the live heart rate.
    const pulse = heartbeatShape(c.beat) * motion;
    parts.heart.scale.setScalar(1 + 0.17 * pulse);
    glow(parts.mats.heart, v.regions.heart === "normal" ? "#7A1E25" : v.regionColors.heart, 0.25 + 0.75 * pulse);

    // Lungs: expand and contract at the live breathing rate.
    const breath = Math.sin(c.breath * Math.PI * 2) * motion;
    const ls = 1 + 0.06 * breath;
    parts.lungL.scale.set(ls, 1 + 0.035 * breath, ls);
    parts.lungR.scale.set(ls, 1 + 0.035 * breath, ls);
    regionGlow(parts.mats.lungs, v.regions.lungs, v.regionColors.lungs, c.beat);

    // Head: temperature region.
    if (v.regions.head === "normal") {
      parts.mats.head.emissive.set("#000000");
      parts.mats.head.opacity = xray ? 0.06 : 0.2;
    } else {
      const k = 0.5 + 0.5 * Math.sin(c.beat * Math.PI);
      parts.mats.head.emissive.set(v.regionColors.head).multiplyScalar(0.35 + 0.35 * k);
      parts.mats.head.opacity = 0.45;
    }

    // Body tint follows the twin state.
    tmp.c.copy(tmp.base).lerp(new THREE.Color(v.stateColor), 0.35);
    parts.mats.skin.color.lerp(tmp.c, Math.min(1, dt * 3));
    parts.mats.head.color.copy(parts.mats.skin.color);

    // Limbs: gait amplitude and speed follow measured movement intensity.
    const amp = v.movement * motion * (1 - c.lying);
    const s = Math.sin(c.stride);
    ease(parts.armL.rotation, "x", 0.75 * amp * s, dt);
    ease(parts.armR.rotation, "x", -0.75 * amp * s, dt);
    ease(parts.legL.rotation, "x", -0.55 * amp * s, dt);
    ease(parts.legR.rotation, "x", 0.55 * amp * s, dt);

    // Posture: lie down while the source reports sleep.
    posture.current.rotation.z = (Math.PI / 2) * c.lying;
    posture.current.position.x = 0.9 * c.lying;
    posture.current.position.y = 0.4 * c.lying + Math.abs(s) * 0.025 * amp;
    if (bed.current) {
      bed.current.visible = c.lying > 0.02;
      (bed.current.material as THREE.MeshStandardMaterial).opacity = 0.55 * c.lying;
    }
  });

  const a = payload?.assessments;
  return (
    <>
    {/* Bed: appears while the source reports sleep. */}
    <mesh ref={bed} position={[0, 0.15, 0]} visible={false}>
      <boxGeometry args={[2.0, 0.3, 0.75]} />
      <meshStandardMaterial color="#C9D6DE" transparent opacity={0} roughness={0.8} depthWrite={false} />
    </mesh>
    <group ref={posture}>
      <primitive object={root} />
      {showLabels && a && !payload?.observation.is_asleep && (
        <>
          <Callout from={[0.04, 1.27, 0.08]} to={[0.42, 1.3, 0.1]} status={a.heart_rate.status}>
            <b>{Math.round(a.heart_rate.value)}</b> bpm
          </Callout>
          <Callout from={[-0.1, 1.33, 0.03]} to={[-0.46, 1.4, 0.1]} status={worse(a.respiratory_rate.status, a.spo2.status)} left>
            <b>{Math.round(a.respiratory_rate.value)}</b> br/min, SpO₂ <b>{a.spo2.value.toFixed(1)}</b>%
          </Callout>
          <Callout from={[0.06, 1.66, 0.05]} to={[0.36, 1.72, 0.1]} status={a.temperature.status}>
            <b>{a.temperature.value.toFixed(1)}</b> °C
          </Callout>
        </>
      )}
    </group>
    </>
  );
}

function worse(a: string, b: string) {
  const rank: Record<string, number> = { normal: 0, watch: 1, anomalous: 2 };
  return rank[a] >= rank[b] ? a : b;
}

function Callout({
  from,
  to,
  status,
  left,
  children,
}: {
  from: [number, number, number];
  to: [number, number, number];
  status: string;
  left?: boolean;
  children: ReactNode;
}) {
  const color = status === "anomalous" ? "#B4363F" : status === "watch" ? "#C98A1B" : "#5B6F7C";
  return (
    <>
      <Line points={[from, to]} color={color} lineWidth={1} transparent opacity={0.8} />
      <mesh position={from}>
        <sphereGeometry args={[0.008, 10, 8]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <Html position={to} zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <div className={`callout callout-${status} ${left ? "callout-left" : ""}`}>{children}</div>
      </Html>
    </>
  );
}

function glow(mat: THREE.MeshStandardMaterial, color: string, k: number) {
  mat.emissive.set(color).multiplyScalar(k);
}

function regionGlow(mat: THREE.MeshStandardMaterial, status: string, color: string, beat: number) {
  if (status === "normal") {
    mat.emissive.set("#000000");
    return;
  }
  const k = 0.45 + 0.35 * Math.sin(beat * Math.PI);
  mat.emissive.set(color).multiplyScalar(k);
}

function ease(rot: THREE.Euler, axis: "x", target: number, dt: number) {
  rot[axis] += (target - rot[axis]) * Math.min(1, dt * 12);
}

// ---------------------------------------------------------- calibration plate
function CalibrationPlate() {
  const ticks = useMemo(() => {
    const out: [number, number, number][][] = [];
    for (let i = 0; i < 72; i++) {
      const t = (i / 72) * Math.PI * 2;
      const r0 = i % 6 === 0 ? 0.86 : 0.9;
      out.push([
        [Math.cos(t) * r0, 0.003, Math.sin(t) * r0],
        [Math.cos(t) * 0.94, 0.003, Math.sin(t) * 0.94],
      ]);
    }
    return out;
  }, []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2}>
        <circleGeometry args={[0.98, 96]} />
        <meshStandardMaterial color="#E3EAEE" roughness={0.9} />
      </mesh>
      {[0.42, 0.94].map((r) => (
        <mesh key={r} rotation-x={-Math.PI / 2} position={[0, 0.002, 0]}>
          <ringGeometry args={[r - 0.004, r, 128]} />
          <meshBasicMaterial color="#98AAB5" />
        </mesh>
      ))}
      {ticks.map((pts, i) => (
        <Line key={i} points={pts} color="#98AAB5" lineWidth={1} />
      ))}
    </group>
  );
}

function usePrefersReducedMotion() {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(mq.matches);
    const on = () => setReduce(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduce;
}
