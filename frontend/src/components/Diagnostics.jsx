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

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toISOString().slice(11, 16) + 'Z'
}

function BiasSampleList({ title, rows, showTouch }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="mt-1">
      <div className="text-[11px] text-gray-400">{title}</div>
      <ul className="font-mono text-[11px] text-gray-300 space-y-0.5">
        {rows.map((r, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="text-gray-200">{r.date}</span>
            <span className={r.direction === 'bull' ? 'text-good' : 'text-bad'}>
              {r.direction}
            </span>
            <span className="text-gray-500">brk {fmtTime(r.breakout_time)}</span>
            {showTouch && r.opposite_touch_time && (
              <span className="text-gray-500">→ {fmtTime(r.opposite_touch_time)}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function BiasSamples({ bias }) {
  const held = bias?.held_days_sample
  const failed = bias?.failed_days_sample
  if ((!held || held.length === 0) && (!failed || failed.length === 0)) return null
  return (
    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 border-t border-border/60 pt-2">
      <BiasSampleList title="Held samples (opposite NOT taken)" rows={held} />
      <BiasSampleList
        title="Failed samples (opposite WAS taken)"
        rows={failed}
        showTouch
      />
    </div>
  )
}

export default function Diagnostics() {
  const results = useBacktestStore((s) => s.results)
  if (!results) return null
  const d = results.diagnostics || {}
  const bias = results.dr_directional_bias || {}
  const entries = d.entries_via_retest || 0
  const midEntries = d.entries_via_midpoint || 0
  const breakouts = d.days_with_breakout || 0
  const validDays = d.valid_dr_days || 0
  const totalDays = d.total_days_seen || 0
  const newsByType = d.news_skips_by_type || {}

  // Backend returns *_held_pct already as 0-100.
  const biasOverall = bias.overall_held_pct
  const biasTone = biasOverall == null
    ? 'muted'
    : biasOverall >= 70
    ? 'good'
    : biasOverall >= 55
    ? 'warn'
    : 'bad'

  return (
    <div className="card text-xs space-y-3">
      <h2 className="text-sm font-semibold text-gray-200">Diagnostics</h2>

      <div>
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
          DR Directional Bias <span className="text-gray-400 normal-case">
            (opposite side holds after break)
          </span>
        </div>
        {bias.overall_days ? (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            <Stat
              label="Overall hold rate"
              value={`${biasOverall.toFixed(1)}% (${bias.overall_held}/${bias.overall_days})`}
              tone={biasTone}
            />
            <Stat
              label="Bull breaks → low held"
              value={`${(bias.bull_held_pct ?? 0).toFixed(1)}% (${bias.bull_held}/${bias.bull_break_days})`}
            />
            <Stat
              label="Bear breaks → high held"
              value={`${(bias.bear_held_pct ?? 0).toFixed(1)}% (${bias.bear_held}/${bias.bear_break_days})`}
            />
          </div>
        ) : (
          <div className="text-gray-500 italic">No breakout days yet — run a longer window.</div>
        )}
        <div className="text-[11px] text-gray-500 mt-1 leading-relaxed">
          Opposite side = wick within 2 pips of the opposite DR level between
          breakout and 16:00 NY. Classic claim is ~70%; 60-75% validates the
          edge on your dataset.
        </div>
        <BiasSamples bias={bias} />
      </div>

      <div className="border-t border-border pt-2">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Day funnel</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <Stat label="Days seen" value={totalDays} />
          <Stat label="Valid DR days" value={`${validDays} (${pct(validDays, totalDays)})`} />
          <Stat label="Skipped — narrow" value={d.days_skipped_narrow || 0} />
          <Stat label="Skipped — wide" value={d.days_skipped_wide || 0} />
          <Stat label="Skipped — news" value={d.days_skipped_news || 0} />
          <Stat label="Skipped — day of week" value={d.days_skipped_day_of_week || 0} />
        </div>
        {(newsByType.NFP || newsByType.FOMC || newsByType.CPI) ? (
          <div className="text-[11px] text-gray-500 mt-1">
            News breakdown: NFP {newsByType.NFP || 0} · FOMC {newsByType.FOMC || 0} · CPI {newsByType.CPI || 0}
          </div>
        ) : null}
      </div>

      <div className="border-t border-border pt-2">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Breakouts</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <Stat label="Days with breakout" value={`${breakouts} (${pct(breakouts, validDays)})`} />
          <Stat label="Bull breaks" value={d.bull_breakouts || 0} tone="good" />
          <Stat label="Bear breaks" value={d.bear_breakouts || 0} tone="bad" />
          <Stat
            label="Avg breakout → entry"
            value={d.avg_breakout_to_entry_minutes != null
              ? `${d.avg_breakout_to_entry_minutes.toFixed(1)} min`
              : '—'}
          />
        </div>
      </div>

      <div className="border-t border-border pt-2">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Entries</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <Stat label="Via DR retest" value={entries} tone="good" />
          <Stat label="Via midpoint retest" value={midEntries} />
          <Stat label="No retest within window" value={d.days_no_retest || 0} />
          <Stat label="Past last-entry cutoff" value={d.days_past_last_entry || 0} />
        </div>
      </div>

      {results.trades?.length === 0 && (
        <div className="border-t border-border pt-2 text-[11px] text-warn leading-relaxed">
          Zero trades. Common fixes: widen DR range band, relax retest tolerance,
          extend retest window, disable confirmation candle, or allow more days.
        </div>
      )}
    </div>
  )
}
