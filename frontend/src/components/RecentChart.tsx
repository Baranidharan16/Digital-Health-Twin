import { useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { HistoryPoint } from "../api/types";
import { fmtClockDate, fmtDateTime, toDate } from "../lib/format";

/** For twins built from recorded data: the last hours before the final reading. */
export function RecentChart({ hours = "6h" }: { hours?: "1h" | "6h" | "24h" }) {
  const [points, setPoints] = useState<HistoryPoint[]>([]);
  useEffect(() => {
    api.history(hours).then((h) => setPoints(h.points)).catch(() => setPoints([]));
  }, [hours]);
  const rows = points.map((p) => ({ t: toDate(p.t).getTime(), hr: p.heart_rate }));
  return (
    <figure className="chart">
      <figcaption>
        <strong>Heart rate</strong> (bpm), the last {hours.replace("h", " hours")} of recorded data before the final reading
      </figcaption>
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#D5DEE3" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => fmtClockDate(new Date(t), false)} tick={{ fontSize: 11, fill: "#5B6F7C" }} minTickGap={40} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#5B6F7C" }} width={48} />
          <Tooltip labelFormatter={(t) => fmtDateTime(new Date(Number(t)).toISOString())} formatter={(v) => [`${Number(v).toFixed(0)} bpm`, "Heart rate"]} />
          <Line dataKey="hr" stroke="#1D2B36" strokeWidth={1.6} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  );
}
