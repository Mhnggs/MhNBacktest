import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import { useBacktestStore } from '../store/useBacktestStore'

function toUnix(s) {
  return Math.floor(new Date(s).getTime() / 1000)
}

function dedupSorted(points) {
  if (!points.length) return points
  const map = new Map()
  for (const p of points) {
    if (Number.isFinite(p.time)) map.set(p.time, p)
  }
  return Array.from(map.values()).sort((a, b) => a.time - b.time)
}

function resultColor(result) {
  if (result === 'win') return '#22c55e'
  if (result === 'loss') return '#ef4444'
  return '#6b7280'
}

export default function CandleChart() {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef({})
  const results = useBacktestStore((s) => s.results)
  const selectedId = useBacktestStore((s) => s.selectedTradeId)
  const selectTrade = useBacktestStore((s) => s.selectTrade)
  const [showDr, setShowDr] = useState(true)

  const data = useMemo(() => {
    if (!results?.candles) return null
    const candles = dedupSorted(results.candles.map((c) => ({
      time: toUnix(c.datetime),
      open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    const drHigh = dedupSorted(results.candles
      .filter((c) => c.dr_high != null && !isNaN(c.dr_high) && c.post_dr)
      .map((c) => ({ time: toUnix(c.datetime), value: c.dr_high })))
    const drLow = dedupSorted(results.candles
      .filter((c) => c.dr_low != null && !isNaN(c.dr_low) && c.post_dr)
      .map((c) => ({ time: toUnix(c.datetime), value: c.dr_low })))
    const drMid = dedupSorted(results.candles
      .filter((c) => c.dr_midpoint != null && !isNaN(c.dr_midpoint) && c.post_dr)
      .map((c) => ({ time: toUnix(c.datetime), value: c.dr_midpoint })))

    const markers = []
    for (const t of results.trades) {
      markers.push({
        time: toUnix(t.entry_time),
        position: t.direction === 'long' ? 'belowBar' : 'aboveBar',
        color: t.direction === 'long' ? '#22c55e' : '#ef4444',
        shape: t.direction === 'long' ? 'arrowUp' : 'arrowDown',
        text: `#${t.id}`,
        id: t.id,
        kind: 'entry',
      })
      if (t.exit_time) {
        markers.push({
          time: toUnix(t.exit_time),
          position: t.direction === 'long' ? 'aboveBar' : 'belowBar',
          color: resultColor(t.result),
          shape: t.result === 'win' ? 'circle' : 'square',
          text: t.result === 'win' ? 'W' : t.result === 'loss' ? 'L' : '—',
          id: t.id,
          kind: 'exit',
        })
      }
    }
    markers.sort((a, b) => a.time - b.time)
    return { candles, drHigh, drLow, drMid, markers }
  }, [results])

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: '#0b0f17' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#111827' }, horzLines: { color: '#111827' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1f2937' },
      timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false },
    })
    const candle = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })
    const drHigh = chart.addLineSeries({
      color: '#38bdf8', lineWidth: 2, priceLineVisible: false,
    })
    const drLow = chart.addLineSeries({
      color: '#f97316', lineWidth: 2, priceLineVisible: false,
    })
    const drMid = chart.addLineSeries({
      color: '#a855f7', lineWidth: 1, lineStyle: 2, priceLineVisible: false,
    })
    chartRef.current = chart
    seriesRef.current = { candle, drHigh, drLow, drMid }

    const clickSub = chart.subscribeClick((p) => {
      if (!p?.time || !data?.markers) return
      const tol = 60 * 10
      let best = null, bestDelta = Infinity
      for (const m of data.markers) {
        const d = Math.abs(m.time - p.time)
        if (d < bestDelta && d <= tol) { bestDelta = d; best = m }
      }
      if (best) selectTrade(best.id)
    })

    const ro = new ResizeObserver(() => chart.applyOptions({}))
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.unsubscribeClick(clickSub)
      chart.remove()
      chartRef.current = null
      seriesRef.current = {}
    }
  }, [])

  useEffect(() => {
    if (!data || !seriesRef.current.candle) return
    const { candle, drHigh, drLow, drMid } = seriesRef.current
    candle.setData(data.candles)
    drHigh.setData(showDr ? data.drHigh : [])
    drLow.setData(showDr ? data.drLow : [])
    drMid.setData(showDr ? data.drMid : [])
    candle.setMarkers(data.markers)
    chartRef.current?.timeScale().fitContent()
  }, [data, showDr])

  useEffect(() => {
    const candle = seriesRef.current.candle
    if (!candle || !results) return
    const trade = results.trades.find((t) => t.id === selectedId)
    if (!trade) return
    const lines = []
    const opts = { axisLabelVisible: true, lineWidth: 1, lineStyle: 2 }
    lines.push(candle.createPriceLine({ price: trade.entry_price, color: '#22d3ee', title: 'Entry', ...opts }))
    lines.push(candle.createPriceLine({ price: trade.stop, color: '#ef4444', title: 'Stop', ...opts }))
    if (trade.target1 != null) {
      lines.push(candle.createPriceLine({ price: trade.target1, color: '#facc15', title: 'T1', ...opts }))
    }
    if (trade.target2 != null) {
      lines.push(candle.createPriceLine({ price: trade.target2, color: '#22c55e', title: 'T2', ...opts }))
    } else if (trade.target != null) {
      lines.push(candle.createPriceLine({ price: trade.target, color: '#22c55e', title: 'Target', ...opts }))
    }
    const tEntry = toUnix(trade.entry_time)
    const tExit = trade.exit_time ? toUnix(trade.exit_time) : tEntry + 3600
    const pad = Math.max(1800, (tExit - tEntry))
    chartRef.current?.timeScale().setVisibleRange({ from: tEntry - pad, to: tExit + pad })
    return () => lines.forEach((l) => candle.removePriceLine(l))
  }, [selectedId, results])

  if (!results) {
    return (
      <div className="card text-sm text-gray-400 h-[420px] flex items-center justify-center">
        Candlestick chart will appear here after running a backtest.
      </div>
    )
  }

  const bars = data?.candles?.length ?? 0
  const signals = results.trades?.length ?? 0

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <h2 className="text-sm font-semibold text-gray-200">Price + DR Levels</h2>
        <div className="flex items-center gap-3 text-[11px] text-gray-400">
          <span>{bars} bars · {signals} trades</span>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" className="accent-accent" checked={showDr}
              onChange={(e) => setShowDr(e.target.checked)} />
            DR levels
          </label>
          <button
            className="btn btn-ghost px-2 py-0.5 text-[10px]"
            onClick={() => chartRef.current?.timeScale().fitContent()}
          >
            Reset zoom
          </button>
          {selectedId != null && (
            <button
              className="btn btn-ghost px-2 py-0.5 text-[10px]"
              onClick={() => selectTrade(null)}
            >
              Clear selection
            </button>
          )}
        </div>
      </div>
      <div className="flex gap-3 text-[10px] text-gray-400 mb-1 flex-wrap">
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1" style={{ background: '#38bdf8' }} />DR High</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1" style={{ background: '#f97316' }} />DR Low</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1" style={{ background: '#a855f7' }} />DR Mid</span>
        <span>▲ long entry · ▼ short entry · ● win · ■ loss</span>
      </div>
      <div ref={containerRef} className="w-full h-[420px]" />
    </div>
  )
}
