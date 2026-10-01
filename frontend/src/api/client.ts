import type {
  AnalyticsResponse,
  BaselineResponse,
  Evaluation,
  HistoryResponse,
  ImportSummary,
  LiveStatus,
  Pairing,
  PhoneDevice,
  SimulationResult,
  SystemInfo,
  TwinEvent,
  TwinInfo,
  TwinStatePayload,
  Wellness,
} from "./types";

/** The synthetic demo twin (driven by the live simulator). */
export const TWIN_ID = "twin-001";

let active = TWIN_ID;
/** Twin shown in the dashboard; every twin-scoped call defaults to it. */
export const activeTwin = () => active;
export const setActiveTwin = (id: string) => {
  active = id;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  twins: () => request<TwinInfo[]>("/api/twins"),
  twin: (id = activeTwin()) => request<TwinInfo>(`/api/twin/${id}`),
  state: (id = activeTwin()) => request<TwinStatePayload>(`/api/twin/${id}/state`),
  events: (id = activeTwin(), limit = 40) => request<TwinEvent[]>(`/api/twin/${id}/events?limit=${limit}`),
  history: (range: string, start?: string, end?: string, id = activeTwin(), maxPoints = 600) => {
    const q = new URLSearchParams({ range, max_points: String(maxPoints) });
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return request<HistoryResponse>(`/api/twin/${id}/history?${q}`);
  },
  baseline: (id = activeTwin()) => request<BaselineResponse>(`/api/twin/${id}/baseline`),
  recomputeBaseline: (id = activeTwin()) => post<unknown>(`/api/twin/${id}/baseline/recompute`),
  wellness: (id = activeTwin()) => request<Wellness>(`/api/twin/${id}/wellness`),
  analytics: (range = "7d", id = activeTwin()) => request<AnalyticsResponse>(`/api/twin/${id}/analytics?range=${range}`),
  evaluation: () => request<Evaluation>("/api/system/evaluation"),
  system: () => request<SystemInfo>("/api/system/info"),
  liveStatus: () => request<LiveStatus>("/api/simulator/status"),
  liveStart: (scenario = "NORMAL", guided = false, mode: "simulator" | "replay" = "simulator") =>
    post<LiveStatus>("/api/simulator/start", { twin_id: TWIN_ID, scenario, guided, mode }),
  liveStop: () => post<LiveStatus>("/api/simulator/stop"),
  liveScenario: (scenario: string) => post<LiveStatus>("/api/simulator/scenario", { scenario }),
  resetDemo: () => post<unknown>("/api/demo/reset"),
  simulate: (body: Record<string, unknown>) => post<SimulationResult>("/api/simulation", { twin_id: activeTwin(), ...body }),
  importSample: () => post<ImportSummary>("/api/twins/import-sample"),
  importFiles: async (form: FormData) => {
    const res = await fetch("/api/twins/import", { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
    return body as ImportSummary;
  },
  deleteTwin: (id: string) => request<{ deleted: string }>(`/api/twin/${id}`, { method: "DELETE" }),
  createPairing: (display_name: string, age_years: number) =>
    post<Pairing>("/api/devices/pairing", { display_name, age_years }),
  devices: () => request<PhoneDevice[]>("/api/devices"),
  revokeDevice: (id: number) => request<{ revoked: number }>(`/api/devices/${id}`, { method: "DELETE" }),
};
