import { useMemo, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'

const PAGE_SIZE = 25

const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function fmtPct(v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

function exportCsv(trades) {
  if (!trades || !trades.length) return
  const cols = [
    'id', 'direction', 'pattern', 'entry_time', 'entry_price', 'stop',
    'target', 'exit_time', 'exit_price', 'pnl', 'pnl_pct', 'result',
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
  // JS getDay: 0=Sun..6=Sat  →  remap to 0=Mon..6=Sun
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
    rows = [...rows].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av === bv) return 0
      const cmp = av > bv ? 1 : -1
      return sortDir === 'asc' ? cmp : -cmp
    })
    return rows
  }, [trades, direction, result, dateFrom, dateTo, dow, sortKey, sortDir])

  const summary = useMemo(() => {
    const n = filtered.length
    if (!n) return null
    let wins = 0, losses = 0, pnl = 0, grossW = 0, grossL = 0, rSum = 0, rCount = 0
    for (const t of filtered) {
      pnl += t.pnl || 0
      if (t.result === 'win') { wins += 1; grossW += t.pnl }
      else if (t.result === 'loss') { losses += 1; grossL += -t.pnl }
      const risk = t.risk_per_unit && t.units ? t.risk_per_unit * (t.units || 1) : null
      if (risk && risk > 0 && t.pnl != null) { rSum += t.pnl / risk; rCount += 1 }
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
    setPage(1)
  }

  function viewOnChart(id) {
    selectTrade(id)
    document.querySelector('[data-chart-anchor]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (!results) return null

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
          <option value="timeout">Timeout</option>
        </select>
        <select className="input w-auto text-xs py-1" value={dow} onChange={(e) => { setDow(e.target.value); setPage(1) }}>
          <option value="all">All Days</option>
          {DOW_LABELS.map((d, i) => <option key={i} value={i}>{d}</option>)}
        </select>
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
              {[
                ['id', '#'], ['entry_time', 'Entry Time'], ['direction', 'Dir'],
                ['pattern', 'Pattern'],
                ['entry_price', 'Entry'], ['stop', 'Stop'], ['target', 'Target'],
                ['exit_price', 'Exit'], ['pnl', 'P&L $'], ['pnl_pct', 'P&L %'], ['result', 'Result'],
              ].map(([k, label]) => (
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
                  <td className="px-2 py-1.5 text-gray-300 text-[11px]">{t.pattern || '—'}</td>
                  <td className="px-2 py-1.5 font-mono">{t.entry_price?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.stop?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.target?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.exit_price?.toFixed(5)}</td>
                  <td className={`px-2 py-1.5 font-mono ${t.pnl >= 0 ? 'text-good' : 'text-bad'}`}>{fmtMoney(t.pnl)}</td>
                  <td className={`px-2 py-1.5 font-mono ${t.pnl_pct >= 0 ? 'text-good' : 'text-bad'}`}>{t.pnl_pct?.toFixed(2)}%</td>
                  <td className="px-2 py-1.5 uppercase text-xs">{t.result}</td>
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
              <tr><td colSpan={12} className="px-2 py-6 text-center text-gray-500">No trades match the filters.</td></tr>
            )}
          </tbody>
          {summary && (
            <tfoot className="border-t-2 border-border bg-bg/40 font-mono text-xs">
              <tr>
                <td className="px-2 py-2 text-gray-400" colSpan={2}>
                  Summary ({summary.count} trade{summary.count === 1 ? '' : 's'})
                </td>
                <td className="px-2 py-2 text-gray-400">
                  {summary.wins}W / {summary.losses}L
                </td>
                <td className="px-2 py-2 text-gray-400" colSpan={4}>
                  Win rate <span className="text-gray-100">{fmtPct(summary.win_rate, 1)}</span>
                </td>
                <td className="px-2 py-2 text-gray-400">
                  PF <span className="text-gray-100">
                    {summary.profit_factor === Infinity ? '∞' : summary.profit_factor.toFixed(2)}
                  </span>
                </td>
                <td className={`px-2 py-2 ${summary.pnl >= 0 ? 'text-good' : 'text-bad'}`}>
                  {fmtMoney(summary.pnl)}
                </td>
                <td className="px-2 py-2 text-gray-400">
                  Avg <span className={summary.avg >= 0 ? 'text-good' : 'text-bad'}>{fmtMoney(summary.avg)}</span>
                </td>
                <td className="px-2 py-2 text-gray-400" colSpan={2}>
                  {summary.avg_r != null ? <>Avg R <span className="text-gray-100">{summary.avg_r.toFixed(2)}</span></> : null}
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
