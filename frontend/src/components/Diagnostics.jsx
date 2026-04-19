import { useBacktestStore } from '../store/useBacktestStore'

const FILTER_LABELS = {
  rejected_day_of_week: 'Day of week not allowed',
  rejected_max_per_day: 'Daily trade cap',
  rejected_open_trade: 'Already in trade',
  rejected_no_pattern: 'No pattern on crossover bar',
}

export default function Diagnostics() {
  const results = useBacktestStore((s) => s.results)
  if (!results) return null
  const d = results.diagnostics || {}
  const totalTrades = results.trades?.length || 0
  const patternCounts = d.pattern_counts || {}
  const patternEntries = Object.entries(patternCounts).sort((a, b) => b[1] - a[1])

  if (totalTrades > 0) {
    return (
      <div className="card text-xs">
        <h2 className="text-sm font-semibold text-gray-200 mb-2">Diagnostics</h2>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-gray-300">
          <div>Bars processed</div><div className="text-right font-mono">{d.total_bars || 0}</div>
          <div>In session</div><div className="text-right font-mono">{d.in_session_bars || 0}</div>
          <div>Bullish crosses</div><div className="text-right font-mono text-good">{d.bullish_crosses || 0}</div>
          <div>Bearish crosses</div><div className="text-right font-mono text-bad">{d.bearish_crosses || 0}</div>
          <div>Long signals</div><div className="text-right font-mono text-good">{d.long_signals || 0}</div>
          <div>Short signals</div><div className="text-right font-mono text-bad">{d.short_signals || 0}</div>
          <div>Rejected (no pattern)</div><div className="text-right font-mono">{d.rejected_no_pattern || 0}</div>
          <div>Rejected (day filter)</div><div className="text-right font-mono">{d.rejected_day_of_week || 0}</div>
          <div>Rejected (daily cap)</div><div className="text-right font-mono">{d.rejected_max_per_day || 0}</div>
          <div>Rejected (in trade)</div><div className="text-right font-mono">{d.rejected_open_trade || 0}</div>
        </div>
        {patternEntries.length > 0 && (
          <div className="mt-3 border-t border-border pt-2">
            <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
              Patterns that fired
            </div>
            <div className="space-y-1">
              {patternEntries.map(([name, count]) => (
                <div key={name} className="flex justify-between text-xs">
                  <span className="text-gray-300">{name}</span>
                  <span className="font-mono text-gray-400">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
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
      <div className="text-xs text-gray-400 mb-3 space-y-0.5">
        <div>{d.total_bars || 0} bars processed · {d.in_session_bars || 0} in session</div>
        <div>{d.bullish_crosses || 0} bullish crosses · {d.bearish_crosses || 0} bearish crosses</div>
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
        Common fixes: select more candlestick patterns, widen session times, allow more days,
        or check that your session timezone matches the data.
      </div>
    </div>
  )
}
