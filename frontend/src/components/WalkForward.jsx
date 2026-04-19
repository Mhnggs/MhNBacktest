import { useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { useBacktestStore } from '../store/useBacktestStore'
import { runWalkForward } from '../api/client'
import { SESSION_SCOPES, applySessionScope } from '../util/sessionScope'

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function fmtPct(v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

function fmtNum(v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return v.toFixed(digits)
}

function StatCell({ label, train, test, format = fmtNum, accentSign = false }) {
  const color = (v) => {
    if (!accentSign) return 'text-gray-100'
    if (v == null || isNaN(v)) return 'text-gray-400'
    return v >= 0 ? 'text-good' : 'text-bad'
  }
  return (
    <tr className="border-b border-border/60">
      <td className="py-1.5 text-gray-400 text-xs">{label}</td>
      <td className={`py-1.5 text-right font-mono text-sm ${color(train)}`}>{format(train)}</td>
      <td className={`py-1.5 text-right font-mono text-sm ${color(test)}`}>{format(test)}</td>
    </tr>
  )
}

function ConsistencyBadge({ consistency }) {
  if (!consistency) return null
  const map = {
    good: 'bg-good/20 border-good text-good',
    warn: 'bg-yellow-500/15 border-yellow-500 text-yellow-300',
    bad: 'bg-bad/20 border-bad text-bad',
    unknown: 'bg-gray-700/40 border-gray-500 text-gray-300',
  }
  const cls = map[consistency.tier] || map.unknown
  return (
    <div className={`border rounded-md p-3 ${cls}`}>
      <div className="flex items-center justify-between">
        <div className="text-lg font-bold tracking-wide">{consistency.label}</div>
        {consistency.sharpe_degradation_pct != null && (
          <div className="text-xs opacity-80">
            Sharpe Δ: {consistency.sharpe_degradation_pct.toFixed(1)}%
          </div>
        )}
      </div>
      <div className="text-xs mt-1 opacity-90">{consistency.note}</div>
    </div>
  )
}

export default function WalkForward() {
  const {
    sessionId, params, startDate, endDate,
    isRunning, setRunning, setError,
    walkForwardResults, setWalkForwardResults,
    walkForwardTrainPct, setWalkForwardTrainPct,
  } = useBacktestStore()
  const [sessionScope, setSessionScope] = useState('all')

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await runWalkForward({
        session_id: sessionId,
        params: applySessionScope(params, sessionScope),
        start_date: startDate || null,
        end_date: endDate || null,
        train_pct: walkForwardTrainPct,
      })
      setWalkForwardResults(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setRunning(false)
    }
  }

  const combined = useMemo(() => {
    if (!walkForwardResults) return []
    const train = walkForwardResults.train.equity_curve.map((p) => ({
      t: p.datetime,
      label: p.datetime.slice(0, 10),
      train: p.equity,
    }))
    const test = walkForwardResults.test.equity_curve.map((p) => ({
      t: p.datetime,
      label: p.datetime.slice(0, 10),
      test: p.equity,
    }))
    return [...train, ...test]
  }, [walkForwardResults])

  const splitLabel = walkForwardResults?.split_datetime?.slice(0, 10)

  return (
    <div className="space-y-4">
      <div className="card flex items-center justify-between gap-4">
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-gray-200 mb-2">Walk Forward Test</h2>
          <p className="text-xs text-gray-400 leading-relaxed">
            Splits the date range chronologically: the first portion is treated as the
            in-sample (train) period the strategy is "built on", and the remainder is
            held out as unseen data. If the strategy only works on the train half, it's
            likely curve-fit.
          </p>
        </div>
        <div className="flex items-end gap-3">
          <div>
            <div className="label">Session</div>
            <select
              className="input w-auto text-xs py-1"
              value={sessionScope}
              onChange={(e) => setSessionScope(e.target.value)}
            >
              {SESSION_SCOPES.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
          <div>
            <div className="label">Train split</div>
            <div className="flex items-center gap-2">
              <input
                type="range"
                className="accent-accent"
                min={0.3}
                max={0.9}
                step={0.05}
                value={walkForwardTrainPct}
                onChange={(e) => setWalkForwardTrainPct(Number(e.target.value))}
              />
              <span className="font-mono text-sm text-gray-200 w-12 text-right">
                {(walkForwardTrainPct * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <button
            className="btn btn-primary px-4 py-2 whitespace-nowrap"
            onClick={handleRun}
            disabled={isRunning}
          >
            {isRunning ? 'Running…' : 'Run Walk Forward'}
          </button>
        </div>
      </div>

      {!walkForwardResults && (
        <div className="card text-sm text-gray-400">
          Press <b>Run Walk Forward</b> to split the data and test out-of-sample performance.
        </div>
      )}

      {walkForwardResults && (
        <>
          <ConsistencyBadge consistency={walkForwardResults.consistency} />

          <div className="card">
            <div className="flex items-baseline justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-200">Equity Curve</h3>
              <div className="text-xs text-gray-400">
                Split at <span className="font-mono text-gray-200">{splitLabel}</span> —
                train: {walkForwardResults.train_bars} bars, test: {walkForwardResults.test_bars} bars
              </div>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={combined}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="label" stroke="#6b7280" fontSize={10} minTickGap={40} />
                <YAxis stroke="#6b7280" fontSize={10} domain={['auto', 'auto']}
                  tickFormatter={(v) => fmtMoney(v)} />
                <Tooltip
                  contentStyle={{ background: '#0b0f17', border: '1px solid #1f2937', fontSize: 12 }}
                  formatter={(v) => fmtMoney(v)}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine x={splitLabel} stroke="#f59e0b" strokeDasharray="4 4"
                  label={{ value: 'Split', fill: '#f59e0b', fontSize: 10, position: 'insideTop' }} />
                <Line type="monotone" dataKey="train" name="Train (in-sample)"
                  stroke="#22d3ee" dot={false} strokeWidth={2} connectNulls={false} />
                <Line type="monotone" dataKey="test" name="Test (out-of-sample)"
                  stroke="#a855f7" dot={false} strokeWidth={2} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3 className="text-sm font-semibold text-gray-200 mb-2">Side-by-Side Stats</h3>
            <table className="w-full">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-gray-400 border-b border-border">
                  <th className="py-1.5">Metric</th>
                  <th className="py-1.5 text-right">Train</th>
                  <th className="py-1.5 text-right">Test</th>
                </tr>
              </thead>
              <tbody>
                <StatCell label="Trades"
                  train={walkForwardResults.train.stats.total_trades}
                  test={walkForwardResults.test.stats.total_trades}
                  format={(v) => String(v ?? '—')} />
                <StatCell label="Win Rate"
                  train={walkForwardResults.train.stats.win_rate}
                  test={walkForwardResults.test.stats.win_rate}
                  format={(v) => fmtPct(v, 1)} />
                <StatCell label="Profit Factor"
                  train={walkForwardResults.train.stats.profit_factor}
                  test={walkForwardResults.test.stats.profit_factor} />
                <StatCell label="Sharpe"
                  train={walkForwardResults.train.stats.sharpe_ratio}
                  test={walkForwardResults.test.stats.sharpe_ratio}
                  accentSign />
                <StatCell label="Total Return"
                  train={walkForwardResults.train.stats.total_return_pct}
                  test={walkForwardResults.test.stats.total_return_pct}
                  format={(v) => fmtPct(v)}
                  accentSign />
                <StatCell label="Max Drawdown"
                  train={walkForwardResults.train.stats.max_drawdown_pct}
                  test={walkForwardResults.test.stats.max_drawdown_pct}
                  format={(v) => fmtPct(v)} />
                <StatCell label="Total P&L"
                  train={walkForwardResults.train.stats.total_pnl}
                  test={walkForwardResults.test.stats.total_pnl}
                  format={fmtMoney}
                  accentSign />
                <StatCell label="Avg Win"
                  train={walkForwardResults.train.stats.avg_win}
                  test={walkForwardResults.test.stats.avg_win}
                  format={fmtMoney} />
                <StatCell label="Avg Loss"
                  train={walkForwardResults.train.stats.avg_loss}
                  test={walkForwardResults.test.stats.avg_loss}
                  format={fmtMoney} />
                <StatCell label="Final Equity"
                  train={walkForwardResults.train.stats.final_equity}
                  test={walkForwardResults.test.stats.final_equity}
                  format={fmtMoney} />
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
