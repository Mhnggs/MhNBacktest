import { useState } from 'react'
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { useBacktestStore } from '../store/useBacktestStore'

const TABS = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'dow', label: 'Day of Week' },
  { key: 'hourly', label: 'Hour' },
]

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
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey={x} stroke="#6b7280" fontSize={10} />
          <YAxis stroke="#6b7280" fontSize={10} />
          <Tooltip contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }} />
          <Bar dataKey="pnl">
            {rows?.map((r, i) => (
              <Cell key={i} fill={r.pnl >= 0 ? '#22c55e' : '#ef4444'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
