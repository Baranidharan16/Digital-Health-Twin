// Catalogue of the structures in anatomy_twin.glb (built by
// blender/build_anatomy_twin.py from BodyParts3D). For each one: which body
// system it belongs to, what it does, and — honestly — whether any wearable
// data drives it in the twin.

export type Layer = "skin" | "skeleton" | "muscles" | "organs" | "vessels";

export interface StructureInfo {
  label: string;
  layer: Layer;
  system: string;
  role: string;
  /** How live data drives it, or null when no wearable measures it. */
  drivenBy: string | null;
  metrics?: ("heart_rate" | "respiratory_rate" | "spo2" | "temperature")[];
}

export const LAYERS: { key: Layer; label: string }[] = [
  { key: "skin", label: "Skin" },
  { key: "organs", label: "Organs" },
  { key: "vessels", label: "Blood vessels" },
  { key: "skeleton", label: "Skeleton" },
  { key: "muscles", label: "Muscles" },
];

export const DEFAULT_LAYERS: Record<Layer, boolean> = {
  skin: true,
  organs: true,
  vessels: true,
  skeleton: false,
  muscles: false,
};

export const STRUCTURES: Record<string, StructureInfo> = {
  Heart: {
    label: "Heart",
    layer: "organs",
    system: "Cardiovascular",
    role: "Pumps blood through the lungs and the body, about 100,000 beats a day.",
    drivenBy: "Beats at the live heart rate; glows amber or red when heart rate is unusual for this person.",
    metrics: ["heart_rate"],
  },
  Arteries: {
    label: "Arteries",
    layer: "vessels",
    system: "Cardiovascular",
    role: "Carry oxygen-rich blood from the heart to every organ.",
    drivenBy: "A pulse wave runs with each heartbeat; colour darkens as blood oxygen (SpO₂) falls, when SpO₂ is measured.",
    metrics: ["heart_rate", "spo2"],
  },
  Veins: {
    label: "Veins",
    layer: "vessels",
    system: "Cardiovascular",
    role: "Return oxygen-poor blood to the heart.",
    drivenBy: null,
  },
  Lung_L: {
    label: "Left lung",
    layer: "organs",
    system: "Respiratory",
    role: "Takes in oxygen and removes carbon dioxide.",
    drivenBy: "Expands and contracts at the live breathing rate; highlights when breathing or SpO₂ is unusual.",
    metrics: ["respiratory_rate", "spo2"],
  },
  Lung_R: {
    label: "Right lung",
    layer: "organs",
    system: "Respiratory",
    role: "Takes in oxygen and removes carbon dioxide (three lobes).",
    drivenBy: "Expands and contracts at the live breathing rate; highlights when breathing or SpO₂ is unusual.",
    metrics: ["respiratory_rate", "spo2"],
  },
  Diaphragm: {
    label: "Diaphragm",
    layer: "organs",
    system: "Respiratory",
    role: "The main breathing muscle; moves down to pull air in.",
    drivenBy: "Moves down and up with each breath at the live breathing rate.",
    metrics: ["respiratory_rate"],
  },
  Airway: {
    label: "Trachea and bronchi",
    layer: "organs",
    system: "Respiratory",
    role: "Carry air between the throat and the lungs.",
    drivenBy: null,
  },
  Brain: {
    label: "Brain",
    layer: "organs",
    system: "Nervous",
    role: "Controls the body; sleep is when it recovers and consolidates memory.",
    drivenBy: "Shows a slow blue glow while the device reports sleep.",
  },
  Muscles: {
    label: "Skeletal muscles",
    layer: "muscles",
    system: "Musculoskeletal",
    role: "Move the body; their demand for oxygen drives heart rate and breathing up during exercise.",
    drivenBy: "Glow with the measured movement intensity (from the accelerometer, or estimated from step cadence).",
  },
  Skeleton: {
    label: "Skeleton",
    layer: "skeleton",
    system: "Musculoskeletal",
    role: "Supports and protects the body; 320 bones and cartilages in this model.",
    drivenBy: null,
  },
  Skin: {
    label: "Skin",
    layer: "skin",
    system: "Integumentary",
    role: "Protects the body and helps regulate temperature.",
    drivenBy: "Warms in colour when body temperature is unusual for this person, when temperature is measured.",
    metrics: ["temperature"],
  },
  Liver: {
    label: "Liver and gallbladder",
    layer: "organs",
    system: "Digestive",
    role: "Processes nutrients, stores energy, filters toxins and makes bile.",
    drivenBy: null,
  },
  Stomach: {
    label: "Stomach and oesophagus",
    layer: "organs",
    system: "Digestive",
    role: "Carries food down and begins digesting it.",
    drivenBy: null,
  },
  Intestines: {
    label: "Intestines",
    layer: "organs",
    system: "Digestive",
    role: "Absorb nutrients (small intestine) and water (large intestine).",
    drivenBy: null,
  },
  Pancreas: {
    label: "Pancreas",
    layer: "organs",
    system: "Digestive and endocrine",
    role: "Makes digestive enzymes and the hormones that control blood sugar.",
    drivenBy: null,
  },
  Spleen: {
    label: "Spleen",
    layer: "organs",
    system: "Immune",
    role: "Filters blood and supports the immune system.",
    drivenBy: null,
  },
  Kidney_L: {
    label: "Left kidney",
    layer: "organs",
    system: "Urinary",
    role: "Filters blood to make urine and balances fluids and salts.",
    drivenBy: null,
  },
  Kidney_R: {
    label: "Right kidney",
    layer: "organs",
    system: "Urinary",
    role: "Filters blood to make urine and balances fluids and salts.",
    drivenBy: null,
  },
  Bladder: {
    label: "Bladder",
    layer: "organs",
    system: "Urinary",
    role: "Stores urine.",
    drivenBy: null,
  },
};

export const NOT_MONITORED =
  "Not monitored: consumer wearables do not measure this organ, so the twin shows it for anatomical context only and never animates it.";

export const ANATOMY_CREDIT =
  "Anatomy: BodyParts3D, © The Database Center for Life Science, CC BY-SA 2.1 JP (segmented from real scan data of one adult male).";
