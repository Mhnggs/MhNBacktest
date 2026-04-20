import { useBacktestStore } from '../store/useBacktestStore'

function Stat({ label, value, tone }) {
  const toneClass = tone === 'good'
    ? 'text-good'
    : tone === 'bad'
    ? 'text-bad'
    : tone === 'warn'
    ? 'text-warn'
    : 'text-gray-300'
  return (
    <>
      <div className="text-gray-400">{label}</div>
      <div className={`text-right font-mono ${toneClass}`}>{value}</div>
    </>
  )
}

function pct(num, denom) {
  if (!denom) return '—'
  return `${((num / denom) * 100).toFixed(1)}%`
}

function FunnelRow({ label, value, of, hint }) {
  const bar = of > 0 ? Math.min(100, (value / of) * 100) : 0
  return (
    <div className="grid grid-cols-[1fr_80px_60px] gap-2 items-center">
      <div className="text-gray-300" title={hint || ''}>{label}</div>
      <div className="bg-border h-1.5 rounded-full overflow-hidden">
        <div
          className="h-full"
          style={{
            width: `${bar}%`,
            background: bar > 50 ? '#22c55e' : bar > 20 ? '#eab308' : '#ef4444',
          }}
        />
      </div>
      <div className="text-right font-mono text-gray-300">
        {value}
        <span className="text-gray-500 text-[10px] ml-1">({pct(value, of)})</span>
      </div>
    </div>
  )
}

export default function Diagnostics() {
  const results = useBacktestStore((s) => s.results)
  if (!results) return null
  const d = results.diagnostics || {}
  const funnel = d.setup_funnel || {}
  const kzBars = funnel.kill_zone_bars || 0

  return (
    <div className="card text-xs space-y-3">
      <h2 className="text-sm font-semibold text-gray-200">Setup Funnel</h2>

      {kzBars === 0 ? (
        <div className="text-gray-500 italic">
          No kill-zone bars in this range. Enable a kill zone and/or widen the date window.
        </div>
      ) : (
        <div className="space-y-1.5">
          <FunnelRow
            label="Kill-zone bars"
            value={funnel.kill_zone_bars || 0}
            of={funnel.kill_zone_bars || 0}
            hint="Bars inside an enabled kill zone (before filtering)"
          />
          <FunnelRow
            label="Sweeps detected"
            value={funnel.sweeps || 0}
            of={funnel.kill_zone_bars || 0}
            hint="Liquidity sweeps confirmed during a kill zone"
          />
          <FunnelRow
            label="After displacement"
            value={funnel.displacements || 0}
            of={funnel.sweeps || 0}
            hint="Sweeps that produced a displacement bar"
          />
          <FunnelRow
            label="After FVG formed"
            value={funnel.fvgs || 0}
            of={funnel.displacements || 0}
            hint="Displacements that produced a valid FVG"
          />
          <FunnelRow
            label="After MSS confirmed"
            value={funnel.mss || 0}
            of={funnel.fvgs || 0}
            hint="FVGs that also saw a market-structure shift"
          />
          <FunnelRow
            label="After HTF aligned"
            value={funnel.htf_aligned || 0}
            of={funnel.mss || funnel.fvgs || 0}
            hint="Setups that matched the 1H bias"
          />
          <FunnelRow
            label="Trades taken"
            value={funnel.entries_taken || 0}
            of={funnel.kill_zone_bars || 0}
            hint="Actual entries taken after all filters"
          />
        </div>
      )}

      <div className="border-t border-border pt-2">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Skip reasons</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <Stat label="Daily trade limit" value={d.skipped_daily_limit || 0} />
          <Stat label="Kill-zone limit" value={d.skipped_killzone_limit || 0} />
          <Stat label="Low confluence" value={d.skipped_low_confluence || 0} tone="warn" />
          <Stat label="FVG mitigated" value={d.skipped_fvg_mitigated || 0} />
          <Stat label="R:R too thin" value={d.skipped_r_ratio || 0} />
          <Stat label="News day" value={d.skipped_news || 0} />
          <Stat label="Wrong day of week" value={d.skipped_wrong_day || 0} />
          <Stat label="Open trade" value={d.skipped_open_trade || 0} />
          <Stat label="Circuit breaker" value={d.skipped_circuit_breaker || 0} tone="bad" />
        </div>
      </div>

      {results.trades?.length === 0 && (
        <div className="border-t border-border pt-2 text-[11px] text-warn leading-relaxed">
          Zero trades. Common fixes: lower min_sweep_pips, lower displacement_body_pips,
          reduce min_confluence_score, or disable MSS / HTF filters.
        </div>
      )}
    </div>
  )
}
