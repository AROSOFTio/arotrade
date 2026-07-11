import { Bot, ShieldAlert } from 'lucide-react'

import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'

export default function AIAnalysisPage() {
  return (
    <>
      <PageHeader eyebrow="Research" title="AI analysis" description="AI-generated chart analysis is kept separate from the signal and paper-execution workflow." />
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]"><EmptyState icon={Bot} title="Analysis provider not connected" description="No AI chart output is shown until the configured provider can return a verified, structured analysis. Generated text will not open a trade by itself." /><aside className="card"><div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50 text-amber-700"><ShieldAlert size={20} aria-hidden="true" /></div><h2 className="mt-4 text-sm font-semibold text-slate-900">Execution boundary</h2><p className="mt-2 text-sm leading-6 text-slate-500">Only approved signals that pass risk checks can reach the paper-trade workflow.</p></aside></section>
    </>
  )
}
