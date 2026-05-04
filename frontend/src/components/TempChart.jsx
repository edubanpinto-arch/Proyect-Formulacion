import React from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  ReferenceArea, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return iso; }
}

export default function TempChart({ readings = [], height = 320 }) {
  const data = readings.map((r) => ({
    ts: r.ts,
    time: formatTime(r.ts),
    temp: typeof r.temperature === "number" ? r.temperature : parseFloat(r.temperature),
  }));

  return (
    <div className="w-full" style={{ height }} data-testid="temp-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0369a1" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#0369a1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
          <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#64748b", fontFamily: "IBM Plex Mono" }} stroke="#cbd5e1" />
          <YAxis domain={[0, 12]} tick={{ fontSize: 11, fill: "#64748b", fontFamily: "IBM Plex Mono" }} stroke="#cbd5e1" tickFormatter={(v) => `${v}°`} />
          <ReferenceArea y1={2} y2={8} fill="#10b981" fillOpacity={0.1} stroke="#10b981" strokeOpacity={0.25} />
          <ReferenceLine y={2.5} stroke="#f59e0b" strokeDasharray="4 4" />
          <ReferenceLine y={7.5} stroke="#f59e0b" strokeDasharray="4 4" />
          <ReferenceLine y={2} stroke="#e11d48" strokeDasharray="2 2" />
          <ReferenceLine y={8} stroke="#e11d48" strokeDasharray="2 2" />
          <Tooltip
            contentStyle={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 8, fontFamily: "IBM Plex Mono", fontSize: 12 }}
            formatter={(v) => [`${Number(v).toFixed(2)} °C`, "T"]}
          />
          <Line type="monotone" dataKey="temp" stroke="#0369a1" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
