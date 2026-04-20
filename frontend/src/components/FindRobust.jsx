import { useEffect, useMemo, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'
import { getOptimizeOptions, runAutoRobust } from '../api/client'

const METRIC_LABELS = {
  sharpe_ratio: 'Sharpe Ratio',
  total_return_pct: 'Total Return %',
  profit_factor: 'Profit Factor',
  total_trades: 'Total Trades',
  win_rate: 'Win Rate %',
  max_drawdown_pct: 'Max Drawdown %',
}

const TIER_STYLES = {
  good: 'bg-good/20 border-good text-good',
  warn: 'bg-yellow-500/15 border-yellow-500 text-yellow-300',
  bad: 'bg-bad/20 border-bad text-bad',
  unknown: 'bg-gray-700/40 border-gray-500 text-gray-300',
}

function range(start, end, step) {
  const out = []
  const eps = 1e-9
  if (step <= 0) return out
  for (let v = start; v <= end + eps; v += step) {
    out.push(Number(v.toFixed(6)))
  }
  return out
}

function fmtPct(v, d = 1) {
  if (v == null || isNaN(v)) return '—'
  return `${v.toFixed(d)}%`
}

function fmtNum(v, d = 2) {
  if (v == null || isNaN(v)) return '—'
  return v.toFixed(d)
}

function AxisRow({ axis, setAxis, onRemove, options, excludeKeys }) {
  const spec = options.find((o) => o.key === axis.key)
  return (
    <div className="grid grid-cols-12 gap-2 items-end bg-bg border border-border rounded-md p-2">
      <div className="col-span-4">
        <div className="text-[10px] text-gray-500 mb-0.5">Parameter</div>
        <select
          className="input text-xs py-1"
          value={axis.key}
          onChange={(e) => setAxis({ ...axis, key: e.target.value })}
        >
          {options.filter((o) => !excludeKeys.includes(o.key) || o.key === axis.key)
            .map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
      <div className="col-span-2">
        <div className="text-[10px] text-gray-500 mb-0.5">Start</div>
        <input className="input text-xs py-1" type="number"
          value={axis.start}
          onChange={(e) => setAxis({ ...axis, start: Number(e.target.value) })} />
      </div>
      <div className="col-span-2">
        <div className="text-[10px] text-gray-500 mb-0.5">End</div>
        <input className="input text-xs py-1" type="number"
          value={axis.end}
          onChange={(e) => setAxis({ ...axis, end: Number(e.target.value) })} />
      </div>
      <div className="col-span-2">
        <div className="text-[10px] text-gray-500 mb-0.5">Step</div>
        <input className="input text-xs py-1" type="number"
          value={axis.step}
          onChange={(e) => setAxis({ ...axis, step: Number(e.target.value) })} />
      </div>
      <div className="col-span-1 text-[10px] text-gray-400 text-right pr-1">
        {range(axis.start, axis.end, axis.step).length} vals
        {spec?.integer ? ' (int)' : ''}
      </div>
      <div className="col-span-1 text-right">
        {onRemove && (
          <button className="btn btn-ghost px-2 py-1 text-xs" onClick={onRemove}>×</button>
        )}
      </div>
    </div>
  )
}

function ResultRow({ row, onApply }) {
  const tier = row.consistency?.tier || 'unknown'
  const label = row.consistency?.label || '—'
  const paramStr = Object.entries(row.params || {})
    .map(([k, v]) => `${k}=${typeof v === 'number' ? Number(v).toFixed(2) : v}`)
    .join(', ')
  return (
    <tr className="border-b border-border/60 hover:bg-bg/60">
      <td className="px-2 py-1.5 text-gray-400 font-mono text-xs">{row.rank}</td>
      <td className="px-2 py-1.5">
        <span className={`inline-block px-2 py-0.5 rounded border text-[10px] font-semibold ${TIER_STYLES[tier]}`}>
          {label}
        </span>
      </td>
      <td className="px-2 py-1.5 font-mono text-xs text-gray-200 max-w-[420px] truncate" title={paramStr}>
        {paramStr}
      </td>
      <td className="px-2 py-1.5 font-mono text-right">{fmtNum(row.test_stats?.sharpe_ratio)}</td>
      <td className="px-2 py-1.5 font-mono text-right">{fmtNum(row.test_stats?.profit_factor)}</td>
      <td className="px-2 py-1.5 font-mono text-right">{fmtPct(row.test_stats?.win_rate)}</td>
      <td className="px-2 py-1.5 font-mono text-right">{row.test_stats?.total_trades ?? 0}</td>
      <td className="px-2 py-1.5 font-mono text-right">{fmtPct(row.test_stats?.total_return_pct, 2)}</td>
      <td className="px-2 py-1.5 font-mono text-right text-gray-400">{fmtNum(row.train_stats?.sharpe_ratio)}</td>
      <td className="px-2 py-1.5 text-right">
        <button className="btn btn-ghost px-2 py-0.5 text-[10px]" onClick={() => onApply(row.params)}>
          Apply
        </button>
      </td>
    </tr>
  )
}

export default function FindRobust() {
  const {
    sessionId, params, startDate, endDate,
    isRunning, setRunning, setError,
    autoRobustResults, setAutoRobustResults, applyParams, setActiveView,
  } = useBacktestStore()

  const [options, setOptions] = useState([])
  const [axes, setAxes] = useState([
    { key: 'min_sweep_pips', start: 2, end: 8, step: 2 },
    { key: 'displacement_body_pips', start: 4, end: 12, step: 2 },
  ])
  const [metric, setMetric] = useState('sharpe_ratio')
  const [trainPct, setTrainPct] = useState(0.7)
  const [topK, setTopK] = useState(10)
  const [minTestTrades, setMinTestTrades] = useState(5)
  const [onlyPassing, setOnlyPassing] = useState(true)

  useEffect(() => {
    getOptimizeOptions().then((d) => setOptions(d.params || [])).catch(() => {})
  }, [])

  const excludeKeys = axes.map((a) => a.key)
  const totalCombos = axes.reduce((acc, a) => acc * range(a.start, a.end, a.step).length, 1)
  const maxCombos = 500

  function setAxisAt(idx, newAxis) {
    setAxes((prev) => prev.map((a, i) => (i === idx ? newAxis : a)))
  }
  function addAxis() {
    if (axes.length >= 3) return
    const taken = new Set(axes.map((a) => a.key))
    const next = options.find((o) => !taken.has(o.key))
    if (!next) return
    setAxes([...axes, { key: next.key, start: next.min, end: Math.min(next.max, next.min + 5), step: next.integer ? 1 : 0.5 }])
  }
  function removeAxis(i) {
    setAxes(axes.filter((_, idx) => idx !== i))
  }

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
      return
    }
    if (totalCombos === 0) {
      setError('Ranges produce 0 combinations.')
      return
    }
    if (totalCombos > maxCombos) {
      setError(`${totalCombos} combinations exceeds cap of ${maxCombos}. Widen the step.`)
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await runAutoRobust({
        session_id: sessionId,
        params,
        start_date: startDate || null,
        end_date: endDate || null,
        sweeps: axes.map((a) => ({ key: a.key, values: range(a.start, a.end, a.step) })),
        train_pct: trainPct,
        top_k: topK,
        primary_metric: metric,
        min_test_trades: minTestTrades,
      })
      setAutoRobustResults(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setRunning(false)
    }
  }

  function handleApply(rowParams) {
    applyParams(rowParams)
    setActiveView('backtest')
  }

  const displayedRows = useMemo(() => {
    const rows = autoRobustResults?.results || []
    return onlyPassing ? rows.filter((r) => r.robust_enough) : rows
  }, [autoRobustResults, onlyPassing])

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-sm font-semibold text-gray-200">Find Robust Parameters</h2>
          <div className="text-xs text-gray-400">
            {totalCombos} / {maxCombos} combinations
          </div>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">
          One pass: the backend sweeps the ranges on the full dataset, picks the
          top-K by your metric, then walk-forwards each one and keeps only the
          configurations that still had positive Sharpe and profit factor on the
          held-out test period. Rows flagged <b>ROBUST</b> or <b>MARGINAL</b>
          cleared the out-of-sample bar; <b>CURVE FITTED</b> rows didn't.
        </p>

        <div className="space-y-2">
          {axes.map((a, i) => (
            <AxisRow
              key={i}
              axis={a}
              setAxis={(na) => setAxisAt(i, na)}
              onRemove={axes.length > 1 ? () => removeAxis(i) : null}
              options={options}
              excludeKeys={excludeKeys.filter((_, idx) => idx !== i)}
            />
          ))}
          {axes.length < 3 && (
            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={addAxis}>
              + Add axis
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <div>
            <div className="label">Rank by</div>
            <select className="input text-xs py-1" value={metric} onChange={(e) => setMetric(e.target.value)}>
              {Object.entries(METRIC_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <div className="label">Train split</div>
            <div className="flex items-center gap-2">
              <input type="range" className="accent-accent flex-1" min={0.3} max={0.9} step={0.05}
                value={trainPct} onChange={(e) => setTrainPct(Number(e.target.value))} />
              <span className="font-mono text-xs text-gray-200 w-10 text-right">
                {(trainPct * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <div>
            <div className="label">Validate top-K</div>
            <input className="input text-xs py-1" type="number" min={1} max={50}
              value={topK} onChange={(e) => setTopK(Number(e.target.value))} />
          </div>
          <div>
            <div className="label">Min test trades</div>
            <input className="input text-xs py-1" type="number" min={0}
              value={minTestTrades} onChange={(e) => setMinTestTrades(Number(e.target.value))} />
          </div>
        </div>

        <button
          className="btn btn-primary w-full py-2"
          disabled={isRunning || totalCombos === 0 || totalCombos > maxCombos}
          onClick={handleRun}
        >
          {isRunning ? 'Working…' : `Find Robust Params (${totalCombos} combos)`}
        </button>
      </div>

      {!autoRobustResults && (
        <div className="card text-sm text-gray-400">
          Pick 1–3 parameters and ranges, then press the button. The server does
          the sweeping and out-of-sample validation; you get a clean ranked list.
        </div>
      )}

      {autoRobustResults && (
        <div className="card space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-gray-400">
              Evaluated <span className="text-gray-100 font-mono">{autoRobustResults.evaluated}</span> combos ·
              Split at <span className="text-gray-100 font-mono">{autoRobustResults.split_datetime?.slice(0, 10)}</span> ·
              Train {autoRobustResults.train_bars} / Test {autoRobustResults.test_bars} bars
            </div>
            <label className="flex items-center gap-1 text-xs text-gray-300 cursor-pointer">
              <input type="checkbox" className="accent-accent" checked={onlyPassing}
                onChange={(e) => setOnlyPassing(e.target.checked)} />
              Only passing rows
            </label>
          </div>

          <div className="flex flex-wrap gap-3 text-[11px]">
            <span className={`px-2 py-0.5 rounded border ${TIER_STYLES.good}`}>
              ROBUST: {autoRobustResults.tier_counts?.good || 0}
            </span>
            <span className={`px-2 py-0.5 rounded border ${TIER_STYLES.warn}`}>
              MARGINAL: {autoRobustResults.tier_counts?.warn || 0}
            </span>
            <span className={`px-2 py-0.5 rounded border ${TIER_STYLES.bad}`}>
              CURVE FITTED: {autoRobustResults.tier_counts?.bad || 0}
            </span>
            {(autoRobustResults.tier_counts?.unknown || 0) > 0 && (
              <span className={`px-2 py-0.5 rounded border ${TIER_STYLES.unknown}`}>
                NO TEST TRADES: {autoRobustResults.tier_counts.unknown}
              </span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-400 border-b border-border">
                <tr>
                  <th className="px-2 py-2 text-left">#</th>
                  <th className="px-2 py-2 text-left">Verdict</th>
                  <th className="px-2 py-2 text-left">Parameters</th>
                  <th className="px-2 py-2 text-right">Test Sharpe</th>
                  <th className="px-2 py-2 text-right">Test PF</th>
                  <th className="px-2 py-2 text-right">Test WR</th>
                  <th className="px-2 py-2 text-right">Test Trades</th>
                  <th className="px-2 py-2 text-right">Test Return</th>
                  <th className="px-2 py-2 text-right text-gray-500">Train Sharpe</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {displayedRows.map((r) => (
                  <ResultRow key={r.rank} row={r} onApply={handleApply} />
                ))}
                {!displayedRows.length && (
                  <tr>
                    <td colSpan={10} className="px-2 py-6 text-center text-gray-500">
                      No rows match the current filter.
                      {onlyPassing && ' Uncheck "Only passing rows" to see everything.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="text-[10px] text-gray-500 leading-relaxed">
            "Apply" copies those parameter values into the strategy panel and
            switches to the Backtest tab so you can inspect the trades.
          </div>
        </div>
      )}
    </div>
  )
}
