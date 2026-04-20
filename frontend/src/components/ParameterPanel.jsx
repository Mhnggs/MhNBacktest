import { useEffect, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'
import { runBacktest, getPatterns } from '../api/client'

const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Los_Angeles',
  'Europe/London', 'Europe/Berlin', 'Asia/Karachi', 'Asia/Dubai',
  'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney', 'UTC',
]

const FALLBACK_PATTERNS = [
  { key: 'marubozu', label: 'Marubozu' },
  { key: 'engulfing', label: 'Engulfing' },
  { key: 'hammer_star', label: 'Hammer / Shooting Star' },
  { key: 'inside_bar', label: 'Inside Bar' },
  { key: 'piercing_cloud', label: 'Piercing Line / Dark Cloud Cover' },
  { key: 'doji', label: 'Doji' },
]

const ENTRY_TYPE_OPTIONS = [
  { key: 'retest_only', label: 'Retest only' },
  { key: 'midpoint_only', label: 'Midpoint retest only' },
  { key: 'retest_then_midpoint', label: 'Retest, fallback to midpoint' },
]

function Field({ label, children }) {
  return (
    <div>
      <div className="label">{label}</div>
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

function Slider({ value, onChange, min, max, step }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        className="flex-1 accent-accent"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="text-xs text-gray-300 w-10 text-right">{value}</span>
    </div>
  )
}

function Toggle({ value, onChange, label }) {
  return (
    <label className="flex items-center justify-between cursor-pointer text-sm">
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

function PatternToggles({ options, value, onChange }) {
  const active = new Set(value || [])
  const toggle = (key) => {
    const next = new Set(active)
    if (next.has(key)) next.delete(key); else next.add(key)
    onChange(Array.from(next))
  }
  return (
    <div className="grid grid-cols-1 gap-1">
      {options.map((opt) => {
        const on = active.has(opt.key)
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => toggle(opt.key)}
            className={`btn ${on ? 'btn-primary' : 'btn-ghost'} justify-start text-left text-xs py-1.5`}
          >
            <span className="w-4 inline-block">{on ? '✓' : ''}</span>
            <span>{opt.label}</span>
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

function CustomSkipDatesInput({ value, onChange }) {
  const [draft, setDraft] = useState((value || []).join(', '))
  useEffect(() => { setDraft((value || []).join(', ')) }, [value])
  return (
    <input
      className="input"
      type="text"
      placeholder="2024-03-20, 2024-05-01"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const tokens = draft
          .split(/[,\s]+/)
          .map((t) => t.trim())
          .filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t))
        onChange(tokens)
      }}
    />
  )
}

export default function ParameterPanel() {
  const {
    params, setParam, sessionId, startDate, endDate, setDateRange,
    isRunning, setRunning, setResults, setError, resetParams,
  } = useBacktestStore()

  const [patternOptions, setPatternOptions] = useState(FALLBACK_PATTERNS)

  useEffect(() => {
    let mounted = true
    getPatterns()
      .then((data) => {
        if (mounted && Array.isArray(data?.patterns) && data.patterns.length) {
          setPatternOptions(data.patterns)
        }
      })
      .catch(() => { /* keep fallback */ })
    return () => { mounted = false }
  }, [])

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
      return
    }
    if (params.require_confirmation_candle &&
        (!params.confirmation_patterns || params.confirmation_patterns.length === 0)) {
      setError('Select at least one confirmation candle pattern, or disable the confirmation requirement.')
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
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-200">DR / IDR Strategy</h2>
        <button
          type="button"
          className="btn btn-ghost text-[11px] px-2 py-1"
          onClick={resetParams}
          title="Reset to defaults"
        >
          Reset
        </button>
      </div>

      <Section title="Defining Range (DR)">
        <div className="grid grid-cols-2 gap-2">
          <Field label="DR Start">
            <input
              className="input"
              type="time"
              value={params.dr_start_time}
              onChange={(e) => setParam('dr_start_time', e.target.value)}
            />
          </Field>
          <Field label="DR End">
            <input
              className="input"
              type="time"
              value={params.dr_end_time}
              onChange={(e) => setParam('dr_end_time', e.target.value)}
            />
          </Field>
        </div>
        <Field label="DR Timezone">
          <select
            className="input"
            value={params.dr_timezone}
            onChange={(e) => setParam('dr_timezone', e.target.value)}
          >
            {TIMEZONES.map((tz) => (<option key={tz} value={tz}>{tz}</option>))}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Min DR Range (pips)">
            <NumberInput
              value={params.min_dr_range_pips}
              onChange={(v) => setParam('min_dr_range_pips', v)}
              min={0} max={500} step={1}
            />
          </Field>
          <Field label="Max DR Range (pips)">
            <NumberInput
              value={params.max_dr_range_pips}
              onChange={(v) => setParam('max_dr_range_pips', v)}
              min={1} max={1000} step={1}
            />
          </Field>
        </div>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          Days whose DR range falls outside the min/max band are skipped as
          either too flat or too volatile.
        </div>
      </Section>

      <Section title="Entry">
        <Field label="Entry Mode">
          <select
            className="input"
            value={params.entry_type}
            onChange={(e) => setParam('entry_type', e.target.value)}
          >
            {ENTRY_TYPE_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Retest Tolerance (pips)">
          <NumberInput
            value={params.retest_tolerance_pips}
            onChange={(v) => setParam('retest_tolerance_pips', v)}
            min={0} max={100} step={0.5}
          />
        </Field>
        <Toggle
          label="Require confirmation candle"
          value={params.require_confirmation_candle}
          onChange={(v) => setParam('require_confirmation_candle', v)}
        />
        {params.require_confirmation_candle && (
          <>
            <div className="label">Confirmation Patterns</div>
            <PatternToggles
              options={patternOptions}
              value={params.confirmation_patterns}
              onChange={(v) => setParam('confirmation_patterns', v)}
            />
          </>
        )}
        <div className="text-[11px] text-gray-500 leading-relaxed">
          After the first clean break of the DR, the strategy waits for price
          to return within tolerance of the broken level (or the DR midpoint).
        </div>
      </Section>

      <Section title="Time Limits">
        <Field label={`Retest Window (min) — ${params.retest_window_minutes}`}>
          <Slider
            value={params.retest_window_minutes}
            onChange={(v) => setParam('retest_window_minutes', v)}
            min={15} max={300} step={5}
          />
        </Field>
        <Field label="Last Entry Time">
          <input
            className="input"
            type="time"
            value={params.last_entry_time}
            onChange={(e) => setParam('last_entry_time', e.target.value)}
          />
        </Field>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          Entries blocked after the last entry time. Open trades are force-closed
          on the bar closing at or past this time.
        </div>
      </Section>

      <Section title="Stops & Targets">
        <Field label="Stop Buffer (pips beyond DR level)">
          <NumberInput
            value={params.stop_buffer_pips}
            onChange={(v) => setParam('stop_buffer_pips', v)}
            min={0} max={100} step={0.5}
          />
        </Field>
        <Toggle
          label="Use Partial TP"
          value={params.use_partial_tp}
          onChange={(v) => setParam('use_partial_tp', v)}
        />
        <Field label={`T1 × DR Range (${params.partial_tp_1_mult})`}>
          <Slider
            value={params.partial_tp_1_mult}
            onChange={(v) => setParam('partial_tp_1_mult', v)}
            min={0.1} max={3.0} step={0.05}
          />
        </Field>
        <Field label={`T2 × DR Range (${params.partial_tp_2_mult})`}>
          <Slider
            value={params.partial_tp_2_mult}
            onChange={(v) => setParam('partial_tp_2_mult', v)}
            min={0.25} max={5.0} step={0.05}
          />
        </Field>
        {params.use_partial_tp && (
          <Field label={`% closed at T1 (${params.partial_tp_pct}%)`}>
            <Slider
              value={params.partial_tp_pct}
              onChange={(v) => setParam('partial_tp_pct', v)}
              min={10} max={90} step={5}
            />
          </Field>
        )}
        <Toggle
          label="Move stop to BE after T1"
          value={params.move_be_after_t1}
          onChange={(v) => setParam('move_be_after_t1', v)}
        />
        <Field label="Max Trades / Day">
          <NumberInput
            value={params.max_trades_per_day}
            onChange={(v) => setParam('max_trades_per_day', v)}
            min={1} max={10}
          />
        </Field>
      </Section>

      <Section title="News Filter">
        <Toggle
          label="Skip NFP / FOMC / CPI days"
          value={params.enable_news_filter}
          onChange={(v) => setParam('enable_news_filter', v)}
        />
        <Field label="Custom Skip Dates (YYYY-MM-DD, comma-separated)">
          <CustomSkipDatesInput
            value={params.custom_skip_dates}
            onChange={(v) => setParam('custom_skip_dates', v)}
          />
        </Field>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          Built-in calendar covers first-Friday NFP, FOMC meeting dates and
          approximate CPI days (2016-2026).
        </div>
      </Section>

      <Section title="Day Filter">
        <DayToggles value={params.allowed_days} onChange={(v) => setParam('allowed_days', v)} />
        <div className="text-[11px] text-gray-500">Based on DR timezone.</div>
      </Section>

      <Section title="Account">
        <Field label="Starting Capital ($)">
          <NumberInput
            value={params.starting_capital}
            onChange={(v) => setParam('starting_capital', v)}
            min={100} step={100}
          />
        </Field>
        <Field label={`Risk / Trade % (${params.risk_per_trade_pct})`}>
          <Slider
            value={params.risk_per_trade_pct}
            onChange={(v) => setParam('risk_per_trade_pct', v)}
            min={0.1} max={5} step={0.1}
          />
        </Field>
        <Field label="Pip Size">
          <select
            className="input"
            value={params.pip_size}
            onChange={(e) => setParam('pip_size', Number(e.target.value))}
          >
            <option value={0.0001}>0.0001 (EURUSD, GBPUSD, …)</option>
            <option value={0.01}>0.01 (JPY pairs)</option>
            <option value={0.1}>0.1 (XAUUSD / Gold)</option>
            <option value={1}>1 (indices, BTC)</option>
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="From">
            <input className="input" type="date" value={startDate} onChange={(e) => setDateRange(e.target.value, endDate)} />
          </Field>
          <Field label="To">
            <input className="input" type="date" value={endDate} onChange={(e) => setDateRange(startDate, e.target.value)} />
          </Field>
        </div>
      </Section>

      <button
        className="btn btn-primary w-full text-base py-3"
        onClick={handleRun}
        disabled={isRunning}
      >
        {isRunning ? 'Running Backtest...' : 'Run Backtest'}
      </button>
    </div>
  )
}
