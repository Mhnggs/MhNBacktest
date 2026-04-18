import { useMemo, useState } from 'react'
import { useBacktestStore } from '../store/useBacktestStore'

const PAGE_SIZE = 20

function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function exportCsv(trades) {
  if (!trades || !trades.length) return
  const cols = [
    'id', 'direction', 'entry_time', 'entry_price', 'stop',
    'target_1', 'target_2', 'exit_time', 'exit_price', 'pnl', 'pnl_pct', 'result',
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

export default function TradeLog() {
  const results = useBacktestStore((s) => s.results)
  const selectTrade = useBacktestStore((s) => s.selectTrade)
  const selectedId = useBacktestStore((s) => s.selectedTradeId)
  const [direction, setDirection] = useState('all')
  const [result, setResult] = useState('all')
  const [sortKey, setSortKey] = useState('entry_time')
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(1)

  const trades = results?.trades || []

  const filtered = useMemo(() => {
    let rows = trades
    if (direction !== 'all') rows = rows.filter((t) => t.direction === direction)
    if (result !== 'all') rows = rows.filter((t) => t.result === result)
    rows = [...rows].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av === bv) return 0
      const cmp = av > bv ? 1 : -1
      return sortDir === 'asc' ? cmp : -cmp
    })
    return rows
  }, [trades, direction, result, sortKey, sortDir])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const view = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  function toggleSort(k) {
    if (sortKey === k) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortKey(k); setSortDir('asc') }
  }

  if (!results) return null

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-gray-200 mr-auto">Trade Log ({filtered.length})</h2>
        <select className="input w-32" value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="all">All Directions</option>
          <option value="long">Longs</option>
          <option value="short">Shorts</option>
        </select>
        <select className="input w-32" value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="all">All Results</option>
          <option value="win">Wins</option>
          <option value="loss">Losses</option>
          <option value="breakeven">Breakeven</option>
          <option value="timeout">Timeout</option>
        </select>
        <button className="btn btn-ghost" onClick={() => exportCsv(filtered)}>Export CSV</button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-gray-400 border-b border-border">
            <tr>
              {[
                ['id', '#'], ['entry_time', 'Entry Time'], ['direction', 'Dir'],
                ['entry_price', 'Entry'], ['stop', 'Stop'], ['target_2', 'Target'],
                ['exit_price', 'Exit'], ['pnl', 'P&L $'], ['pnl_pct', 'P&L %'], ['result', 'Result'],
              ].map(([k, label]) => (
                <th key={k} className="text-left py-2 px-2 cursor-pointer hover:text-accent" onClick={() => toggleSort(k)}>
                  {label}{sortKey === k ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
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
                  <td className="px-2 py-1.5 font-mono">{t.entry_price?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.stop?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.target_2?.toFixed(5)}</td>
                  <td className="px-2 py-1.5 font-mono">{t.exit_price?.toFixed(5)}</td>
                  <td className={`px-2 py-1.5 font-mono ${t.pnl >= 0 ? 'text-good' : 'text-bad'}`}>{fmtMoney(t.pnl)}</td>
                  <td className={`px-2 py-1.5 font-mono ${t.pnl_pct >= 0 ? 'text-good' : 'text-bad'}`}>{t.pnl_pct?.toFixed(2)}%</td>
                  <td className="px-2 py-1.5 uppercase text-xs">{t.result}</td>
                </tr>
              )
            })}
            {!view.length && (
              <tr><td colSpan={10} className="px-2 py-6 text-center text-gray-500">No trades match the filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
        <span>Page {safePage} / {pageCount}</span>
        <div className="flex gap-2">
          <button className="btn btn-ghost px-2 py-1" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>Prev</button>
          <button className="btn btn-ghost px-2 py-1" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}>Next</button>
        </div>
      </div>
    </div>
  )
}
