import type {
  AnalyticsResponse,
  BaselineResponse,
  Evaluation,
  HistoryResponse,
  LiveStatus,
  SimulationResult,
  SystemInfo,
  TwinEvent,
  TwinInfo,
  TwinStatePayload,
  Wellness,
} from "./types";

export const TWIN_ID = "twin-001";

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
  twin: (id = TWIN_ID) => request<TwinInfo>(`/api/twin/${id}`),
  state: (id = TWIN_ID) => request<TwinStatePayload>(`/api/twin/${id}/state`),
  events: (id = TWIN_ID, limit = 40) => request<TwinEvent[]>(`/api/twin/${id}/events?limit=${limit}`),
  history: (range: string, start?: string, end?: string, id = TWIN_ID) => {
    const q = new URLSearchParams({ range, max_points: "600" });
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return request<HistoryResponse>(`/api/twin/${id}/history?${q}`);
  },
  baseline: (id = TWIN_ID) => request<BaselineResponse>(`/api/twin/${id}/baseline`),
  recomputeBaseline: (id = TWIN_ID) => post<unknown>(`/api/twin/${id}/baseline/recompute`),
  wellness: (id = TWIN_ID) => request<Wellness>(`/api/twin/${id}/wellness`),
  analytics: (range = "7d", id = TWIN_ID) => request<AnalyticsResponse>(`/api/twin/${id}/analytics?range=${range}`),
  evaluation: () => request<Evaluation>("/api/system/evaluation"),
  system: () => request<SystemInfo>("/api/system/info"),
  liveStatus: () => request<LiveStatus>("/api/simulator/status"),
  liveStart: (scenario = "NORMAL", guided = false, mode: "simulator" | "replay" = "simulator") =>
    post<LiveStatus>("/api/simulator/start", { twin_id: TWIN_ID, scenario, guided, mode }),
  liveStop: () => post<LiveStatus>("/api/simulator/stop"),
  liveScenario: (scenario: string) => post<LiveStatus>("/api/simulator/scenario", { scenario }),
  resetDemo: () => post<unknown>("/api/demo/reset"),
  simulate: (body: Record<string, unknown>) => post<SimulationResult>("/api/simulation", { twin_id: TWIN_ID, ...body }),
};
