import { useEffect, useMemo, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'
import { getOptimizeOptions, runOptimize } from '../api/client'

const DEFAULT_X = 'stop_loss_pips'
const DEFAULT_Y = 'risk_reward'
const DEFAULT_METRIC = 'sharpe_ratio'

const METRIC_LABELS = {
  sharpe_ratio: 'Sharpe Ratio',
  total_return_pct: 'Total Return %',
  profit_factor: 'Profit Factor',
  total_trades: 'Total Trades',
  win_rate: 'Win Rate %',
  max_drawdown_pct: 'Max Drawdown %',
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

function formatVal(v, integer) {
  if (v == null || isNaN(v)) return '—'
  return integer ? String(Math.round(v)) : Number(v).toFixed(2)
}

// Green→red diverging scale around the mid of the value range.
function cellColor(value, min, max) {
  if (min === max) return 'rgba(34, 197, 94, 0.3)'
  const t = (value - min) / (max - min) // 0..1
  // 0 = red, 0.5 = neutral, 1 = green
  const r = Math.round(239 * (1 - t) + 34 * t)
  const g = Math.round(68 * (1 - t) + 197 * t)
  const b = Math.round(68 * (1 - t) + 94 * t)
  const alpha = 0.25 + Math.abs(t - 0.5) * 0.7
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(2)})`
}

function AxisPicker({ label, paramKey, setParamKey, start, setStart, end, setEnd, step, setStep, options, excludeKey }) {
  return (
    <div className="bg-bg border border-border rounded-md p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
        <select
          className="input w-auto text-xs py-0.5"
          value={paramKey}
          onChange={(e) => setParamKey(e.target.value)}
        >
          {options.filter((o) => o.key !== excludeKey).map((o) => (
            <option key={o.key} value={o.key}>{o.label}</option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <div className="text-[10px] text-gray-500 mb-0.5">Start</div>
          <input className="input text-xs py-1" type="number" value={start}
            onChange={(e) => setStart(Number(e.target.value))} />
        </div>
        <div>
          <div className="text-[10px] text-gray-500 mb-0.5">End</div>
          <input className="input text-xs py-1" type="number" value={end}
            onChange={(e) => setEnd(Number(e.target.value))} />
        </div>
        <div>
          <div className="text-[10px] text-gray-500 mb-0.5">Step</div>
          <input className="input text-xs py-1" type="number" value={step}
            onChange={(e) => setStep(Number(e.target.value))} />
        </div>
      </div>
    </div>
  )
}

export default function Optimize() {
  const {
    sessionId, params, startDate, endDate,
    isRunning, setRunning, setError,
    optimizeResults, setOptimizeResults,
  } = useBacktestStore()

  const [options, setOptions] = useState([])
  const [maxCells, setMaxCells] = useState(400)
  const [xParam, setXParam] = useState(DEFAULT_X)
  const [yParam, setYParam] = useState(DEFAULT_Y)
  const [metric, setMetric] = useState(DEFAULT_METRIC)
  const [xStart, setXStart] = useState(10)
  const [xEnd, setXEnd] = useState(40)
  const [xStep, setXStep] = useState(5)
  const [yStart, setYStart] = useState(1.0)
  const [yEnd, setYEnd] = useState(3.0)
  const [yStep, setYStep] = useState(0.5)

  useEffect(() => {
    getOptimizeOptions()
      .then((data) => {
        setOptions(data.params || [])
        setMaxCells(data.max_cells || 400)
      })
      .catch(() => {})
  }, [])

  const xValues = useMemo(() => range(xStart, xEnd, xStep), [xStart, xEnd, xStep])
  const yValues = useMemo(() => range(yStart, yEnd, yStep), [yStart, yEnd, yStep])
  const cellCount = xValues.length * yValues.length
  const xSpec = options.find((o) => o.key === xParam)
  const ySpec = options.find((o) => o.key === yParam)

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
      return
    }
    if (cellCount === 0) {
      setError('Adjust ranges — produced 0 combinations.')
      return
    }
    if (cellCount > maxCells) {
      setError(`${cellCount} combinations exceeds the cap of ${maxCells}.`)
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await runOptimize({
        session_id: sessionId,
        params,
        start_date: startDate || null,
        end_date: endDate || null,
        x_param: xParam,
        x_values: xValues,
        y_param: yParam,
        y_values: yValues,
        metric,
      })
      setOptimizeResults(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setRunning(false)
    }
  }

  const { minVal, maxVal } = useMemo(() => {
    if (!optimizeResults) return { minVal: 0, maxVal: 0 }
    let mn = Infinity, mx = -Infinity
    for (const row of optimizeResults.grid) {
      for (const c of row) {
        if (c.metric_value < mn) mn = c.metric_value
        if (c.metric_value > mx) mx = c.metric_value
      }
    }
    return { minVal: mn, maxVal: mx }
  }, [optimizeResults])

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-200">Parameter Optimization</h2>
          <div className="text-xs text-gray-400">
            {cellCount} / {maxCells} combinations
          </div>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">
          Sweeps two parameters while holding the rest fixed. The heatmap highlights
          where the chosen metric peaks. Values outside each param's bounds are clamped.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <AxisPicker label="X axis" paramKey={xParam} setParamKey={setXParam}
            start={xStart} setStart={setXStart}
            end={xEnd} setEnd={setXEnd}
            step={xStep} setStep={setXStep}
            options={options} excludeKey={yParam} />
          <AxisPicker label="Y axis" paramKey={yParam} setParamKey={setYParam}
            start={yStart} setStart={setYStart}
            end={yEnd} setEnd={setYEnd}
            step={yStep} setStep={setYStep}
            options={options} excludeKey={xParam} />
        </div>

        <div className="flex items-end gap-3">
          <div className="flex-1">
            <div className="label">Metric</div>
            <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
              {Object.entries(METRIC_LABELS).map(([k, l]) => (
                <option key={k} value={k}>{l}</option>
              ))}
            </select>
          </div>
          <button
            className="btn btn-primary px-4 py-2 whitespace-nowrap"
            disabled={isRunning || cellCount === 0 || cellCount > maxCells}
            onClick={handleRun}
          >
            {isRunning ? 'Running…' : 'Run Sweep'}
          </button>
        </div>
      </div>

      {!optimizeResults && (
        <div className="card text-sm text-gray-400">
          Choose axes, set ranges, and press <b>Run Sweep</b>. Each cell runs a full backtest.
        </div>
      )}

      {optimizeResults && (
        <div className="card space-y-3">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-gray-200">
              {METRIC_LABELS[optimizeResults.metric]} heatmap
            </h3>
            {optimizeResults.best && (
              <div className="text-xs text-gray-400">
                Best: <span className="text-good font-mono">
                  {formatVal(optimizeResults.best.metric_value, false)}
                </span>
                {' '}at {xSpec?.label}={formatVal(optimizeResults.best.x, xSpec?.integer)},
                {' '}{ySpec?.label}={formatVal(optimizeResults.best.y, ySpec?.integer)}
              </div>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="border-collapse text-xs">
              <thead>
                <tr>
                  <th className="p-2 text-right text-gray-400 font-normal">
                    {ySpec?.label} ↓ / {xSpec?.label} →
                  </th>
                  {optimizeResults.x_values.map((xv, i) => (
                    <th key={i} className="p-2 font-mono text-gray-400 font-normal">
                      {formatVal(xv, xSpec?.integer)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {optimizeResults.grid.slice().reverse().map((row, ri) => {
                  const originalIdx = optimizeResults.grid.length - 1 - ri
                  const yv = optimizeResults.y_values[originalIdx]
                  return (
                    <tr key={originalIdx}>
                      <td className="p-2 text-right font-mono text-gray-400">
                        {formatVal(yv, ySpec?.integer)}
                      </td>
                      {row.map((cell, ci) => {
                        const isBest = optimizeResults.best
                          && cell.x === optimizeResults.best.x
                          && cell.y === optimizeResults.best.y
                        return (
                          <td
                            key={ci}
                            title={[
                              `${xSpec?.label || 'x'}=${formatVal(cell.x, xSpec?.integer)}`,
                              `${ySpec?.label || 'y'}=${formatVal(cell.y, ySpec?.integer)}`,
                              `${METRIC_LABELS[optimizeResults.metric]}: ${cell.metric_value.toFixed(3)}`,
                              `Trades: ${cell.total_trades}`,
                              `Win rate: ${cell.win_rate.toFixed(1)}%`,
                              `Profit factor: ${cell.profit_factor.toFixed(2)}`,
                              `Sharpe: ${cell.sharpe_ratio.toFixed(2)}`,
                            ].join('\n')}
                            style={{ background: cellColor(cell.metric_value, minVal, maxVal) }}
                            className={`p-2 text-center font-mono min-w-[56px] ${isBest ? 'ring-2 ring-accent' : ''}`}
                          >
                            <div className="text-gray-100">{cell.metric_value.toFixed(2)}</div>
                            <div className="text-[9px] text-gray-400">n={cell.total_trades}</div>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-2 text-[10px] text-gray-400">
            <span>{minVal.toFixed(2)}</span>
            <div className="flex-1 h-2 rounded"
              style={{ background: 'linear-gradient(to right, rgba(239,68,68,0.95), rgba(107,114,128,0.5), rgba(34,197,94,0.95))' }} />
            <span>{maxVal.toFixed(2)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
