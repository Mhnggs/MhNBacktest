import { useMemo, useState } from 'react'
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LabelList, ReferenceLine,
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

function winRateColor(wr, hasTrades) {
  if (!hasTrades) return '#1f2937'
  if (wr > 60) return '#15803d'
  if (wr >= 50) return '#22c55e'
  if (wr >= 40) return '#eab308'
  return '#ef4444'
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

function HourTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  if (!d.trades) return (
    <div className="bg-bg border border-border text-xs p-2">
      <div className="font-semibold">{d.hour.toString().padStart(2, '0')}:00</div>
      <div className="text-gray-500">No trades</div>
    </div>
  )
  return (
    <div className="bg-bg border border-border text-xs p-2">
      <div className="font-semibold">{d.hour.toString().padStart(2, '0')}:00</div>
      <div>Trades: {d.trades} ({d.wins}W / {d.losses}L)</div>
      <div>Win rate: {d.win_rate?.toFixed(1)}%</div>
      <div>P&L: <span className={d.pnl >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(d.pnl)}</span></div>
      <div>Avg: {fmtMoney(d.avg_pnl)}</div>
    </div>
  )
}

export default function Breakdowns() {
  const results = useBacktestStore((s) => s.results)
  const [tab, setTab] = useState('monthly')

  const hourly24 = useMemo(() => {
    const map = new Map((results?.hourly_breakdown || []).map((r) => [r.hour, r]))
    return Array.from({ length: 24 }, (_, h) => {
      const row = map.get(h)
      return row || { hour: h, trades: 0, wins: 0, losses: 0, pnl: 0, avg_pnl: 0, win_rate: 0 }
    })
  }, [results])

  if (!results) return null

  const dataMap = {
    monthly: { rows: results.monthly_breakdown, x: 'month' },
    dow: { rows: results.dow_breakdown, x: 'dow' },
    hourly: { rows: hourly24, x: 'hour' },
  }
  const { rows, x } = dataMap[tab]
  const sessionMarkers = results.session_markers || []

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
      <ResponsiveContainer width="100%" height={tab === 'dow' ? 220 : tab === 'hourly' ? 240 : 180}>
        <BarChart data={rows} margin={{ top: 20, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey={x}
            stroke="#6b7280"
            fontSize={10}
            type={tab === 'hourly' ? 'number' : 'category'}
            domain={tab === 'hourly' ? [-0.5, 23.5] : undefined}
            ticks={tab === 'hourly' ? Array.from({ length: 24 }, (_, i) => i) : undefined}
            tickFormatter={tab === 'hourly' ? (v) => String(v).padStart(2, '0') : undefined}
          />
          <YAxis stroke="#6b7280" fontSize={10} />
          <Tooltip
            content={tab === 'dow' ? <DowTooltip /> : tab === 'hourly' ? <HourTooltip /> : undefined}
            contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }}
          />
          {tab === 'hourly' && sessionMarkers.map((m, i) => (
            <ReferenceLine
              key={i}
              x={m.hour}
              stroke={m.label.includes('start') ? '#22d3ee' : '#a855f7'}
              strokeDasharray="4 4"
              label={{ value: m.label, fill: '#9ca3af', fontSize: 10, position: 'insideTop' }}
            />
          ))}
          <Bar dataKey="pnl">
            {rows?.map((r, i) => {
              let fill
              if (tab === 'hourly') fill = winRateColor(r.win_rate, r.trades > 0)
              else fill = r.pnl >= 0 ? '#22c55e' : '#ef4444'
              return <Cell key={i} fill={fill} />
            })}
            {tab === 'dow' && (
              <>
                <LabelList dataKey="win_rate" position="top" fill="#e5e7eb" fontSize={11}
                  formatter={(v) => (v != null ? `${v.toFixed(0)}%` : '')} />
                <LabelList dataKey="trades" position="bottom" fill="#6b7280" fontSize={10}
                  formatter={(v) => (v != null ? `n=${v}` : '')} />
              </>
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {tab === 'hourly' && (
        <div className="flex flex-wrap gap-3 text-[10px] text-gray-400 mt-2 justify-center">
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#15803d'}} /> {'>60% WR'}</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#22c55e'}} /> 50–60%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#eab308'}} /> 40–50%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#ef4444'}} /> {'<40% WR'}</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 border border-cyan-400" /> session start</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 border border-purple-500" /> session end</span>
        </div>
      )}
    </div>
  )
}
