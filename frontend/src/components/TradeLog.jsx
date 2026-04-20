import { useMemo, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'

const PAGE_SIZE = 25

const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const KZ_LABELS = {
  london_sb: 'London SB',
  ny_sb: 'NY AM SB',
  ny_pm_sb: 'NY PM SB',
}

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function fmtPct(v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

function tradeRiskDollars(t) {
  const dist = Math.abs((t.entry_price ?? 0) - (t.stop ?? 0))
  const size = t.size || 0
  if (!dist || !size) return null
  return dist * size
}

function tradeR(t) {
  const risk = tradeRiskDollars(t)
  if (!risk || t.pnl == null) return null
  return t.pnl / risk
}

function exportCsv(trades) {
  if (!trades || !trades.length) return
  const cols = [
    'id', 'direction', 'kill_zone', 'confluence_score', 'htf_bias',
    'sweep_level_type', 'fvg_size_pips', 'mss_confirmed',
    'entry_time', 'entry_price', 'stop', 'target1', 'target2',
    'exit_time', 'exit_price', 'pnl', 'result', 'exit_reason',
  ]
  const lines = [cols.join(',')]
  for (const t of trades) {
    lines.push(cols.map((c) => JSON.stringify(t[c] ?? '')).join(','))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'trades.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function dayIndex(isoString) {
  if (!isoString) return null
  const d = new Date(isoString).getDay()
  return (d + 6) % 7
}

export default function TradeLog() {
  const results = useBacktestStore((s) => s.results)
  const selectTrade = useBacktestStore((s) => s.selectTrade)
  const selectedId = useBacktestStore((s) => s.selectedTradeId)
  const [direction, setDirection] = useState('all')
  const [result, setResult] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [dow, setDow] = useState('all')
  const [killZone, setKillZone] = useState('all')
  const [htfBias, setHtfBias] = useState('all')
  const [sortKey, setSortKey] = useState('entry_time')
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(1)

  const trades = results?.trades || []

  const filtered = useMemo(() => {
    let rows = trades
    if (direction !== 'all') rows = rows.filter((t) => t.direction === direction)
    if (result !== 'all') rows = rows.filter((t) => t.result === result)
    if (dateFrom) rows = rows.filter((t) => (t.entry_time || '').slice(0, 10) >= dateFrom)
    if (dateTo) rows = rows.filter((t) => (t.entry_time || '').slice(0, 10) <= dateTo)
    if (dow !== 'all') {
      const target = Number(dow)
      rows = rows.filter((t) => dayIndex(t.entry_time) === target)
    }
    if (killZone !== 'all') {
      rows = rows.filter((t) => (t.kill_zone || '') === killZone)
    }
    if (htfBias !== 'all') {
      rows = rows.filter((t) => (t.htf_bias || '') === htfBias)
    }
    rows = [...rows].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av === bv) return 0
      const cmp = av > bv ? 1 : -1
      return sortDir === 'asc' ? cmp : -cmp
    })
    return rows
  }, [trades, direction, result, dateFrom, dateTo, dow, killZone, htfBias, sortKey, sortDir])

  const killZoneChoices = useMemo(() => {
    const s = new Set()
    for (const t of trades) if (t.kill_zone) s.add(t.kill_zone)
    return Array.from(s).sort()
  }, [trades])

  const htfChoices = useMemo(() => {
    const s = new Set()
    for (const t of trades) if (t.htf_bias) s.add(t.htf_bias)
    return Array.from(s).sort()
  }, [trades])

  const summary = useMemo(() => {
    const n = filtered.length
    if (!n) return null
    let wins = 0, losses = 0, pnl = 0, grossW = 0, grossL = 0, rSum = 0, rCount = 0
    for (const t of filtered) {
      pnl += t.pnl || 0
      if (t.result === 'win') { wins += 1; grossW += t.pnl }
      else if (t.result === 'loss') { losses += 1; grossL += -t.pnl }
      const r = tradeR(t)
      if (r != null) { rSum += r; rCount += 1 }
    }
    return {
      count: n,
      wins, losses,
      win_rate: (wins / n) * 100,
      pnl,
      avg: pnl / n,
      profit_factor: grossL > 0 ? grossW / grossL : (grossW > 0 ? Infinity : 0),
      avg_r: rCount ? rSum / rCount : null,
    }
  }, [filtered])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const view = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  function toggleSort(k) {
    if (sortKey === k) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortKey(k); setSortDir('asc') }
  }

  function clearFilters() {
    setDirection('all'); setResult('all'); setDateFrom(''); setDateTo(''); setDow('all')
    setKillZone('all'); setHtfBias('all')
    setPage(1)
  }

  function viewOnChart(id) {
    selectTrade(id)
    document.querySelector('[data-chart-anchor]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (!results) return null

  const HEADERS = [
    ['id', '#'],
    ['entry_time', 'Entry Time'],
    ['direction', 'Dir'],
    ['kill_zone', 'Kill Zone'],
    ['confluence_score', '⭐'],
    ['htf_bias', 'HTF'],
    ['sweep_level_type', 'Sweep'],
    ['fvg_size_pips', 'FVG px'],
    ['entry_price', 'Entry'],
    ['stop', 'Stop'],
    ['target1', 'T1'],
    ['target2', 'T2'],
    ['exit_price', 'Exit'],
    ['pnl', 'P&L $'],
    ['result', 'Result'],
    ['exit_reason', 'Exit'],
  ]

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h2 className="text-sm font-semibold text-gray-200 mr-auto">
          Trade Log ({filtered.length}{filtered.length !== trades.length ? ` / ${trades.length}` : ''})
        </h2>
        <select className="input w-auto text-xs py-1" value={direction} onChange={(e) => { setDirection(e.target.value); setPage(1) }}>
          <option value="all">All Directions</option>
          <option value="long">Longs</option>
          <option value="short">Shorts</option>
        </select>
        <select className="input w-auto text-xs py-1" value={result} onChange={(e) => { setResult(e.target.value); setPage(1) }}>
          <option value="all">All Results</option>
          <option value="win">Wins</option>
          <option value="loss">Losses</option>
          <option value="breakeven">Breakeven</option>
        </select>
        <select className="input w-auto text-xs py-1" value={dow} onChange={(e) => { setDow(e.target.value); setPage(1) }}>
          <option value="all">All Days</option>
          {DOW_LABELS.map((d, i) => <option key={i} value={i}>{d}</option>)}
        </select>
        {killZoneChoices.length > 0 && (
          <select className="input w-auto text-xs py-1" value={killZone}
            onChange={(e) => { setKillZone(e.target.value); setPage(1) }}>
            <option value="all">All Kill Zones</option>
            {killZoneChoices.map((s) => (
              <option key={s} value={s}>{KZ_LABELS[s] || s}</option>
            ))}
          </select>
        )}
        {htfChoices.length > 0 && (
          <select className="input w-auto text-xs py-1" value={htfBias}
            onChange={(e) => { setHtfBias(e.target.value); setPage(1) }}>
            <option value="all">All HTF Bias</option>
            {htfChoices.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <input className="input w-auto text-xs py-1" type="date" value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} title="From" />
        <input className="input w-auto text-xs py-1" type="date" value={dateTo}
          onChange={(e) => { setDateTo(e.target.value); setPage(1) }} title="To" />
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={clearFilters}>Clear</button>
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => exportCsv(filtered)}>Export CSV</button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-gray-400 border-b border-border">
            <tr>
              {HEADERS.map(([k, label]) => (
                <th key={k} className="text-left py-2 px-2 cursor-pointer hover:text-accent" onClick={() => toggleSort(k)}>
                  {label}{sortKey === k ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
              <th className="py-2 px-2" />
            </tr>
          </thead>
          <tbody>
            {view.map((t) => {
              const cls =
                t.result === 'win' ? 'bg-good/10' :
                t.result === 'loss' ? 'bg-bad/10' :
                t.result === 'breakeven' ? 'bg-warn/10' : ''
              const sel = selectedId === t.id ? 'ring-1 ring-accent' : ''
              return (
                <tr
                  key={t.id}
                  className={`${cls} ${sel} hover:bg-bg cursor-pointer border-b border-border/40`}
                  onClick={() => selectTrade(t.id)}
                >
                  <td className="px-2 py-1.5 font-mono text-gray-400">{t.id}</td>
                  <td className="px-2 py-1.5 font-mono">{t.entry_time?.replace('T', ' ').slice(0, 16)}</td>
                  <td className="px-2 py-1.5 uppercase">
                    <span className={t.direction === 'long' ? 'text-good' : 'text-bad'}>{t.direction}</span>
                  </td>
                  <td className="px-2 py-1.5 text-gray-300 text-[11px]">{KZ_LABELS[t.kill_zone] || t.kill_zone || '—'}</td>
                  <td className="px-2 py-1.5 font-mono text-gray-200">{t.confluence_score ?? '—'}</td>
                  <td className="px-2 py-1.5 text-gray-300 text-[11px]">{t.htf_bias || '—'}</td>
                  <td className="px-2 py-1.5 text-gray-300 text-[11px]">{t.sweep_level_type || '—'}</td>
                  <td className="px-2 py-1.5 font-mono text-gray-300">
                    {t.fvg_size_pips != null ? t.fvg_size_pips.toFixed(1) : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-mono">{t.entry_price?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.stop?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.target1?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.target2?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.exit_price?.toFixed(5)}</td>
                  <td className={`px-2 py-1.5 font-mono ${t.pnl >= 0 ? 'text-good' : 'text-bad'}`}>{fmtMoney(t.pnl)}</td>
                  <td className="px-2 py-1.5 uppercase text-xs">{t.result}</td>
                  <td className="px-2 py-1.5 text-gray-400 text-[11px]">{t.exit_reason || '—'}</td>
                  <td className="px-2 py-1.5 text-right">
                    <button
                      className="btn btn-ghost px-2 py-0.5 text-[10px]"
                      onClick={(e) => { e.stopPropagation(); viewOnChart(t.id) }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              )
            })}
            {!view.length && (
              <tr><td colSpan={HEADERS.length + 1} className="px-2 py-6 text-center text-gray-500">No trades match the filters.</td></tr>
            )}
          </tbody>
          {summary && (
            <tfoot className="border-t-2 border-border bg-bg/40 font-mono text-xs">
              <tr>
                <td className="px-2 py-2 text-gray-400" colSpan={3}>
                  {summary.count} trade{summary.count === 1 ? '' : 's'} · {summary.wins}W / {summary.losses}L
                </td>
                <td className="px-2 py-2 text-gray-400" colSpan={4}>
                  Win rate <span className="text-gray-100">{fmtPct(summary.win_rate, 1)}</span>
                </td>
                <td className="px-2 py-2 text-gray-400" colSpan={4}>
                  PF <span className="text-gray-100">
                    {summary.profit_factor === Infinity ? '∞' : summary.profit_factor.toFixed(2)}
                  </span>
                </td>
                <td className="px-2 py-2" colSpan={2}>
                  <span className={summary.pnl >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(summary.pnl)}</span>
                </td>
                <td className="px-2 py-2 text-gray-400" colSpan={4}>
                  Avg <span className={summary.avg >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(summary.avg)}</span>
                  {summary.avg_r != null && <> · Avg R <span className="text-gray-100">{summary.avg_r.toFixed(2)}</span></>}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
        <span>Page {safePage} / {pageCount} · {PAGE_SIZE}/page</span>
        <div className="flex gap-2">
          <button className="btn btn-ghost px-2 py-1" disabled={safePage <= 1} onClick={() => setPage(1)}>« First</button>
          <button className="btn btn-ghost px-2 py-1" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>Prev</button>
          <button className="btn btn-ghost px-2 py-1" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}>Next</button>
          <button className="btn btn-ghost px-2 py-1" disabled={safePage >= pageCount} onClick={() => setPage(pageCount)}>Last »</button>
        </div>
      </div>
    </div>
  )
}
