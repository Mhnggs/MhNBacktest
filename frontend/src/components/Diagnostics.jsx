import { useBacktestStore } from '../store/useBacktestStore'

const FILTER_LABELS = {
  rejected_vwap_side: 'Wrong side of VWAP',
  rejected_ema_slope: 'EMA slope too flat',
  rejected_ema_touch: 'No EMA pullback touch',
  rejected_candle_dir: 'Candle wrong direction',
  rejected_volume: 'Volume below multiplier',
  rejected_vwap_distance: 'Too far from VWAP',
  rejected_chop: 'Too many VWAP crossings',
  rejected_pattern: 'No candle pattern',
  rejected_max_per_day: 'Daily trade cap',
  rejected_open_trade: 'Already in trade',
}

export default function Diagnostics() {
  const results = useBacktestStore((s) => s.results)
  if (!results) return null
  const d = results.diagnostics || {}
  const totalTrades = results.trades?.length || 0

  if (totalTrades > 0) {
    return (
      <div className="card text-xs">
        <h2 className="text-sm font-semibold text-gray-200 mb-2">Diagnostics</h2>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-gray-300">
          <div>Bars processed</div><div className="text-right font-mono">{d.total_bars}</div>
          <div>In session</div><div className="text-right font-mono">{d.in_session_bars}</div>
          <div>Long signals</div><div className="text-right font-mono text-good">{d.long_signals}</div>
          <div>Short signals</div><div className="text-right font-mono text-bad">{d.short_signals}</div>
          {!d.volume_filter_active && (
            <div className="col-span-2 text-warn">Volume filter auto-disabled (no volume data)</div>
          )}
        </div>
      </div>
    )
  }

  // Zero trades — show why
  const rejections = Object.entries(FILTER_LABELS)
    .map(([k, label]) => [label, d[k] || 0])
    .sort((a, b) => b[1] - a[1])

  return (
    <div className="card">
      <h2 className="text-sm font-semibold text-warn mb-2">Zero trades — why?</h2>
      <div className="text-xs text-gray-400 mb-3">
        {d.total_bars || 0} bars processed · {d.in_session_bars || 0} in session · {d.candidate_bars || 0} candidates
        {!d.volume_filter_active && (
          <div className="text-warn mt-1">Volume filter auto-disabled (no volume data)</div>
        )}
      </div>
      <div className="space-y-1 text-xs">
        {rejections.map(([label, count]) => (
          <div key={label} className="flex justify-between">
            <span className="text-gray-300">{label}</span>
            <span className="font-mono text-gray-400">{count}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 text-[11px] text-gray-500 leading-relaxed border-t border-border pt-2">
        Common fixes: turn off "Require Candle Pattern", widen session times, lower
        "Min EMA Slope", or check that your session timezone matches the data.
      </div>
    </div>
  )
}
