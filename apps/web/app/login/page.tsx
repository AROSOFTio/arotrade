'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { ArrowRight, LockKeyhole } from 'lucide-react'

import { apiRequest, errorMessage } from '../components/api'

type TokenResponse = {
  access_token: string
  refresh_token: string
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const response = await apiRequest<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      window.localStorage.setItem('access_token', response.access_token)
      window.localStorage.setItem('refresh_token', response.refresh_token)
      router.replace('/dashboard')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen bg-[#f6f7f9] px-4 py-8 sm:items-center sm:justify-center">
      <section className="mx-auto w-full max-w-md">
        <Link href="/" className="mb-8 inline-flex items-center gap-3"><img src="/logo.svg" alt="AroTrader logo" className="h-10 w-10" /><span><span className="block text-base font-bold text-slate-950">AroTrader</span><span className="block text-xs font-medium text-slate-500">by AROFi</span></span></Link>
        <div className="card"><div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><LockKeyhole size={21} aria-hidden="true" /></div><h1 className="mt-5 text-2xl font-bold text-slate-950">Sign in</h1><p className="mt-2 text-sm leading-6 text-slate-500">Open your paper-trading workspace.</p>{error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">{error}</div>}<form onSubmit={handleSubmit} className="mt-6 space-y-4"><div><label htmlFor="email" className="label">Email address</label><input id="email" type="email" autoComplete="email" className="input-base" value={email} onChange={(event) => setEmail(event.target.value)} required /></div><div><label htmlFor="password" className="label">Password</label><input id="password" type="password" autoComplete="current-password" className="input-base" value={password} onChange={(event) => setPassword(event.target.value)} required /></div><button type="submit" disabled={loading} className="btn-primary mt-2 w-full">{loading ? 'Signing in…' : <>Sign in <ArrowRight size={16} aria-hidden="true" /></>}</button></form><p className="mt-6 text-center text-sm text-slate-500">New to AroTrader? <Link href="/register" className="font-semibold text-[#2563eb] hover:text-[#1d4ed8]">Create an account</Link></p></div>
      </section>
    </main>
  )
}
