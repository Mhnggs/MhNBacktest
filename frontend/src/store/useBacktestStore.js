import { create } from 'zustand'

export const defaultParams = {
  // Instrument / sizing
  pip_size: 0.0001,
  starting_capital: 10000,
  risk_per_trade_pct: 1.0,

  // DR window
  dr_start_time: '09:30',
  dr_end_time: '10:30',
  dr_timezone: 'America/New_York',
  min_dr_range_pips: 15,
  max_dr_range_pips: 70,

  // Entry
  entry_type: 'retest_then_midpoint',
  retest_tolerance_pips: 5,
  require_confirmation_candle: true,
  confirmation_patterns: ['marubozu', 'engulfing'],

  // Time limits
  retest_window_minutes: 90,
  last_entry_time: '13:00',

  // Risk / exits
  stop_buffer_pips: 3,
  use_partial_tp: true,
  partial_tp_1_mult: 0.5,
  partial_tp_2_mult: 1.0,
  partial_tp_pct: 50,
  move_be_after_t1: true,
  max_trades_per_day: 1,

  // News filter
  enable_news_filter: true,
  custom_skip_dates: [],

  // Day-of-week filter
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
