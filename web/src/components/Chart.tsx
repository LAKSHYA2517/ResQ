import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface Series {
  name: string;
  points: { x: number; y: number }[];
}

// Colour plus a distinct dash pattern, so series are told apart without relying on colour.
const STYLES = [
  { stroke: "#1f4fa3", dash: "" },
  { stroke: "#b8322a", dash: "6 3" },
  { stroke: "#8a5a00", dash: "2 3" },
  { stroke: "#2b7a4b", dash: "8 3 2 3" },
];

export function Lines({
  series,
  xLabel,
  yLabel,
  reference,
  referenceLabel,
  logX = false,
  height = 190,
}: {
  series: Series[];
  xLabel: string;
  yLabel: string;
  reference?: number;
  referenceLabel?: string;
  logX?: boolean;
  height?: number;
}) {
  return (
    <div style={{ height }} role="img" aria-label={`${yLabel} against ${xLabel}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart margin={{ top: 6, right: 12, bottom: 14, left: 0 }}>
          <CartesianGrid stroke="#d9d4c7" strokeDasharray="2 4" />
          <XAxis
            dataKey="x"
            type="number"
            scale={logX ? "log" : "linear"}
            domain={["dataMin", "dataMax"]}
            allowDuplicatedCategory={false}
            tick={{ fill: "#5c636c", fontSize: 10 }}
            label={{
              value: xLabel,
              position: "insideBottom",
              offset: -8,
              fill: "#5c636c",
              fontSize: 10,
            }}
          />
          <YAxis
            tick={{ fill: "#5c636c", fontSize: 10 }}
            width={44}
            domain={["auto", "auto"]}
            label={{
              value: yLabel,
              angle: -90,
              position: "insideLeft",
              fill: "#5c636c",
              fontSize: 10,
            }}
          />
          <Tooltip
            contentStyle={{ background: "#fbfaf7", border: "1px solid #d9d4c7", fontSize: 11 }}
            labelFormatter={(v) => `${xLabel}: ${v}`}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} verticalAlign="top" height={22} />
          {reference !== undefined && (
            <ReferenceLine
              y={reference}
              stroke="#1c2229"
              strokeDasharray="4 4"
              label={{
                value: referenceLabel,
                fill: "#1c2229",
                fontSize: 10,
                position: "insideTopRight",
              }}
            />
          )}
          {series.map((s, i) => (
            <Line
              key={s.name}
              data={s.points}
              dataKey="y"
              name={s.name}
              type="stepAfter"
              dot={false}
              isAnimationActive={false}
              stroke={STYLES[i % STYLES.length]?.stroke}
              strokeDasharray={STYLES[i % STYLES.length]?.dash}
              strokeWidth={2}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
