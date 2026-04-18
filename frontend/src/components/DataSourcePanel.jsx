import { useEffect, useRef, useState } from 'react'
import { fetchTwelveData, uploadCsv } from '../api/client'
import { useBacktestStore } from '../store/useBacktestStore'

export default function DataSourcePanel() {
  const { dataSource, setDataSource, setSession, dataSummary, sessionId } = useBacktestStore()
  return (
    <div className="card">
      <h2 className="text-sm font-semibold mb-3 text-gray-200">Data Source</h2>
      <div className="flex gap-2 mb-4">
        <button
          className={`btn flex-1 ${dataSource === 'upload' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setDataSource('upload')}
        >
          Upload CSV
        </button>
        <button
          className={`btn flex-1 ${dataSource === 'twelvedata' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setDataSource('twelvedata')}
        >
          TwelveData
        </button>
      </div>

      {dataSource === 'upload' ? <UploadPanel /> : <TwelveDataPanel />}

      {sessionId && dataSummary && (
        <div className="mt-4 text-xs text-gray-300 border-t border-border pt-3">
          <div className="flex justify-between">
            <span className="text-gray-400">Session</span>
            <span className="font-mono">{sessionId}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Rows</span>
            <span>{dataSummary.rows_loaded?.toLocaleString?.()}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Range</span>
            <span className="text-right text-[11px]">
              {dataSummary.date_range?.start?.slice(0, 10)} → {dataSummary.date_range?.end?.slice(0, 10)}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function UploadPanel() {
  const setSession = useBacktestStore((s) => s.setSession)
  const inputRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function handleFiles(files) {
    if (!files || !files.length) return
    setBusy(true)
    setErr(null)
    try {
      const data = await uploadCsv(Array.from(files))
      setSession({
        sessionId: data.session_id,
        summary: data,
        sample: data.sample,
        source: 'upload',
      })
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <label
        className="block border border-dashed border-border rounded-lg p-4 text-center cursor-pointer hover:border-accent"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          handleFiles(e.dataTransfer.files)
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.txt"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="text-sm text-gray-300">
          {busy ? 'Uploading...' : 'Drop MT CSV files here or click to browse'}
        </div>
        <div className="text-xs text-gray-500 mt-1">Supports comma, semicolon, tab separators</div>
      </label>
      {err && <div className="text-bad text-xs mt-2">{err}</div>}
    </div>
  )
}

function TwelveDataPanel() {
  const setSession = useBacktestStore((s) => s.setSession)
  const [apiKey, setApiKey] = useState(localStorage.getItem('td_api_key') || '')
  const [symbol, setSymbol] = useState('XAU/USD')
  const [interval, setInterval] = useState('5min')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    localStorage.setItem('td_api_key', apiKey)
  }, [apiKey])

  async function fetchNow() {
    setBusy(true)
    setErr(null)
    try {
      const data = await fetchTwelveData({
        api_key: apiKey, symbol, interval,
        start_date: start, end_date: end, use_cache: true,
      })
      setSession({
        sessionId: data.session_id,
        summary: data,
        sample: data.sample,
        source: 'twelvedata',
      })
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 text-sm">
      <div>
        <div className="label">API Key</div>
        <input className="input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="label">Symbol</div>
          <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </div>
        <div>
          <div className="label">Interval</div>
          <select className="input" value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value="1min">1min</option>
            <option value="5min">5min</option>
            <option value="15min">15min</option>
            <option value="30min">30min</option>
            <option value="1h">1h</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="label">Start</div>
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <div className="label">End</div>
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>
      <button className="btn btn-primary w-full" disabled={busy} onClick={fetchNow}>
        {busy ? 'Fetching...' : 'Fetch Data'}
      </button>
      {err && <div className="text-bad text-xs">{err}</div>}
    </div>
  )
}
