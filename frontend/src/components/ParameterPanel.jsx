import { useBacktestStore } from '../store/useBacktestStore'
import { runBacktest } from '../api/client'

const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Los_Angeles',
  'Europe/London', 'Europe/Berlin', 'Asia/Karachi', 'Asia/Dubai',
  'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney', 'UTC',
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

function Section({ title, children }) {
  return (
    <div className="space-y-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h3>
      {children}
    </div>
  )
}

export default function ParameterPanel() {
  const {
    params, setParam, sessionId, startDate, endDate, setDateRange,
    isRunning, setRunning, setResults, setError,
  } = useBacktestStore()

  async function handleRun() {
    if (!sessionId) {
      setError('Load a dataset first (upload CSV or fetch from TwelveData)')
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
      <h2 className="text-sm font-semibold text-gray-200">Strategy Parameters</h2>

      <Section title="Strategy">
        <Field label="EMA Fast Period">
          <NumberInput value={params.ema_period} onChange={(v) => setParam('ema_period', v)} min={3} max={50} />
        </Field>
        <Field label="EMA Slow Period">
          <NumberInput value={params.ema_secondary} onChange={(v) => setParam('ema_secondary', v)} min={5} max={200} />
        </Field>
        <Field label={`Volume Multiplier (${params.volume_multiplier})`}>
          <Slider value={params.volume_multiplier} onChange={(v) => setParam('volume_multiplier', v)} min={1.0} max={3.0} step={0.1} />
        </Field>
        <Field label={`Risk / Reward (${params.risk_reward})`}>
          <Slider value={params.risk_reward} onChange={(v) => setParam('risk_reward', v)} min={1.0} max={5.0} step={0.5} />
        </Field>
        <Field label="Stop Buffer (ticks)">
          <NumberInput value={params.stop_buffer_ticks} onChange={(v) => setParam('stop_buffer_ticks', v)} min={0} />
        </Field>
        <Field label="Tick Size">
          <NumberInput value={params.tick_size} onChange={(v) => setParam('tick_size', v)} step={0.0001} />
        </Field>
        <Field label="Max Trades / Day">
          <NumberInput value={params.max_trades_per_day} onChange={(v) => setParam('max_trades_per_day', v)} min={1} />
        </Field>
      </Section>

      <Section title="Sessions">
        <div className="grid grid-cols-2 gap-2">
          <Field label="S1 Start">
            <input className="input" type="time" value={params.session_start} onChange={(e) => setParam('session_start', e.target.value)} />
          </Field>
          <Field label="S1 End">
            <input className="input" type="time" value={params.session_end} onChange={(e) => setParam('session_end', e.target.value)} />
          </Field>
        </div>
        <Toggle label="Use Session 2" value={params.use_session_2} onChange={(v) => setParam('use_session_2', v)} />
        {params.use_session_2 && (
          <div className="grid grid-cols-2 gap-2">
            <Field label="S2 Start">
              <input className="input" type="time" value={params.session_2_start} onChange={(e) => setParam('session_2_start', e.target.value)} />
            </Field>
            <Field label="S2 End">
              <input className="input" type="time" value={params.session_2_end} onChange={(e) => setParam('session_2_end', e.target.value)} />
            </Field>
          </div>
        )}
        <Field label="Timezone">
          <select className="input" value={params.timezone} onChange={(e) => setParam('timezone', e.target.value)}>
            {TIMEZONES.map((tz) => (<option key={tz} value={tz}>{tz}</option>))}
          </select>
        </Field>
      </Section>

      <Section title="Trend Filter">
        <Toggle label="Enable ADX Filter" value={params.use_adx_filter} onChange={(v) => setParam('use_adx_filter', v)} />
        <Field label="ADX Period">
          <NumberInput value={params.adx_period} onChange={(v) => setParam('adx_period', v)} min={5} max={50} />
        </Field>
        <Field label={`ADX Threshold (${params.adx_threshold})`}>
          <Slider value={params.adx_threshold} onChange={(v) => setParam('adx_threshold', v)} min={15} max={50} step={1} />
        </Field>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          ADX {'>'} 25 = trending market. Below 25 is choppy — signals are skipped.
          Longs also require +DI {'>'} -DI; shorts require -DI {'>'} +DI.
        </div>
      </Section>

      <Section title="Day Filter">
        <DayToggles value={params.allowed_days} onChange={(v) => setParam('allowed_days', v)} />
        <div className="text-[11px] text-gray-500">Based on backtest timezone.</div>
      </Section>

      <Section title="Filters">
        <Field label={`VWAP Max Distance % (${params.vwap_max_distance_pct})`}>
          <Slider value={params.vwap_max_distance_pct} onChange={(v) => setParam('vwap_max_distance_pct', v)} min={0.1} max={10} step={0.1} />
        </Field>
        <Field label="Chop Filter (max VWAP crossings / 10 bars)">
          <NumberInput value={params.chop_filter_crossings} onChange={(v) => setParam('chop_filter_crossings', v)} min={0} max={10} />
        </Field>
        <Toggle label="Require Volume Confirmation" value={params.require_volume} onChange={(v) => setParam('require_volume', v)} />
        <Toggle label="Require Candle Pattern" value={params.require_pattern} onChange={(v) => setParam('require_pattern', v)} />
        <Toggle label="Use Partial TP at 1.5R" value={params.use_partial_tp} onChange={(v) => setParam('use_partial_tp', v)} />
      </Section>

      <Section title="Account">
        <Field label="Starting Capital ($)">
          <NumberInput value={params.starting_capital} onChange={(v) => setParam('starting_capital', v)} min={100} step={100} />
        </Field>
        <Field label={`Risk / Trade % (${params.risk_per_trade_pct})`}>
          <Slider value={params.risk_per_trade_pct} onChange={(v) => setParam('risk_per_trade_pct', v)} min={0.1} max={5} step={0.1} />
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
