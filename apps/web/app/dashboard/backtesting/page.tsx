import { DatabaseZap, LineChart } from 'lucide-react'

import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'

export default function BacktestingPage() {
  return (
    <>
      <PageHeader eyebrow="Validation" title="Backtesting" description="Historical market data and executable strategy rules must be connected before this workspace can produce results." />
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]"><EmptyState icon={LineChart} title="No verified backtest data" description="The backend correctly prevents backtest results from being generated until a market-data source and testable strategy rules are available." /><aside className="card"><div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><DatabaseZap size={20} aria-hidden="true" /></div><h2 className="mt-4 text-sm font-semibold text-slate-900">Current requirement</h2><p className="mt-2 text-sm leading-6 text-slate-500">Backtests remain unavailable rather than showing made-up returns or win rates.</p></aside></section>
    </>
  )
}
