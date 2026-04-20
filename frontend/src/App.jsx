import DataSourcePanel from './components/DataSourcePanel'
import ParameterPanel from './components/ParameterPanel'
import StatsPanel from './components/StatsPanel'
import Diagnostics from './components/Diagnostics'
import EquityCurve from './components/EquityCurve'
import CandleChart from './components/CandleChart'
import TradeLog from './components/TradeLog'
import Breakdowns from './components/Breakdowns'
import WalkForward from './components/WalkForward'
import Optimize from './components/Optimize'
import FindRobust from './components/FindRobust'
import { useBacktestStore } from './store/useBacktestStore'

const VIEWS = [
  { key: 'backtest', label: 'Backtest' },
  { key: 'findrobust', label: 'Find Robust' },
  { key: 'walkforward', label: 'Walk Forward' },
  { key: 'optimize', label: 'Optimize' },
]

export default function App() {
  const activeView = useBacktestStore((s) => s.activeView)
  const setActiveView = useBacktestStore((s) => s.setActiveView)
  const results = useBacktestStore((s) => s.results)

  return (
    <div className="min-h-full">
      <header className="border-b border-border bg-panel/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-[1700px] mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">
            DR / IDR Breakout-Retest <span className="text-accent">Backtest</span>
          </h1>
          <div className="flex items-center gap-1">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                onClick={() => setActiveView(v.key)}
                className={`btn px-4 py-1.5 text-xs ${activeView === v.key ? 'btn-primary' : 'btn-ghost'}`}
              >
                {v.label}
              </button>
            ))}
            {activeView === 'backtest' && results && (
              <button
                onClick={() => window.print()}
                className="btn btn-ghost px-4 py-1.5 text-xs ml-2"
                title="Save report as PDF via browser print dialog"
              >
                Download PDF
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1700px] mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        <aside className="lg:col-span-3 space-y-4">
          <DataSourcePanel />
          <ParameterPanel />
        </aside>

        {activeView === 'backtest' ? (
          <>
            <section className="lg:col-span-6 space-y-4">
              <EquityCurve />
              <CandleChart />
              <Breakdowns />
            </section>

            <aside className="lg:col-span-3 space-y-4">
              <StatsPanel />
              <Diagnostics />
            </aside>

            <div className="lg:col-span-12">
              <TradeLog />
            </div>
          </>
        ) : activeView === 'walkforward' ? (
          <section className="lg:col-span-9">
            <WalkForward />
          </section>
        ) : activeView === 'findrobust' ? (
          <section className="lg:col-span-9">
            <FindRobust />
          </section>
        ) : (
          <section className="lg:col-span-9">
            <Optimize />
          </section>
        )}
      </main>

      <footer className="border-t border-border py-4 text-center text-xs text-gray-500">
        Built for research purposes only — not financial advice.
      </footer>
    </div>
  )
}
