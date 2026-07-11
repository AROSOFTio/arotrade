'use client'

import { useEffect, useState } from 'react'
import { BookOpen, Plus } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'
import { StatusBadge } from '../../components/status-badge'

type JournalEntry = {
  id: number
  symbol: string
  trade_date: string
  strategy?: string | null
  result: string
  profit_loss?: number | null
  emotion_before?: string | null
  notes?: string | null
  lesson_learned?: string | null
  created_at: string
}

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [form, setForm] = useState({ symbol: '', trade_date: new Date().toISOString().slice(0, 16), result: 'win', profit_loss: '', strategy: '', notes: '', lesson_learned: '' })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadEntries = async () => {
    setLoading(true)
    try { setEntries(await apiRequest<JournalEntry[]>('/journal')) } catch (requestError) { setError(errorMessage(requestError)) } finally { setLoading(false) }
  }

  useEffect(() => { void loadEntries() }, [])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const entry = await apiRequest<JournalEntry>('/journal', { method: 'POST', body: JSON.stringify({ symbol: form.symbol.trim().toUpperCase(), trade_date: new Date(form.trade_date).toISOString(), result: form.result, profit_loss: form.profit_loss ? Number(form.profit_loss) : null, strategy: form.strategy || null, notes: form.notes || null, lesson_learned: form.lesson_learned || null }) })
      setEntries((current) => [entry, ...current])
      setForm((current) => ({ ...current, symbol: '', profit_loss: '', strategy: '', notes: '', lesson_learned: '' }))
      setMessage('Journal entry saved.')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setSubmitting(false) }
  }

  const wins = entries.filter((entry) => entry.result === 'win').length
  const winRate = entries.length ? (wins / entries.length) * 100 : 0

  return (
    <>
      <PageHeader eyebrow="Review log" title="Trading journal" description="Record outcomes and lessons from paper trades without turning them into unverified performance claims." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-4 sm:grid-cols-3"><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Entries</p><p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : entries.length}</p></div><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Recorded wins</p><p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : wins}</p></div><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Journal win rate</p><p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : `${winRate.toFixed(0)}%`}</p></div></section>
      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(340px,0.75fr)_minmax(0,1.25fr)]"><form onSubmit={submit} className="card h-fit"><div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Plus size={18} aria-hidden="true" /></span><div><h2 className="text-sm font-semibold text-slate-900">Add entry</h2><p className="mt-0.5 text-xs text-slate-500">Capture the outcome while it is fresh.</p></div></div><div className="mt-5 grid grid-cols-2 gap-4"><div><label className="label" htmlFor="journal-symbol">Symbol</label><input id="journal-symbol" className="input-base" value={form.symbol} onChange={(event) => setForm((current) => ({ ...current, symbol: event.target.value }))} required /></div><div><label className="label" htmlFor="journal-date">Trade date</label><input id="journal-date" type="datetime-local" className="input-base" value={form.trade_date} onChange={(event) => setForm((current) => ({ ...current, trade_date: event.target.value }))} required /></div><div><label className="label" htmlFor="journal-result">Result</label><select id="journal-result" className="input-base" value={form.result} onChange={(event) => setForm((current) => ({ ...current, result: event.target.value }))}><option value="win">Win</option><option value="loss">Loss</option><option value="breakeven">Breakeven</option></select></div><div><label className="label" htmlFor="journal-pnl">P/L</label><input id="journal-pnl" type="number" step="any" className="input-base" value={form.profit_loss} onChange={(event) => setForm((current) => ({ ...current, profit_loss: event.target.value }))} /></div></div><div className="mt-4"><label className="label" htmlFor="journal-strategy">Strategy</label><input id="journal-strategy" className="input-base" value={form.strategy} onChange={(event) => setForm((current) => ({ ...current, strategy: event.target.value }))} /></div><div className="mt-4"><label className="label" htmlFor="journal-notes">Notes</label><textarea id="journal-notes" className="input-base min-h-20 resize-y" value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} /></div><div className="mt-4"><label className="label" htmlFor="journal-lesson">Lesson learned</label><textarea id="journal-lesson" className="input-base min-h-20 resize-y" value={form.lesson_learned} onChange={(event) => setForm((current) => ({ ...current, lesson_learned: event.target.value }))} /></div><button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Saving…' : 'Save entry'}</button></form><div className="card overflow-hidden p-0"><div className="border-b border-slate-200 px-5 py-4"><h2 className="text-sm font-semibold text-slate-900">Journal history</h2><p className="mt-1 text-xs text-slate-500">Entries are sorted by creation time.</p></div>{loading ? <div className="p-8 text-sm text-slate-500">Loading journal…</div> : entries.length ? <div className="divide-y divide-slate-100">{entries.map((entry) => <article key={entry.id} className="px-5 py-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold text-slate-900">{entry.symbol} {entry.strategy && <span className="font-normal text-slate-500">· {entry.strategy}</span>}</h3><p className="mt-1 text-xs text-slate-500">{formatDate(entry.trade_date)}</p></div><div className="flex items-center gap-3"><span className={`text-sm font-semibold ${entry.profit_loss && entry.profit_loss < 0 ? 'text-red-700' : 'text-emerald-700'}`}>{entry.profit_loss === null || entry.profit_loss === undefined ? '—' : formatNumber(entry.profit_loss)}</span><StatusBadge value={entry.result} /></div></div>{entry.notes && <p className="mt-3 text-sm leading-6 text-slate-600">{entry.notes}</p>}{entry.lesson_learned && <p className="mt-2 border-l-2 border-blue-200 pl-3 text-sm leading-6 text-slate-600">{entry.lesson_learned}</p>}</article>)}</div> : <EmptyState icon={BookOpen} title="No journal entries" description="Save the outcome and lesson from your next paper-trade review." />}</div></section>
    </>
  )
}
