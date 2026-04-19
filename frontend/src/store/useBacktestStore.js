import { create } from 'zustand'

export const defaultParams = {
  ema_period: 9,
  ema_secondary: 20,
  allowed_patterns: ['engulfing', 'hammer_star', 'marubozu'],
  stop_loss_pips: 20,
  risk_reward: 2.0,
  pip_size: 0.0001,
  starting_capital: 10000,
  risk_per_trade_pct: 1.0,
  max_trades_per_day: 3,
  use_ny: true,
  session_start: '09:45',
  session_end: '11:30',
  session_2_start: '13:30',
  session_2_end: '15:00',
  use_session_2: true,
  timezone: 'America/New_York',
  use_london: false,
  london_start: '08:00',
  london_end: '11:00',
  london_tz: 'Europe/London',
  use_asian: false,
  asian_start: '09:00',
  asian_end: '12:00',
  asian_tz: 'Asia/Tokyo',
  allowed_days: [0, 1, 2, 3, 4],

  use_partial_tp: false,
  partial_tp_r: 1.5,
  partial_tp_pct: 50,

  use_breakeven: false,
  breakeven_r: 1.5,
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
  activeView: 'backtest',
  walkForwardResults: null,
  walkForwardTrainPct: 0.7,

  // Optimization
  optimizeResults: null,

  // Auto Robust
  autoRobustResults: null,

  setSession: ({ sessionId, summary, sample, source }) => {
    const startIso = summary?.date_range?.start || ''
    const endIso = summary?.date_range?.end || ''
    set({
      sessionId,
      dataSummary: summary,
      dataSample: sample || [],
      dataSource: source || get().dataSource,
      startDate: startIso ? startIso.slice(0, 10) : '',
      endDate: endIso ? endIso.slice(0, 10) : '',
      results: null,
    })
  },

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
  setAutoRobustResults: (autoRobustResults) => set({ autoRobustResults, error: null }),
  applyParams: (overrides) =>
    set((s) => ({ params: { ...s.params, ...overrides } })),
}))
