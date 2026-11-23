import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { monthLabel } from '../format';

export interface ChartSeries {
  key: string;         // stable identity (e.g. ZIP); color follows the entity, never its rank
  label: string;
  points: { period: string; value: number }[];
}

// Fixed categorical order. Callers pass `colorIndex` so a series keeps its color when filters change.
const SLOTS = ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5', '--series-6', '--series-7', '--series-8'];
const seriesColor = (index: number) => `var(${SLOTS[index % SLOTS.length]})`;

interface Props {
  series: (ChartSeries & { colorIndex: number })[];
  format: (value: number) => string;
  height?: number;
  dashedKeys?: string[];  // reference series (metro / US) drawn dashed as a secondary encoding
}

export default function TrendChart({ series, format, height = 300, dashedKeys = [] }: Props) {
  const byPeriod = new Map<string, Record<string, number | string>>();
  for (const s of series) {
    for (const point of s.points) {
      const row = byPeriod.get(point.period) ?? { period: point.period };
      row[s.key] = point.value;
      byPeriod.set(point.period, row);
    }
  }
  const data = [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)));

  if (!data.length) {
    return <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">No data yet — waiting on sync.</div>;
  }

  // Short ranges label months ("Mar '25") so ticks don't repeat the same year.
  const spanYears = Number(String(data.at(-1)!.period).slice(0, 4)) - Number(String(data[0].period).slice(0, 4));
  const tickLabel = (period: string) => {
    if (spanYears >= 3) return period.slice(0, 4);
    const [month, year] = monthLabel(period).split(' ');
    return `${month} '${year.slice(2)}`;
  };

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="period"
            tickFormatter={tickLabel}
            minTickGap={40}
            stroke="var(--chart-axis)"
            tick={{ fill: 'var(--chart-muted)', fontSize: 15 }}
          />
          <YAxis
            tickFormatter={format}
            width={64}
            stroke="var(--chart-axis)"
            tick={{ fill: 'var(--chart-muted)', fontSize: 15 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            formatter={(value, name) => [format(Number(value)), series.find((s) => s.key === name)?.label ?? String(name)]}
            labelFormatter={(label) => monthLabel(String(label))}
            contentStyle={{
              background: 'var(--chart-surface)',
              border: '1px solid var(--chart-grid)',
              borderRadius: 8,
              color: 'var(--ink-primary)',
              fontSize: 15,
            }}
            itemStyle={{ color: 'var(--ink-secondary)' }}
            cursor={{ stroke: 'var(--chart-axis)' }}
          />
          {series.length > 1 && (
            <Legend
              formatter={(value) => (
                <span style={{ color: 'var(--ink-secondary)', fontSize: 15 }}>
                  {series.find((s) => s.key === value)?.label ?? value}
                </span>
              )}
            />
          )}
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              type="monotone"
              stroke={seriesColor(s.colorIndex)}
              strokeWidth={2}
              strokeDasharray={dashedKeys.includes(s.key) ? '6 4' : undefined}
              dot={false}
              activeDot={{ r: 4, stroke: 'var(--chart-surface)', strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
