'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { ArrowRight, UserPlus } from 'lucide-react'

import { apiRequest, errorMessage } from '../components/api'

type TokenResponse = {
  access_token: string
  refresh_token: string
}

export default function RegisterPage() {
  const router = useRouter()
  const [form, setForm] = useState({ fullName: '', email: '', password: '', confirmPassword: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }))

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    if (form.password !== form.confirmPassword) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      const response = await apiRequest<TokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify({ email: form.email, password: form.password, full_name: form.fullName || null }) })
      window.localStorage.setItem('access_token', response.access_token)
      window.localStorage.setItem('refresh_token', response.refresh_token)
      router.replace('/dashboard')
    } catch (requestError) { setError(errorMessage(requestError)) } finally { setLoading(false) }
  }

  return (
    <main className="flex min-h-screen bg-[#f6f7f9] px-4 py-8 sm:items-center sm:justify-center"><section className="mx-auto w-full max-w-md"><Link href="/" className="mb-8 inline-flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#2563eb] text-sm font-black text-white">AT</span><span><span className="block text-base font-bold text-slate-950">AroTrade</span><span className="block text-xs font-medium text-slate-500">by AROFi</span></span></Link><div className="card"><div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><UserPlus size={21} aria-hidden="true" /></div><h1 className="mt-5 text-2xl font-bold text-slate-950">Create account</h1><p className="mt-2 text-sm leading-6 text-slate-500">Start with the paper-trading workspace.</p>{error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">{error}</div>}<form onSubmit={handleSubmit} className="mt-6 space-y-4"><div><label htmlFor="full-name" className="label">Full name</label><input id="full-name" autoComplete="name" className="input-base" value={form.fullName} onChange={(event) => update('fullName', event.target.value)} /></div><div><label htmlFor="registration-email" className="label">Email address</label><input id="registration-email" type="email" autoComplete="email" className="input-base" value={form.email} onChange={(event) => update('email', event.target.value)} required /></div><div><label htmlFor="registration-password" className="label">Password</label><input id="registration-password" type="password" autoComplete="new-password" className="input-base" value={form.password} onChange={(event) => update('password', event.target.value)} required /><p className="mt-1.5 text-xs leading-5 text-slate-500">Use 8+ characters with an uppercase letter, number, and special character.</p></div><div><label htmlFor="confirm-password" className="label">Confirm password</label><input id="confirm-password" type="password" autoComplete="new-password" className="input-base" value={form.confirmPassword} onChange={(event) => update('confirmPassword', event.target.value)} required /></div><button type="submit" disabled={loading} className="btn-primary mt-2 w-full">{loading ? 'Creating account…' : <>Create account <ArrowRight size={16} aria-hidden="true" /></>}</button></form><p className="mt-6 text-center text-sm text-slate-500">Already registered? <Link href="/login" className="font-semibold text-[#2563eb] hover:text-[#1d4ed8]">Sign in</Link></p></div></section></main>
  )
}
