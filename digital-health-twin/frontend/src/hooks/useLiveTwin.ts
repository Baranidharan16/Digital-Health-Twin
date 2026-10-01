import { useCallback, useEffect, useRef, useState } from "react";
import { api, TWIN_ID } from "../api/client";
import type { LiveStatus, TwinEvent, TwinStatePayload } from "../api/types";

export type Connection = "connecting" | "live" | "offline";

const BUFFER = 160; // readings kept for the live strip chart

export interface LiveTwin {
  state: TwinStatePayload | null;
  buffer: TwinStatePayload[];
  live: LiveStatus | null;
  events: TwinEvent[];
  connection: Connection;
  lastMessageAt: number | null;
  refreshEvents: () => void;
  setLive: (s: LiveStatus) => void;
}

/**
 * Subscribes to the twin's WebSocket. Every reading the backend ingests is
 * pushed here, so the dashboard and 3D body update within one tick.
 * Falls back to polling the REST API while the socket is down.
 */
export function useLiveTwin(twinId = TWIN_ID): LiveTwin {
  const [state, setState] = useState<TwinStatePayload | null>(null);
  const [buffer, setBuffer] = useState<TwinStatePayload[]>([]);
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [events, setEvents] = useState<TwinEvent[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const lastKey = useRef<string>("");

  const refreshEvents = useCallback(() => {
    api.events(twinId, 40).then(setEvents).catch(() => undefined);
  }, [twinId]);

  const accept = useCallback(
    (next: TwinStatePayload) => {
      setLastMessageAt(Date.now());
      if (next.twin_time === lastKey.current) return;
      const prev = lastKey.current;
      lastKey.current = next.twin_time;
      setState((old) => {
        if (old && (old.state !== next.state || anomalyCount(old) !== anomalyCount(next))) refreshEvents();
        return next;
      });
      setBuffer((b) => {
        const out = prev && b.length && next.twin_time < b[b.length - 1].twin_time ? [] : b; // twin reset
        return [...out.slice(-(BUFFER - 1)), next];
      });
    },
    [refreshEvents],
  );

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: number | undefined;
    let poll: number | undefined;

    const startPolling = () => {
      if (poll) return;
      poll = window.setInterval(() => {
        api.state(twinId).then(accept).catch(() => undefined);
        api.liveStatus().then(setLive).catch(() => undefined);
      }, 2000);
    };
    const stopPolling = () => {
      if (poll) window.clearInterval(poll);
      poll = undefined;
    };

    const connect = () => {
      if (closed) return;
      setConnection((c) => (c === "live" ? c : "connecting"));
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/twin/${twinId}`);
      ws.onopen = () => {
        setConnection("live");
        stopPolling();
      };
      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data);
        if (data.type === "state") accept(data.data as TwinStatePayload);
        else if (data.type === "live") setLive(data.data as LiveStatus);
      };
      ws.onclose = () => {
        if (closed) return;
        setConnection("offline");
        startPolling();
        retry = window.setTimeout(connect, 2500);
      };
    };

    // Prime the buffer with recent readings so the strip chart is not empty.
    api.state(twinId).then(accept).catch(() => setConnection("offline"));
    api.liveStatus().then(setLive).catch(() => undefined);
    refreshEvents();
    connect();
    const eventTimer = window.setInterval(refreshEvents, 15000);

    return () => {
      closed = true;
      window.clearTimeout(retry);
      window.clearInterval(eventTimer);
      stopPolling();
      ws?.close();
    };
  }, [twinId, accept, refreshEvents]);

  return { state, buffer, live, events, connection, lastMessageAt, refreshEvents, setLive };
}

function anomalyCount(p: TwinStatePayload) {
  return Object.values(p.assessments).filter((a) => a.status === "anomalous").length;
}
