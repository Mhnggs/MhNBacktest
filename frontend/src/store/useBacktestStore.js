import { create } from 'zustand'

export const defaultParams = {
  // Instrument / sizing
  pip_size: 0.0001,
  starting_capital: 10000,
  risk_per_trade_pct: 1.0,

  // Kill zones (NY time windows)
  enable_london_sb: true,
  enable_ny_sb: true,
  enable_ny_pm_sb: false,

  // Liquidity detection
  swing_lookback: 5,
  equal_level_tolerance_pips: 3,
  min_sweep_pips: 3,
  sweep_confirmation_candles: 3,

  // Displacement
  displacement_body_pips: 8,
  displacement_close_pct: 0.7,

  // FVG
  min_fvg_size_pips: 3,
  fvg_max_age_candles: 20,
  fvg_entry_type: '50% midpoint',

  // MSS
  require_mss: true,

  // Order block
  require_ob_confluence: false,

  // HTF bias
  require_htf_alignment: true,
  htf_neutral_action: 'Skip trade',

  // Risk / exits
  stop_type: 'Beyond sweep',
  stop_buffer_pips: 3,
  fixed_stop_pips: 10,
  rr_ratio: 2.0,
  use_partial_tp: true,
  max_trades_per_killzone: 1,
  max_trades_per_day: 2,
  close_at_killzone_end: true,

  // Confluence
  min_confluence_score: 5,

  // Filters
  enable_news_filter: true,
  custom_skip_dates: [],
  allowed_days: [0, 1, 2, 3, 4],
  min_fvg_to_stop_ratio: 0.5,
  spread_pips: 0.2,

  // Circuit breakers
  enable_daily_circuit_breaker: true,
  daily_loss_limit_pct: 2.0,
  enable_weekly_circuit_breaker: true,
  weekly_loss_limit_pct: 5.0,
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
