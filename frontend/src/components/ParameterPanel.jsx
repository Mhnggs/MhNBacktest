import { useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'
import { runBacktest } from '../api/client'

function Field({ label, help, children }) {
  return (
    <div>
      <div className="label flex items-center gap-1">
        <span>{label}</span>
        {help && (
          <span
            className="text-[10px] text-gray-500 cursor-help border border-gray-600 rounded-full w-3.5 h-3.5 inline-flex items-center justify-center"
            title={help}
          >
            ?
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

function NumberInput({ value, onChange, step = 1, min, max }) {
  return (
    <input
      className="input"
      type="number"
      value={value}
      step={step}
      min={min}
      max={max}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  )
}

function Select({ value, onChange, options }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  )
}

function Toggle({ value, onChange, label, help }) {
  return (
    <label className="flex items-center justify-between cursor-pointer text-sm" title={help || ''}>
      <span className="text-gray-300">{label}</span>
      <input
        type="checkbox"
        className="accent-accent"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  )
}

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

function DayToggles({ value, onChange }) {
  const active = new Set(value || [])
  const toggle = (idx) => {
    const next = new Set(active)
    if (next.has(idx)) next.delete(idx); else next.add(idx)
    onChange(Array.from(next).sort((a, b) => a - b))
  }
  return (
    <div className="grid grid-cols-5 gap-1">
      {DAY_LABELS.map((label, i) => {
        const on = active.has(i)
        return (
          <button
            key={i}
            type="button"
            onClick={() => toggle(i)}
            className={`btn ${on ? 'btn-primary' : 'btn-ghost'} px-0 py-1 text-xs`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="space-y-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h3>
      {children}
    </div>
  )
}

function GuideModal({ open, onClose }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="card max-w-3xl max-h-[85vh] overflow-y-auto text-sm space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-100">ICT Silver Bullet — Strategy Guide</h2>
          <button className="btn btn-ghost text-xs px-2 py-1" onClick={onClose}>Close</button>
        </div>
        <p className="text-gray-300">
          The Silver Bullet is a one-hour kill-zone reversal strategy. Every
          rule is 100% mechanical, no discretion. Trades only during:
        </p>
        <ul className="list-disc pl-5 text-gray-300">
          <li>London SB: 03:00 – 04:00 New York time</li>
          <li>NY SB: 10:00 – 11:00 New York time (primary)</li>
          <li>NY PM SB: 14:00 – 15:00 New York time (optional)</li>
        </ul>
        <h3 className="text-sm font-semibold text-gray-200">The setup sequence</h3>
        <ol className="list-decimal pl-5 text-gray-300 space-y-1">
          <li><b>Liquidity sweep</b> — a wick pierces an equal high/low or a
            previous session high/low by at least <i>min_sweep_pips</i> AND the
            candle closes back on the other side. This hunts retail stop losses.</li>
          <li><b>Displacement</b> — within 10 bars of the sweep, a large body
            candle (≥ <i>displacement_body_pips</i>) closes in the extreme end
            of its range. Signals institutional conviction.</li>
          <li><b>Fair Value Gap</b> — a 3-candle imbalance where candle 3's
            opposite wick doesn't fill the gap left by candle 1's wick.
            Entry happens on a pullback into the FVG midpoint.</li>
          <li><b>Market Structure Shift</b> (optional) — a close breaks the
            most recent opposing swing, confirming the reversal.</li>
          <li><b>HTF bias</b> (optional) — trades only in the direction of
            the 1H trend.</li>
        </ol>
        <h3 className="text-sm font-semibold text-gray-200">Entry &amp; exits</h3>
        <ul className="list-disc pl-5 text-gray-300">
          <li>Entry: pullback to 50% of the FVG (limit order).</li>
          <li>Stop: beyond the sweep wick, beyond the FVG, or a fixed pip stop.</li>
          <li>Partial TP at 1R, move to breakeven, close remainder at <i>rr_ratio</i> × R.</li>
          <li>Close any open trade at kill-zone end if the toggle is on.</li>
        </ul>
        <h3 className="text-sm font-semibold text-gray-200">Confluence score</h3>
        <p className="text-gray-300">
          Each trade is scored 4–10 based on: kill zone, sweep, displacement,
          FVG, MSS, HTF alignment, order-block confluence, equal-levels sweep,
          large FVG, and previous-session sweep. Trades below
          <i> min_confluence_score</i> are skipped.
        </p>
      </div>
    </div>
  )
}

export default function ParameterPanel() {
  const {
    params, setParam, sessionId, startDate, endDate,
    isRunning, setRunning, setResults, setError, resetParams,
  } = useBacktestStore()
  const [guideOpen, setGuideOpen] = useState(false)

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
      return
    }
    if (!params.enable_london_sb && !params.enable_ny_sb && !params.enable_ny_pm_sb) {
      setError('Enable at least one kill zone.')
      return
    }
    if (!params.allowed_days || params.allowed_days.length === 0) {
      setError('Enable at least one day of the week.')
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await runBacktest({
        session_id: sessionId,
        params,
        start_date: startDate || null,
        end_date: endDate || null,
      })
      setResults(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="card space-y-4">
      <GuideModal open={guideOpen} onClose={() => setGuideOpen(false)} />

      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-gray-200">ICT Silver Bullet</h2>
        <div className="flex gap-1">
          <button
            type="button"
            className="btn btn-ghost text-[11px] px-2 py-1"
            onClick={() => setGuideOpen(true)}
            title="Open the strategy guide"
          >
            Guide
          </button>
          <button
            type="button"
            className="btn btn-ghost text-[11px] px-2 py-1"
            onClick={resetParams}
            title="Reset to defaults"
          >
            Reset
          </button>
        </div>
      </div>

      <Section title="Kill Zones (NY time)">
        <Toggle
          label="London SB (03:00 – 04:00 NY)"
          value={params.enable_london_sb}
          onChange={(v) => setParam('enable_london_sb', v)}
          help="Enable the London Silver Bullet window"
        />
        <Toggle
          label="NY SB (10:00 – 11:00 NY) — primary"
          value={params.enable_ny_sb}
          onChange={(v) => setParam('enable_ny_sb', v)}
          help="Enable the New York Silver Bullet window. This is the most-studied and typically best-performing kill zone."
        />
        <Toggle
          label="NY PM SB (14:00 – 15:00 NY)"
          value={params.enable_ny_pm_sb}
          onChange={(v) => setParam('enable_ny_pm_sb', v)}
          help="Enable the New York afternoon Silver Bullet"
        />
      </Section>

      <Section title="Liquidity detection">
        <div className="grid grid-cols-2 gap-2">
          <Field
            label="Swing Lookback"
            help="Bars on each side required to confirm a swing. Lower = more swings, more liquidity pools. Higher = only major swings."
          >
            <NumberInput value={params.swing_lookback}
              onChange={(v) => setParam('swing_lookback', v)} min={3} max={10} step={1} />
          </Field>
          <Field
            label="Equal-level Tol. (pips)"
            help="Two swing highs within this tolerance count as Equal Highs (EQH). Lower = fewer but sharper EQH/EQL clusters."
          >
            <NumberInput value={params.equal_level_tolerance_pips}
              onChange={(v) => setParam('equal_level_tolerance_pips', v)} min={0} max={25} step={0.5} />
          </Field>
          <Field
            label="Min Sweep (pips)"
            help="Minimum pip extension beyond the level required to count as a sweep. Lower = more sweeps but noisier. Higher = only decisive stop hunts."
          >
            <NumberInput value={params.min_sweep_pips}
              onChange={(v) => setParam('min_sweep_pips', v)} min={0.5} max={30} step={0.5} />
          </Field>
          <Field
            label="Sweep Confirm (bars)"
            help="Max bars allowed to close back the other side of a level."
          >
            <NumberInput value={params.sweep_confirmation_candles}
              onChange={(v) => setParam('sweep_confirmation_candles', v)} min={1} max={10} step={1} />
          </Field>
        </div>
      </Section>

      <Section title="Displacement">
        <div className="grid grid-cols-2 gap-2">
          <Field
            label="Body (pips)"
            help="Minimum candle body for a displacement bar. Lower = more displacements, more trades, lower quality. Higher = fewer but more decisive."
          >
            <NumberInput value={params.displacement_body_pips}
              onChange={(v) => setParam('displacement_body_pips', v)} min={2} max={60} step={0.5} />
          </Field>
          <Field
            label="Close %"
            help="Required close position inside the range (0.70 = top/bottom 30%). Higher = stricter."
          >
            <NumberInput value={params.displacement_close_pct}
              onChange={(v) => setParam('displacement_close_pct', v)} min={0.5} max={1.0} step={0.05} />
          </Field>
        </div>
      </Section>

      <Section title="Fair Value Gap">
        <div className="grid grid-cols-2 gap-2">
          <Field
            label="Min Size (pips)"
            help="Smaller FVGs give poor R:R. Raising this filters out micro-gaps."
          >
            <NumberInput value={params.min_fvg_size_pips}
              onChange={(v) => setParam('min_fvg_size_pips', v)} min={0.5} max={30} step={0.5} />
          </Field>
          <Field
            label="Max Age (bars)"
            help="FVG expires after this many bars. 20 bars ≈ 100 minutes on 5-minute charts."
          >
            <NumberInput value={params.fvg_max_age_candles}
              onChange={(v) => setParam('fvg_max_age_candles', v)} min={3} max={100} step={1} />
          </Field>
        </div>
        <Field
          label="FVG Entry Type"
          help="50% midpoint: limit-enter at the gap center. FVG touch: market-enter when price first touches the FVG. FVG close: enter when a candle closes inside."
        >
          <Select
            value={params.fvg_entry_type}
            onChange={(v) => setParam('fvg_entry_type', v)}
            options={['50% midpoint', 'FVG touch', 'FVG close']}
          />
        </Field>
      </Section>

      <Section title="Structure & Bias">
        <Toggle
          label="Require MSS confirmation"
          value={params.require_mss}
          onChange={(v) => setParam('require_mss', v)}
          help="Require a break of intermediate high/low after the sweep. Usually improves win rate."
        />
        <Toggle
          label="Require Order-Block confluence"
          value={params.require_ob_confluence}
          onChange={(v) => setParam('require_ob_confluence', v)}
          help="Only take trades where the FVG overlaps the last opposing candle before displacement. Rarer but higher quality."
        />
        <Toggle
          label="Require HTF alignment (1H bias)"
          value={params.require_htf_alignment}
          onChange={(v) => setParam('require_htf_alignment', v)}
          help="Skip trades that fight the 1H direction."
        />
        <Field
          label="HTF neutral action"
          help="What to do when the 1H is neither bullish nor bearish."
        >
          <Select
            value={params.htf_neutral_action}
            onChange={(v) => setParam('htf_neutral_action', v)}
            options={['Skip trade', 'Allow both']}
          />
        </Field>
      </Section>

      <Section title="Risk & Exits">
        <Field
          label="Stop Type"
          help="Beyond sweep: safest, uses the stop-hunt wick. Beyond FVG: tighter. Fixed pips: simplest."
        >
          <Select
            value={params.stop_type}
            onChange={(v) => setParam('stop_type', v)}
            options={['Beyond sweep', 'Beyond FVG', 'Fixed pips']}
          />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Stop Buffer (pips)"
            help="Extra cushion past the sweep / FVG edge.">
            <NumberInput value={params.stop_buffer_pips}
              onChange={(v) => setParam('stop_buffer_pips', v)} min={0} max={30} step={0.5} />
          </Field>
          <Field label="Fixed Stop (pips)"
            help="Used only when Stop Type = Fixed pips.">
            <NumberInput value={params.fixed_stop_pips}
              onChange={(v) => setParam('fixed_stop_pips', v)} min={2} max={100} step={0.5} />
          </Field>
          <Field label="R:R Ratio"
            help="Final target as a multiple of risk. Higher = fewer winners but bigger ones.">
            <NumberInput value={params.rr_ratio}
              onChange={(v) => setParam('rr_ratio', v)} min={0.5} max={10} step={0.25} />
          </Field>
          <Field label="Min FVG / Stop"
            help="Require FVG to be at least this fraction of the stop distance. Skips unfavourable R:R.">
            <NumberInput value={params.min_fvg_to_stop_ratio}
              onChange={(v) => setParam('min_fvg_to_stop_ratio', v)} min={0.1} max={2.0} step={0.1} />
          </Field>
        </div>
        <Toggle
          label="Partial TP at 1R + breakeven"
          value={params.use_partial_tp}
          onChange={(v) => setParam('use_partial_tp', v)}
          help="Close 50% at 1R and move stop to breakeven, then run the rest to target."
        />
        <Toggle
          label="Close at kill-zone end"
          value={params.close_at_killzone_end}
          onChange={(v) => setParam('close_at_killzone_end', v)}
          help="Flatten any open trade when the one-hour window ends."
        />
        <div className="grid grid-cols-2 gap-2">
          <Field label="Max/KZ" help="Max trades per kill zone.">
            <NumberInput value={params.max_trades_per_killzone}
              onChange={(v) => setParam('max_trades_per_killzone', v)} min={1} max={5} step={1} />
          </Field>
          <Field label="Max/day" help="Max trades across all kill zones in one day.">
            <NumberInput value={params.max_trades_per_day}
              onChange={(v) => setParam('max_trades_per_day', v)} min={1} max={10} step={1} />
          </Field>
        </div>
      </Section>

      <Section title="Confluence Filter">
        <Field
          label="Min Confluence Score (4–10)"
          help="Base 4 (kill zone, sweep, displacement, FVG) + bonuses for MSS, HTF, OB, EQ levels, large FVG, prev-session sweep. Higher = fewer but higher-quality trades."
        >
          <NumberInput value={params.min_confluence_score}
            onChange={(v) => setParam('min_confluence_score', v)} min={4} max={10} step={1} />
        </Field>
      </Section>

      <Section title="Sizing & spread">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Capital" help="Starting equity.">
            <NumberInput value={params.starting_capital}
              onChange={(v) => setParam('starting_capital', v)} min={100} step={100} />
          </Field>
          <Field label="Risk/Trade %" help="Account risk per entry.">
            <NumberInput value={params.risk_per_trade_pct}
              onChange={(v) => setParam('risk_per_trade_pct', v)} min={0.1} max={10} step={0.1} />
          </Field>
          <Field label="Spread (pips)" help="Deducted from every trade P&L.">
            <NumberInput value={params.spread_pips}
              onChange={(v) => setParam('spread_pips', v)} min={0} max={5} step={0.1} />
          </Field>
          <Field label="Pip Size" help="0.0001 for EUR/USD-class pairs, 0.01 for JPY pairs.">
            <NumberInput value={params.pip_size}
              onChange={(v) => setParam('pip_size', v)} step={0.0001} />
          </Field>
        </div>
      </Section>

      <Section title="Circuit Breakers">
        <Toggle
          label="Daily loss stop"
          value={params.enable_daily_circuit_breaker}
          onChange={(v) => setParam('enable_daily_circuit_breaker', v)}
        />
        <div className="grid grid-cols-2 gap-2">
          <Field label="Daily limit %">
            <NumberInput value={params.daily_loss_limit_pct}
              onChange={(v) => setParam('daily_loss_limit_pct', v)} min={0} max={50} step={0.25} />
          </Field>
          <Field label="Weekly limit %">
            <NumberInput value={params.weekly_loss_limit_pct}
              onChange={(v) => setParam('weekly_loss_limit_pct', v)} min={0} max={100} step={0.25} />
          </Field>
        </div>
        <Toggle
          label="Weekly loss stop"
          value={params.enable_weekly_circuit_breaker}
          onChange={(v) => setParam('enable_weekly_circuit_breaker', v)}
        />
      </Section>

      <Section title="News & day filter">
        <Toggle
          label="Skip FOMC / NFP / CPI days"
          value={params.enable_news_filter}
          onChange={(v) => setParam('enable_news_filter', v)}
        />
        <Field label="Allowed days">
          <DayToggles
            value={params.allowed_days}
            onChange={(v) => setParam('allowed_days', v)}
          />
        </Field>
      </Section>

      <button
        type="button"
        className="btn btn-primary w-full py-2"
        onClick={handleRun}
        disabled={isRunning}
      >
        {isRunning ? 'Running…' : 'Run Backtest'}
      </button>
    </div>
  )
}
