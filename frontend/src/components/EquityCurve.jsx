import { useMemo } from 'react'
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts'
import { useBacktestStore } from '../store/useBacktestStore'

function fmt(v) {
  return `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

export default function EquityCurve() {
  const results = useBacktestStore((s) => s.results)
  const params = useBacktestStore((s) => s.params)

  const equity = useMemo(() => {
    if (!results?.equity_curve) return []
    return results.equity_curve.map((p) => ({
      t: p.datetime,
      equity: p.equity,
      label: p.datetime.slice(0, 10),
    }))
  }, [results])

  const dailyPnl = useMemo(() => {
    if (!results?.trades) return []
    const map = new Map()
    for (const t of results.trades) {
      const day = (t.exit_time || t.entry_time).slice(0, 10)
      map.set(day, (map.get(day) || 0) + t.pnl)
    }
    return Array.from(map.entries())
      .map(([day, pnl]) => ({ day, pnl }))
      .sort((a, b) => a.day.localeCompare(b.day))
  }, [results])

  if (!results) {
    return (
      <div className="card text-sm text-gray-400 h-full flex items-center justify-center">
        Equity curve will appear here after running a backtest.
      </div>
    )
  }

  const start = params.starting_capital
  return (
    <div className="card space-y-4">
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-sm font-semibold text-gray-200">Equity Curve</h2>
          <span className="text-xs text-gray-400">
            Final: <span className="text-gray-100 font-mono">{fmt(results.stats.final_equity)}</span>
          </span>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={equity}>
            <defs>
              <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="label" stroke="#6b7280" fontSize={10} minTickGap={40} />
            <YAxis stroke="#6b7280" fontSize={10} domain={['auto', 'auto']} tickFormatter={fmt} />
            <Tooltip
              contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }}
              formatter={(v) => fmt(v)}
              labelFormatter={(l) => `Time: ${l}`}
            />
            <ReferenceLine y={start} stroke="#6b7280" strokeDasharray="4 4" />
            <Area type="monotone" dataKey="equity" stroke="#22c55e" fill="url(#g)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">Daily P&L</h3>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={dailyPnl}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="day" stroke="#6b7280" fontSize={10} minTickGap={40} />
            <YAxis stroke="#6b7280" fontSize={10} tickFormatter={fmt} />
            <Tooltip contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }} formatter={(v) => fmt(v)} />
            <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
              {dailyPnl.map((p, i) => (
                <Cell key={i} fill={p.pnl >= 0 ? '#22c55e' : '#ef4444'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
