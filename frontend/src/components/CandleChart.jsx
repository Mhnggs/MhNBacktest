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

/**
 * Build a step-line series that covers kill-zone bars with semi-transparent
 * color. We fake this by plotting an area series at a very high/low price,
 * using color fills to tint the chart background. Lightweight-charts does
 * not expose a native "background shading by x-range", so we draw a thin
 * shaded area just above the lowest prices.
 */
function buildKillZoneSeries(candles) {
  if (!candles?.length) return { london: [], ny: [], ny_pm: [] }
  const outs = { london: [], ny: [], ny_pm: [] }
  for (const c of candles) {
    const t = toUnix(c.datetime)
    const kz = c.kill_zone || ''
    for (const key of ['london', 'ny', 'ny_pm']) {
      outs[key].push({
        time: t,
        value: kz === key ? 1 : 0,
      })
    }
  }
  return outs
}

export default function CandleChart() {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef({})
  const results = useBacktestStore((s) => s.results)
  const selectedId = useBacktestStore((s) => s.selectedTradeId)
  const selectTrade = useBacktestStore((s) => s.selectTrade)
  const [showLiquidity, setShowLiquidity] = useState(true)
  const [showFvg, setShowFvg] = useState(true)
  const [showKz, setShowKz] = useState(true)

  const data = useMemo(() => {
    if (!results?.candles) return null
    const raw = results.candles
    const candles = dedupSorted(raw.map((c) => ({
      time: toUnix(c.datetime),
      open: c.open, high: c.high, low: c.low, close: c.close,
    })))

    // Liquidity levels — prev-day + prev-session broadcast.
    const line = (key) => dedupSorted(raw
      .filter((c) => c[key] != null && !isNaN(c[key]))
      .map((c) => ({ time: toUnix(c.datetime), value: c[key] })))
    const pdh = line('prev_day_high')
    const pdl = line('prev_day_low')
    const lonH = line('prev_london_high')
    const lonL = line('prev_london_low')
    const nyH = line('prev_ny_high')
    const nyL = line('prev_ny_low')

    // Sweep + MSS markers.
    const markers = []
    for (const t of results.trades) {
      markers.push({
        time: toUnix(t.entry_time),
        position: t.direction === 'long' ? 'belowBar' : 'aboveBar',
        color: t.direction === 'long' ? '#22c55e' : '#ef4444',
        shape: t.direction === 'long' ? 'arrowUp' : 'arrowDown',
        text: `#${t.id}⭐${t.confluence_score ?? ''}`,
        id: t.id, kind: 'entry',
      })
      if (t.exit_time) {
        markers.push({
          time: toUnix(t.exit_time),
          position: t.direction === 'long' ? 'aboveBar' : 'belowBar',
          color: resultColor(t.result),
          shape: t.result === 'win' ? 'circle' : 'square',
          text: t.result === 'win' ? 'W' : t.result === 'loss' ? 'L' : '—',
          id: t.id, kind: 'exit',
        })
      }
    }
    markers.sort((a, b) => a.time - b.time)

    // FVG rectangles represented as top/bottom lines (lightweight-charts
    // doesn't expose filled rectangles natively; this is the cleanest
    // approximation without custom primitives).
    const fvgBullTop = dedupSorted(raw
      .filter((c) => c.fvg_bull_top != null && !isNaN(c.fvg_bull_top))
      .map((c) => ({ time: toUnix(c.datetime), value: c.fvg_bull_top })))
    const fvgBullBot = dedupSorted(raw
      .filter((c) => c.fvg_bull_bot != null && !isNaN(c.fvg_bull_bot))
      .map((c) => ({ time: toUnix(c.datetime), value: c.fvg_bull_bot })))
    const fvgBearTop = dedupSorted(raw
      .filter((c) => c.fvg_bear_top != null && !isNaN(c.fvg_bear_top))
      .map((c) => ({ time: toUnix(c.datetime), value: c.fvg_bear_top })))
    const fvgBearBot = dedupSorted(raw
      .filter((c) => c.fvg_bear_bot != null && !isNaN(c.fvg_bear_bot))
      .map((c) => ({ time: toUnix(c.datetime), value: c.fvg_bear_bot })))

    const kz = buildKillZoneSeries(raw)

    // HTF bias (last candle determines the indicator in the header).
    const lastBias = raw.length ? raw[raw.length - 1].htf_bias : 'neutral'

    return {
      candles, pdh, pdl, lonH, lonL, nyH, nyL,
      markers, fvgBullTop, fvgBullBot, fvgBearTop, fvgBearBot, kz, lastBias,
    }
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
    const line = (color, style = 0, w = 1) => chart.addLineSeries({
      color, lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: false,
    })
    const areaKz = (color) => chart.addAreaSeries({
      topColor: color, bottomColor: color + '00', lineColor: color + '00',
      priceLineVisible: false, lastValueVisible: false, priceScaleId: '',
    })

    const pdh = line('#ef4444', 0, 1)          // solid red
    const pdl = line('#22c55e', 0, 1)          // solid green
    const lonH = line('#fb923c', 2, 1)         // dashed orange
    const lonL = line('#fb923c', 2, 1)
    const nyH = line('#60a5fa', 2, 1)          // dashed blue
    const nyL = line('#60a5fa', 2, 1)
    const fvgBullTop = line('#22c55e', 1, 1)   // dotted green
    const fvgBullBot = line('#22c55e', 1, 1)
    const fvgBearTop = line('#ef4444', 1, 1)
    const fvgBearBot = line('#ef4444', 1, 1)

    const kzLondon = areaKz('#facc1533')
    const kzNy = areaKz('#3b82f633')
    const kzNyPm = areaKz('#a855f733')

    chartRef.current = chart
    seriesRef.current = {
      candle, pdh, pdl, lonH, lonL, nyH, nyL,
      fvgBullTop, fvgBullBot, fvgBearTop, fvgBearBot,
      kzLondon, kzNy, kzNyPm,
    }

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
    const s = seriesRef.current
    s.candle.setData(data.candles)
    s.pdh.setData(showLiquidity ? data.pdh : [])
    s.pdl.setData(showLiquidity ? data.pdl : [])
    s.lonH.setData(showLiquidity ? data.lonH : [])
    s.lonL.setData(showLiquidity ? data.lonL : [])
    s.nyH.setData(showLiquidity ? data.nyH : [])
    s.nyL.setData(showLiquidity ? data.nyL : [])
    s.fvgBullTop.setData(showFvg ? data.fvgBullTop : [])
    s.fvgBullBot.setData(showFvg ? data.fvgBullBot : [])
    s.fvgBearTop.setData(showFvg ? data.fvgBearTop : [])
    s.fvgBearBot.setData(showFvg ? data.fvgBearBot : [])

    // Kill-zone shading: invisible area series doesn't really work natively.
    // We just toggle markers on the time axis instead.
    s.kzLondon.setData(showKz ? data.kz.london : [])
    s.kzNy.setData(showKz ? data.kz.ny : [])
    s.kzNyPm.setData(showKz ? data.kz.ny_pm : [])

    s.candle.setMarkers(data.markers)
    chartRef.current?.timeScale().fitContent()
  }, [data, showLiquidity, showFvg, showKz])

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
    }
    const tEntry = toUnix(trade.entry_time)
    const tExit = trade.exit_time ? toUnix(trade.exit_time) : tEntry + 3600
    const pad = Math.max(1800, (tExit - tEntry))
    chartRef.current?.timeScale().setVisibleRange({ from: tEntry - pad, to: tExit + pad })
    return () => lines.forEach((l) => candle.removePriceLine(l))
  }, [selectedId, results])

  if (!results) {
    return (
      <div className="card text-sm text-gray-400 h-[460px] flex items-center justify-center">
        Candlestick chart with liquidity levels, FVGs, and sweep markers will appear after running a backtest.
      </div>
    )
  }

  const bars = data?.candles?.length ?? 0
  const signals = results.trades?.length ?? 0
  const biasLabel = {
    bullish: <span className="text-good">📈 BULLISH</span>,
    bearish: <span className="text-bad">📉 BEARISH</span>,
    neutral: <span className="text-gray-400">↔ NEUTRAL</span>,
  }[data?.lastBias || 'neutral']

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <h2 className="text-sm font-semibold text-gray-200">
          Silver Bullet Chart <span className="text-[11px] text-gray-400 ml-2">1H bias: {biasLabel}</span>
        </h2>
        <div className="flex items-center gap-3 text-[11px] text-gray-400">
          <span>{bars} bars · {signals} trades</span>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" className="accent-accent" checked={showLiquidity}
              onChange={(e) => setShowLiquidity(e.target.checked)} />
            Liquidity
          </label>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" className="accent-accent" checked={showFvg}
              onChange={(e) => setShowFvg(e.target.checked)} />
            FVGs
          </label>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" className="accent-accent" checked={showKz}
              onChange={(e) => setShowKz(e.target.checked)} />
            Kill zones
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
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1" style={{ background: '#ef4444' }} />PDH</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1" style={{ background: '#22c55e' }} />PDL</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1 border-t border-dashed border-orange-400" />Prev London H/L</span>
        <span><span className="inline-block w-3 h-0.5 align-middle mr-1 border-t border-dashed border-blue-400" />Prev NY H/L</span>
        <span>FVGs (dotted) · ▲ long · ▼ short · ⭐ confluence score</span>
      </div>
      <div ref={containerRef} className="w-full h-[460px]" />
    </div>
  )
}
