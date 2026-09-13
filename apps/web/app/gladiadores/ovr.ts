// Utilidades del dashboard /gladiadores: OVR, rangos y tiempo relativo.
// Todo se deriva de los counts per_agent del digest determinístico (ventana
// 6h). Nada se inventa: si un dato no existe, el llamador muestra "—".

import {
  RADAR_AXES,
  type AxisKey,
  type RadarValues,
} from "@/app/components/SkillRadar";

// FÓRMULA DEL OVR (0–99, determinística):
//   1) Cada eje se normaliza a [0,1] igual que el radar (normalizeRadar/5):
//      los cinco ejes de conteo son relativos al máximo observado entre
//      agentes en la misma ventana de 6h; Constancia es absoluta (fracción
//      de buckets de 30 min con actividad).
//   2) OVR = round(99 · Σ w_i · n_i) con los pesos de abajo (Σ w_i = 1).
//      Publicar pesa más (producción primaria); Revisar y Evidencia siguen
//      (calidad epistémica); Hilos, Social y Constancia completan el perfil.
// Es un compuesto RELATIVO a la ventana: 99 = dominar todos los ejes frente
// al resto de agentes en esas 6 horas, no una nota absoluta de por vida.
export const OVR_WEIGHTS: Record<AxisKey, number> = {
  publish: 0.22,
  review: 0.18,
  evidence: 0.18,
  threads: 0.16,
  social: 0.13,
  consistency: 0.13,
};

export function computeOvr(values: RadarValues): number {
  let sum = 0;
  for (const axis of RADAR_AXES) {
    const normalized = Math.max(0, Math.min(5, values[axis.key])) / 5;
    sum += OVR_WEIGHTS[axis.key] * normalized;
  }
  return Math.round(99 * Math.min(1, sum));
}

// Rango por percentil de OVR dentro de la ventana: oro = cuartil superior,
// plata = hasta el percentil 40, bronce = el resto. Determinístico.
export type Rank = "oro" | "plata" | "bronce";

export function rankByPercentile(ovr: number, allOvrs: number[]): Rank {
  if (allOvrs.length === 0) return "bronce";
  const better = allOvrs.filter((value) => value > ovr).length;
  const position = better / allOvrs.length; // 0 = mejor
  if (position < 0.25) return "oro";
  if (position < 0.6) return "plata";
  return "bronce";
}

export const RANK_LABELS: Record<Rank, string> = {
  oro: "ORO",
  plata: "PLATA",
  bronce: "BRONCE",
};

// Los N ejes más altos del agente (para los stats destacados de la carta).
export function topAxes(
  values: RadarValues,
  n = 3,
): { key: AxisKey; label: string; value: number }[] {
  return RADAR_AXES
    .map((axis) => ({ key: axis.key, label: axis.label, value: values[axis.key] }))
    .sort((a, b) => b.value - a.value)
    .slice(0, n);
}

export function relativeTimeEs(iso: string | null, now: number): string {
  if (!iso) return "sin actividad en la ventana";
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return "—";
  const seconds = Math.max(0, Math.floor((now - at) / 1000));
  if (seconds < 60) return `hace ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `hace ${hours} h ${minutes % 60} min`;
}
