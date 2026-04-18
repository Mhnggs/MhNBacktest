import { useBacktestStore } from '../store/useBacktestStore'

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function fmtPct(v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

function Metric({ label, value, sub, accent }) {
  const color = accent === 'good' ? 'text-good' : accent === 'bad' ? 'text-bad' : 'text-gray-100'
  return (
    <div className="bg-bg border border-border rounded-md p-3">
      <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
      {sub && <div className="text-[11px] text-gray-500">{sub}</div>}
    </div>
  )
}

export default function StatsPanel() {
  const results = useBacktestStore((s) => s.results)
  const error = useBacktestStore((s) => s.error)

  if (error) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold text-bad mb-2">Error</h2>
        <div className="text-xs text-gray-300 break-words">{error}</div>
      </div>
    )
  }

  if (!results) {
    return (
      <div className="card text-sm text-gray-400">
        Run a backtest to see performance metrics.
      </div>
    )
  }

  const s = results.stats
  return (
    <div className="card space-y-3">
      <h2 className="text-sm font-semibold text-gray-200">Performance</h2>

      <div className="grid grid-cols-2 gap-2">
        <Metric label="Total Return" value={fmtPct(s.total_return_pct)} accent={s.total_return_pct >= 0 ? 'good' : 'bad'} />
        <Metric label="Win Rate" value={fmtPct(s.win_rate, 1)} />
        <Metric label="Profit Factor" value={s.profit_factor?.toFixed(2)} />
        <Metric label="Max Drawdown" value={fmtPct(s.max_drawdown_pct)} accent="bad" />
      </div>

      <div className="grid grid-cols-2 gap-2 pt-1">
        <Metric label="Trades" value={s.total_trades} sub={`${s.wins}W / ${s.losses}L`} />
        <Metric label="Sharpe" value={s.sharpe_ratio?.toFixed(2)} />
        <Metric label="Avg Win" value={fmtMoney(s.avg_win)} accent="good" />
        <Metric label="Avg Loss" value={fmtMoney(s.avg_loss)} accent="bad" />
        <Metric label="Best" value={fmtMoney(s.best_trade)} accent="good" />
        <Metric label="Worst" value={fmtMoney(s.worst_trade)} accent="bad" />
        <Metric label="Avg Duration" value={`${Math.round(s.avg_trade_duration_min || 0)}m`} />
        <Metric label="Streaks" value={`${s.max_consecutive_wins}W / ${s.max_consecutive_losses}L`} />
      </div>

      <div className="border-t border-border pt-2 flex justify-between text-xs">
        <span className="text-gray-400">Final Equity</span>
        <span className="font-semibold">{fmtMoney(s.final_equity)}</span>
      </div>
    </div>
  )
}
