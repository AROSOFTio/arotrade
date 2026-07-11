'use client'

import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'

import { apiRequest, errorMessage } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type UserSettings = {
  default_risk_percent: number
  max_daily_loss_percent: number
  max_open_trades: number
  trading_mode: string
  enable_live_trading: boolean
}

export default function RiskPage() {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [form, setForm] = useState({ default_risk_percent: '', max_daily_loss_percent: '', max_open_trades: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    apiRequest<UserSettings>('/auth/me')
      .then((user) => { setSettings(user); setForm({ default_risk_percent: String(user.default_risk_percent), max_daily_loss_percent: String(user.max_daily_loss_percent), max_open_trades: String(user.max_open_trades) }) })
      .catch((requestError) => setError(errorMessage(requestError)))
      .finally(() => setLoading(false))
  }, [])

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSaving(true)
    try {
      const user = await apiRequest<UserSettings>('/auth/me/settings', { method: 'PATCH', body: JSON.stringify({ default_risk_percent: Number(form.default_risk_percent), max_daily_loss_percent: Number(form.max_daily_loss_percent), max_open_trades: Number(form.max_open_trades) }) })
      setSettings(user)
      setMessage('Risk controls saved.')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setSaving(false) }
  }

  return (
    <>
      <PageHeader eyebrow="Execution safeguards" title="Risk controls" description="Set the account-level limits used by the signal and paper-trade workflow." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(280px,0.45fr)]"><form onSubmit={save} className="card"><div className="flex items-center gap-2"><span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><ShieldCheck size={20} aria-hidden="true" /></span><div><h2 className="text-sm font-semibold text-slate-900">Account limits</h2><p className="mt-0.5 text-xs text-slate-500">Changes apply to future risk-gate decisions.</p></div></div><div className="mt-6 grid gap-5 sm:grid-cols-3"><div><label htmlFor="risk-percent" className="label">Risk per trade %</label><input id="risk-percent" type="number" min="0.1" max="5" step="0.1" className="input-base" value={form.default_risk_percent} onChange={(event) => setForm((current) => ({ ...current, default_risk_percent: event.target.value }))} required /></div><div><label htmlFor="daily-loss-percent" className="label">Daily loss limit %</label><input id="daily-loss-percent" type="number" min="0.1" max="25" step="0.1" className="input-base" value={form.max_daily_loss_percent} onChange={(event) => setForm((current) => ({ ...current, max_daily_loss_percent: event.target.value }))} required /></div><div><label htmlFor="max-open-trades" className="label">Maximum open trades</label><input id="max-open-trades" type="number" min="1" max="20" className="input-base" value={form.max_open_trades} onChange={(event) => setForm((current) => ({ ...current, max_open_trades: event.target.value }))} required /></div></div><button type="submit" disabled={loading || saving} className="btn-primary mt-6">{saving ? 'Saving…' : 'Save controls'}</button></form><aside className="card"><h2 className="text-sm font-semibold text-slate-900">Execution status</h2><dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between gap-3 border-b border-slate-100 pb-3"><dt className="text-slate-500">Account mode</dt><dd className="font-semibold capitalize text-[#1d4ed8]">{settings?.trading_mode || '—'}</dd></div><div className="flex justify-between gap-3 border-b border-slate-100 pb-3"><dt className="text-slate-500">Live broker adapter</dt><dd className="font-semibold text-slate-900">Not connected</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Live permission</dt><dd className="font-semibold text-slate-900">{settings?.enable_live_trading ? 'Enabled' : 'Locked'}</dd></div></dl></aside></section>
    </>
  )
}
