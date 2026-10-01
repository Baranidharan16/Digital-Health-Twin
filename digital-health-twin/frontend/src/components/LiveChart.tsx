import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import type { TwinStatePayload, VitalMetric } from "../api/types";
import { fmtClock, toDate } from "../lib/format";
import { METRICS } from "../lib/states";

/** Rolling chart of the live stream: value vs the twin's expected band. */
export function LiveChart({ buffer, metric = "heart_rate", height = 210 }: { buffer: TwinStatePayload[]; metric?: VitalMetric; height?: number }) {
  const meta = METRICS.find((m) => m.key === metric)!;
  const data = buffer.map((p) => {
    const a = p.assessments[metric];
    return {
      t: toDate(p.twin_time).getTime(),
      value: a.value,
      band: [a.expected_low, a.expected_high] as [number, number],
      status: a.status,
    };
  });
  return (
    <figure className="chart">
      <figcaption>
        <strong>{meta.label}</strong> ({meta.unit}), live stream against the expected band for the current activity
      </figcaption>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#D5DEE3" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => fmtClock(new Date(t).toISOString(), false)}
            tick={{ fontSize: 11, fill: "#5B6F7C" }}
            minTickGap={40}
          />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#5B6F7C" }} width={48} />
          <Tooltip
            labelFormatter={(t) => `Twin time ${fmtClock(new Date(Number(t)).toISOString())}`}
            formatter={(v, name) =>
              name === "band" && Array.isArray(v)
                ? [`${Number(v[0]).toFixed(meta.digits)}–${Number(v[1]).toFixed(meta.digits)} ${meta.unit}`, "Expected"]
                : [`${Number(v).toFixed(meta.digits)} ${meta.unit}`, meta.label]
            }
          />
          <Area dataKey="band" stroke="none" fill="#0E7C7B" fillOpacity={0.14} isAnimationActive={false} />
          <Line dataKey="value" stroke="#1D2B36" strokeWidth={1.8} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  );
}
