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
  { key: 'kill_zone', label: 'Kill Zone' },
  { key: 'sweep_type', label: 'Sweep Type' },
  { key: 'fvg_size', label: 'FVG Size' },
  { key: 'confluence', label: 'Confluence' },
  { key: 'htf_bias', label: 'HTF Bias' },
  { key: 'entry_time', label: 'Entry Time' },
  { key: 'mss', label: 'MSS' },
  { key: 'direction', label: 'Direction' },
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

function GenericTooltip({ active, payload, labelKey }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-bg border border-border text-xs p-2">
      <div className="font-semibold">{d[labelKey]}</div>
      <div>P&L: <span className={d.pnl >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(d.pnl)}</span></div>
      <div>Win rate: {d.win_rate?.toFixed(1)}%</div>
      <div>Trades: {d.trades} ({d.wins}W / {d.losses}L)</div>
      {d.profit_factor != null && (
        <div>Profit factor: {d.profit_factor === 0 ? '—' : d.profit_factor.toFixed(2)}</div>
      )}
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
    monthly: { rows: results.monthly_breakdown, x: 'month', labelKey: 'month' },
    dow: { rows: results.dow_breakdown, x: 'dow', labelKey: 'dow' },
    hourly: { rows: hourly24, x: 'hour', labelKey: 'hour' },
    kill_zone: { rows: results.kill_zone_breakdown || [], x: 'kill_zone', labelKey: 'kill_zone' },
    sweep_type: { rows: results.sweep_type_breakdown || [], x: 'sweep_type', labelKey: 'sweep_type' },
    fvg_size: { rows: results.fvg_size_breakdown || [], x: 'bucket', labelKey: 'bucket' },
    confluence: { rows: results.confluence_breakdown || [], x: 'score', labelKey: 'score' },
    htf_bias: { rows: results.htf_bias_breakdown || [], x: 'bias', labelKey: 'bias' },
    entry_time: { rows: results.entry_time_breakdown || [], x: 'bucket', labelKey: 'bucket' },
    mss: { rows: results.mss_breakdown || [], x: 'bucket', labelKey: 'bucket' },
    direction: { rows: results.direction_breakdown || [], x: 'direction', labelKey: 'direction' },
  }
  const { rows, x, labelKey } = dataMap[tab]
  const sessionMarkers = results.session_markers || []
  const tableTabs = new Set([
    'kill_zone', 'sweep_type', 'fvg_size', 'confluence',
    'htf_bias', 'entry_time', 'mss', 'direction',
  ])

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-sm font-semibold text-gray-200">Breakdowns</h2>
        <div className="flex gap-1 flex-wrap">
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
      <ResponsiveContainer width="100%" height={tab === 'dow' || tableTabs.has(tab) ? 220 : tab === 'hourly' ? 240 : 180}>
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
            content={
              tab === 'dow' ? <DowTooltip />
              : tab === 'hourly' ? <HourTooltip />
              : tableTabs.has(tab) ? <GenericTooltip labelKey={labelKey} />
              : undefined
            }
            contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }}
          />
          {tab === 'hourly' && sessionMarkers.map((m, i) => (
            <ReferenceLine
              key={i}
              x={m.hour}
              stroke={
                m.label.includes('London') ? '#facc15'
                : m.label.includes('PM') ? '#a855f7'
                : '#3b82f6'
              }
              strokeDasharray="4 4"
              label={{ value: m.label, fill: '#9ca3af', fontSize: 9, position: 'insideTop' }}
            />
          ))}
          <Bar dataKey="pnl">
            {rows?.map((r, i) => {
              let fill
              if (tab === 'hourly') fill = winRateColor(r.win_rate, r.trades > 0)
              else fill = r.pnl >= 0 ? '#22c55e' : '#ef4444'
              return <Cell key={i} fill={fill} />
            })}
            {(tab === 'dow' || tableTabs.has(tab)) && (
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

      {tableTabs.has(tab) && (
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-xs">
            <thead className="text-gray-400 border-b border-border">
              <tr>
                <th className="text-left py-1.5 px-2">
                  {tab === 'kill_zone' ? 'Kill Zone'
                   : tab === 'sweep_type' ? 'Sweep Type'
                   : tab === 'confluence' ? 'Score'
                   : tab === 'htf_bias' ? 'HTF Bias'
                   : tab === 'direction' ? 'Direction'
                   : 'Bucket'}
                </th>
                <th className="text-right py-1.5 px-2">Trades</th>
                <th className="text-right py-1.5 px-2">W / L</th>
                <th className="text-right py-1.5 px-2">Win %</th>
                <th className="text-right py-1.5 px-2">PF</th>
                <th className="text-right py-1.5 px-2">P&amp;L</th>
                <th className="text-right py-1.5 px-2">Avg</th>
                <th className="text-right py-1.5 px-2">Best</th>
                <th className="text-right py-1.5 px-2">Worst</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r[labelKey] || i} className="border-b border-border/40">
                  <td className="px-2 py-1.5 font-semibold">{r[labelKey]}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{r.trades}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{r.wins}/{r.losses}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{r.win_rate?.toFixed(1)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {r.profit_factor === 0 ? '—' : r.profit_factor?.toFixed(2)}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.pnl >= 0 ? 'text-good' : 'text-bad'}`}>
                    {fmtMoney(r.pnl)}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.avg_pnl >= 0 ? 'text-good' : 'text-bad'}`}>
                    {fmtMoney(r.avg_pnl)}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-good">{fmtMoney(r.best)}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-bad">{fmtMoney(r.worst)}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={9} className="px-2 py-4 text-center text-gray-500">
                  No trades to bucket.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'hourly' && (
        <div className="flex flex-wrap gap-3 text-[10px] text-gray-400 mt-2 justify-center">
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#15803d'}} /> {'>60% WR'}</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#22c55e'}} /> 50–60%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#eab308'}} /> 40–50%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2" style={{background: '#ef4444'}} /> {'<40% WR'}</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 border border-yellow-400" /> London SB</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 border border-blue-500" /> NY SB</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 border border-purple-400" /> NY PM SB</span>
        </div>
      )}
    </div>
  )
}
