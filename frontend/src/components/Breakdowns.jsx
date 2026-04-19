import { useState } from 'react'
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LabelList,
} from 'recharts'
import { useBacktestStore } from '../store/useBacktestStore'

const TABS = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'dow', label: 'Day of Week' },
  { key: 'hourly', label: 'Hour' },
]

function fmtMoney(v) {
  if (v == null || isNaN(v)) return ''
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(0)}`
}

function DowTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-bg border border-border text-xs p-2">
      <div className="font-semibold">{d.dow}</div>
      <div>P&L: <span className={d.pnl >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(d.pnl)}</span></div>
      <div>Win rate: {d.win_rate?.toFixed(1)}%</div>
      <div>Trades: {d.trades} ({d.wins}W / {d.trades - d.wins}L)</div>
    </div>
  )
}

export default function Breakdowns() {
  const results = useBacktestStore((s) => s.results)
  const [tab, setTab] = useState('monthly')
  if (!results) return null

  const dataMap = {
    monthly: { rows: results.monthly_breakdown, x: 'month' },
    dow: { rows: results.dow_breakdown, x: 'dow' },
    hourly: { rows: results.hourly_breakdown, x: 'hour' },
  }
  const { rows, x } = dataMap[tab]

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-200">Breakdowns</h2>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`btn ${tab === t.key ? 'btn-primary' : 'btn-ghost'} px-3 py-1 text-xs`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={tab === 'dow' ? 220 : 180}>
        <BarChart data={rows} margin={{ top: 20, right: 10, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey={x} stroke="#6b7280" fontSize={10} />
          <YAxis stroke="#6b7280" fontSize={10} />
          <Tooltip
            content={tab === 'dow' ? <DowTooltip /> : undefined}
            contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }}
          />
          <Bar dataKey="pnl">
            {rows?.map((r, i) => (
              <Cell key={i} fill={r.pnl >= 0 ? '#22c55e' : '#ef4444'} />
            ))}
            {tab === 'dow' && (
              <LabelList
                dataKey="win_rate"
                position="top"
                fill="#e5e7eb"
                fontSize={11}
                formatter={(v) => (v != null ? `${v.toFixed(0)}%` : '')}
              />
            )}
            {tab === 'dow' && (
              <LabelList
                dataKey="trades"
                position="bottom"
                fill="#6b7280"
                fontSize={10}
                formatter={(v) => (v != null ? `n=${v}` : '')}
              />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
