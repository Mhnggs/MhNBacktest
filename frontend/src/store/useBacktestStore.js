import { create } from 'zustand'

export const defaultParams = {
  ema_period: 9,
  ema_secondary: 20,
  volume_multiplier: 1.2,
  risk_reward: 2.0,
  partial_rr: 1.5,
  use_partial_tp: true,
  stop_buffer_ticks: 3,
  tick_size: 0.0001,
  max_trades_per_day: 3,
  session_start: '09:45',
  session_end: '11:30',
  session_2_start: '13:30',
  session_2_end: '15:00',
  use_session_2: true,
  timezone: 'America/New_York',
  vwap_max_distance_pct: 2.0,
  chop_filter_crossings: 3,
  require_volume: true,
  require_pattern: true,
  min_ema_slope: 0.0001,
  ema_touch_pct: 0.001,
  starting_capital: 10000,
  risk_per_trade_pct: 1.0,
  use_adx_filter: true,
  adx_period: 14,
  adx_threshold: 25,
  allowed_days: [0, 1, 2, 3, 4],
}

export const useBacktestStore = create((set, get) => ({
  // Data
  sessionId: null,
  dataSource: 'upload',
  dataSummary: null,
  dataSample: [],

  // Parameters
  params: { ...defaultParams },

  // Date filter
  startDate: '',
  endDate: '',

  // Results
  isRunning: false,
  results: null,
  selectedTradeId: null,
  error: null,

  // View / walk-forward
  activeView: 'backtest', // 'backtest' | 'walkforward' | 'optimize'
  walkForwardResults: null,
  walkForwardTrainPct: 0.7,

  // Optimization
  optimizeResults: null,

  setSession: ({ sessionId, summary, sample, source }) =>
    set({
      sessionId,
      dataSummary: summary,
      dataSample: sample || [],
      dataSource: source || get().dataSource,
      results: null,
    }),

  setDataSource: (dataSource) => set({ dataSource }),

  setParam: (key, value) =>
    set((s) => ({ params: { ...s.params, [key]: value } })),

  resetParams: () => set({ params: { ...defaultParams } }),

  setDateRange: (startDate, endDate) => set({ startDate, endDate }),

  setRunning: (isRunning) => set({ isRunning }),
  setResults: (results) => set({ results, error: null }),
  setError: (error) => set({ error, isRunning: false }),
  selectTrade: (id) => set({ selectedTradeId: id }),

  setActiveView: (activeView) => set({ activeView }),
  setWalkForwardResults: (walkForwardResults) => set({ walkForwardResults, error: null }),
  setWalkForwardTrainPct: (walkForwardTrainPct) => set({ walkForwardTrainPct }),
  setOptimizeResults: (optimizeResults) => set({ optimizeResults, error: null }),
}))
