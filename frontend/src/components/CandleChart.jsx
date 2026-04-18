import { useEffect, useMemo, useRef } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import { useBacktestStore } from '../store/useBacktestStore'

function toUnix(s) {
  return Math.floor(new Date(s).getTime() / 1000)
}

export default function CandleChart() {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef({})
  const results = useBacktestStore((s) => s.results)
  const selectedId = useBacktestStore((s) => s.selectedTradeId)

  // Build data once per result
  const data = useMemo(() => {
    if (!results?.candles) return null
    const candles = results.candles.map((c) => ({
      time: toUnix(c.datetime),
      open: c.open, high: c.high, low: c.low, close: c.close,
    }))
    const vwap = results.candles
      .filter((c) => c.vwap != null && !isNaN(c.vwap))
      .map((c) => ({ time: toUnix(c.datetime), value: c.vwap }))
    const emaFast = results.candles
      .filter((c) => c.ema_fast != null && !isNaN(c.ema_fast))
      .map((c) => ({ time: toUnix(c.datetime), value: c.ema_fast }))
    const emaSlow = results.candles
      .filter((c) => c.ema_slow != null && !isNaN(c.ema_slow))
      .map((c) => ({ time: toUnix(c.datetime), value: c.ema_slow }))
    const markers = results.trades.map((t) => ({
      time: toUnix(t.entry_time),
      position: t.direction === 'long' ? 'belowBar' : 'aboveBar',
      color: t.direction === 'long' ? '#22c55e' : '#ef4444',
      shape: t.direction === 'long' ? 'arrowUp' : 'arrowDown',
      text: `#${t.id}`,
      id: t.id,
    }))
    return { candles, vwap, emaFast, emaSlow, markers }
  }, [results])

  // Initialize chart
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
    const vwap = chart.addLineSeries({ color: '#22d3ee', lineWidth: 2, priceLineVisible: false })
    const emaFast = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, priceLineVisible: false })
    const emaSlow = chart.addLineSeries({ color: '#a855f7', lineWidth: 1, priceLineVisible: false })
    chartRef.current = chart
    seriesRef.current = { candle, vwap, emaFast, emaSlow }

    const ro = new ResizeObserver(() => chart.applyOptions({}))
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = {}
    }
  }, [])

  // Push data
  useEffect(() => {
    if (!data || !seriesRef.current.candle) return
    const { candle, vwap, emaFast, emaSlow } = seriesRef.current
    candle.setData(data.candles)
    vwap.setData(data.vwap)
    emaFast.setData(data.emaFast)
    emaSlow.setData(data.emaSlow)
    candle.setMarkers(data.markers)
    chartRef.current?.timeScale().fitContent()
  }, [data])

  // Trade overlay (stop / target lines for selected trade)
  useEffect(() => {
    const candle = seriesRef.current.candle
    if (!candle || !results) return
    const trade = results.trades.find((t) => t.id === selectedId)
    if (!trade) return
    const lines = []
    const opts = { axisLabelVisible: true, lineWidth: 1, lineStyle: 2 }
    lines.push(candle.createPriceLine({ price: trade.entry_price, color: '#22d3ee', title: 'Entry', ...opts }))
    lines.push(candle.createPriceLine({ price: trade.stop, color: '#ef4444', title: 'Stop', ...opts }))
    lines.push(candle.createPriceLine({ price: trade.target_2, color: '#22c55e', title: 'Target', ...opts }))
    chartRef.current?.timeScale().scrollToPosition(0, false)
    const t = toUnix(trade.entry_time)
    chartRef.current?.timeScale().setVisibleRange({ from: t - 3600, to: t + 3600 })
    return () => lines.forEach((l) => candle.removePriceLine(l))
  }, [selectedId, results])

  if (!results) {
    return (
      <div className="card text-sm text-gray-400 h-[420px] flex items-center justify-center">
        Candlestick chart will appear here after running a backtest.
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-gray-200">Price + Signals</h2>
        <div className="flex gap-3 text-[11px] text-gray-400">
          <span><span className="inline-block w-2 h-2 rounded-full bg-accent mr-1" />VWAP</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-warn mr-1" />EMA Fast</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-purple-500 mr-1" />EMA Slow</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full h-[420px]" />
    </div>
  )
}
