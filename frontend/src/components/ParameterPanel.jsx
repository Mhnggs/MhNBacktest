import { useEffect, useState } from 'react'
import { useBacktestStore, defaultParams } from '../store/useBacktestStore'
import { runBacktest, getPatterns } from '../api/client'

const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Los_Angeles',
  'Europe/London', 'Europe/Berlin', 'Asia/Karachi', 'Asia/Dubai',
  'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney', 'UTC',
]

const FALLBACK_PATTERNS = [
  { key: 'engulfing', label: 'Engulfing' },
  { key: 'hammer_star', label: 'Hammer / Shooting Star' },
  { key: 'piercing_cloud', label: 'Piercing Line / Dark Cloud Cover' },
  { key: 'marubozu', label: 'Marubozu' },
  { key: 'doji', label: 'Doji' },
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
    if (!params.allowed_patterns || params.allowed_patterns.length === 0) {
      setError('Select at least one candlestick pattern to use as entry trigger.')
      return
    }
    if (!params.use_ny && !params.use_london && !params.use_asian) {
      setError('Enable at least one session (NY, London, or Asian).')
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
        <h2 className="text-sm font-semibold text-gray-200">Strategy Parameters</h2>
        <button
          type="button"
          className="btn btn-ghost text-[11px] px-2 py-1"
          onClick={resetParams}
          title="Reset to defaults"
        >
          Reset
        </button>
      </div>

      <Section title="EMA Crossover">
        <Field label="EMA Fast Period">
          <NumberInput value={params.ema_period} onChange={(v) => setParam('ema_period', v)} min={2} max={200} />
        </Field>
        <Field label="EMA Slow Period">
          <NumberInput value={params.ema_secondary} onChange={(v) => setParam('ema_secondary', v)} min={2} max={400} />
        </Field>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          Bullish cross (fast crosses above slow) → look for a long setup. Bearish cross → short setup.
        </div>
      </Section>

      <Section title="Entry Patterns">
        <PatternToggles
          options={patternOptions}
          value={params.allowed_patterns}
          onChange={(v) => setParam('allowed_patterns', v)}
        />
        <div className="text-[11px] text-gray-500 leading-relaxed">
          A trade only fires when one of the selected patterns prints on the crossover bar.
        </div>
      </Section>

      <Section title="Risk">
        <Field label="Stop Loss (pips)">
          <NumberInput value={params.stop_loss_pips} onChange={(v) => setParam('stop_loss_pips', v)} step={1} min={1} max={1000} />
        </Field>
        <Field label={`Risk / Reward (${params.risk_reward})`}>
          <Slider value={params.risk_reward} onChange={(v) => setParam('risk_reward', v)} min={0.5} max={5.0} step={0.25} />
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
        <Field label="Max Trades / Day">
          <NumberInput value={params.max_trades_per_day} onChange={(v) => setParam('max_trades_per_day', v)} min={1} max={50} />
        </Field>
      </Section>

      <Section title="Partial Take-Profit">
        <Toggle label="Enable Partial TP" value={params.use_partial_tp} onChange={(v) => setParam('use_partial_tp', v)} />
        {params.use_partial_tp && (
          <>
            <Field label={`Take partial at (${params.partial_tp_r}R)`}>
              <Slider value={params.partial_tp_r} onChange={(v) => setParam('partial_tp_r', v)} min={0.5} max={3.0} step={0.1} />
            </Field>
            <Field label={`% of position closed (${params.partial_tp_pct}%)`}>
              <Slider value={params.partial_tp_pct} onChange={(v) => setParam('partial_tp_pct', v)} min={10} max={90} step={5} />
            </Field>
            <div className="text-[11px] text-gray-500 leading-relaxed">
              Closes that % of the position once price reaches the R-multiple,
              then moves stop to break-even for the runner.
            </div>
          </>
        )}
      </Section>

      <Section title="Break-Even Stop">
        <Toggle label="Enable Breakeven" value={params.use_breakeven} onChange={(v) => setParam('use_breakeven', v)} />
        {params.use_breakeven && (
          <>
            <Field label={`Move SL to BE at (${params.breakeven_r}R)`}>
              <Slider value={params.breakeven_r} onChange={(v) => setParam('breakeven_r', v)} min={0.5} max={3.0} step={0.1} />
            </Field>
            <div className="text-[11px] text-gray-500 leading-relaxed">
              When price runs in your favour by this R-multiple, the stop
              jumps to your entry price. Nothing is closed.
            </div>
          </>
        )}
      </Section>

      <Section title="NY Session">
        <Toggle label="Enable NY" value={params.use_ny} onChange={(v) => setParam('use_ny', v)} />
        {params.use_ny && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Morning Start">
                <input className="input" type="time" value={params.session_start} onChange={(e) => setParam('session_start', e.target.value)} />
              </Field>
              <Field label="Morning End">
                <input className="input" type="time" value={params.session_end} onChange={(e) => setParam('session_end', e.target.value)} />
              </Field>
            </div>
            <Toggle label="Use Afternoon Window" value={params.use_session_2} onChange={(v) => setParam('use_session_2', v)} />
            {params.use_session_2 && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Afternoon Start">
                  <input className="input" type="time" value={params.session_2_start} onChange={(e) => setParam('session_2_start', e.target.value)} />
                </Field>
                <Field label="Afternoon End">
                  <input className="input" type="time" value={params.session_2_end} onChange={(e) => setParam('session_2_end', e.target.value)} />
                </Field>
              </div>
            )}
            <Field label="NY Timezone">
              <select className="input" value={params.timezone} onChange={(e) => setParam('timezone', e.target.value)}>
                {TIMEZONES.map((tz) => (<option key={tz} value={tz}>{tz}</option>))}
              </select>
            </Field>
          </>
        )}
      </Section>

      <Section title="London Session">
        <Toggle label="Enable London" value={params.use_london} onChange={(v) => setParam('use_london', v)} />
        {params.use_london && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Start">
                <input className="input" type="time" value={params.london_start} onChange={(e) => setParam('london_start', e.target.value)} />
              </Field>
              <Field label="End">
                <input className="input" type="time" value={params.london_end} onChange={(e) => setParam('london_end', e.target.value)} />
              </Field>
            </div>
            <Field label="London Timezone">
              <select className="input" value={params.london_tz} onChange={(e) => setParam('london_tz', e.target.value)}>
                {TIMEZONES.map((tz) => (<option key={tz} value={tz}>{tz}</option>))}
              </select>
            </Field>
          </>
        )}
      </Section>

      <Section title="Asian Session">
        <Toggle label="Enable Asian" value={params.use_asian} onChange={(v) => setParam('use_asian', v)} />
        {params.use_asian && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Start">
                <input className="input" type="time" value={params.asian_start} onChange={(e) => setParam('asian_start', e.target.value)} />
              </Field>
              <Field label="End">
                <input className="input" type="time" value={params.asian_end} onChange={(e) => setParam('asian_end', e.target.value)} />
              </Field>
            </div>
            <Field label="Asian Timezone">
              <select className="input" value={params.asian_tz} onChange={(e) => setParam('asian_tz', e.target.value)}>
                {TIMEZONES.map((tz) => (<option key={tz} value={tz}>{tz}</option>))}
              </select>
            </Field>
          </>
        )}
      </Section>

      <Section title="Day Filter">
        <DayToggles value={params.allowed_days} onChange={(v) => setParam('allowed_days', v)} />
        <div className="text-[11px] text-gray-500">Based on backtest timezone.</div>
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
