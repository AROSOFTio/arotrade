'use client'

import { useMemo, useState } from 'react'
import { Calculator, Info } from 'lucide-react'

import { PageHeader } from '../../components/page-header'

const pairPresets = [
  { label: 'Forex — standard pair (pip 0.0001)', pipSize: 0.0001, pipValuePerLot: 10 },
  { label: 'Forex — JPY pair (pip 0.01)', pipSize: 0.01, pipValuePerLot: 9.1 },
  { label: 'Gold (XAUUSD, pip 0.1)', pipSize: 0.1, pipValuePerLot: 10 },
  { label: 'Custom', pipSize: 0.0001, pipValuePerLot: 10 },
]

function parse(value: string): number {
  const n = parseFloat(value)
  return Number.isFinite(n) ? n : 0
}

export default function PositionSizePage() {
  const [balance, setBalance] = useState('10000')
  const [riskPercent, setRiskPercent] = useState('1')
  const [entry, setEntry] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [presetIndex, setPresetIndex] = useState(0)
  const [pipSize, setPipSize] = useState(String(pairPresets[0].pipSize))
  const [pipValue, setPipValue] = useState(String(pairPresets[0].pipValuePerLot))

  const isCustom = presetIndex === pairPresets.length - 1

  const outcome = useMemo(() => {
    const bal = parse(balance)
    const risk = parse(riskPercent)
    const entryPrice = parse(entry)
    const stopPrice = parse(stopLoss)
    const pip = parse(pipSize)
    const valuePerLot = parse(pipValue)

    if (bal <= 0 || risk <= 0 || entryPrice <= 0 || stopPrice <= 0 || pip <= 0 || valuePerLot <= 0 || entryPrice === stopPrice) {
      return null
    }

    const riskAmount = (bal * risk) / 100
    const stopPips = Math.abs(entryPrice - stopPrice) / pip
    const lots = riskAmount / (stopPips * valuePerLot)
    return {
      riskAmount,
      stopPips,
      lots,
      miniLots: lots * 10,
      microLots: lots * 100,
    }
  }, [balance, riskPercent, entry, stopLoss, pipSize, pipValue])

  const applyPreset = (index: number) => {
    setPresetIndex(index)
    const preset = pairPresets[index]
    setPipSize(String(preset.pipSize))
    setPipValue(String(preset.pipValuePerLot))
  }

  return (
    <>
      <PageHeader
        eyebrow="Tools"
        title="Position size calculator"
        description="Size every trade from the risk you can afford to lose — not from a lot size you are used to."
      />
      <section className="grid gap-6 lg:grid-cols-[420px_minmax(0,1fr)]">
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Calculator size={20} aria-hidden="true" /></span>
            <h2 className="text-sm font-semibold text-slate-900">Trade inputs</h2>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="balance" className="label">Account balance ($)</label>
              <input id="balance" type="number" min="0" step="any" inputMode="decimal" className="input-base" value={balance} onChange={(e) => setBalance(e.target.value)} />
            </div>
            <div>
              <label htmlFor="risk" className="label">Risk per trade (%)</label>
              <input id="risk" type="number" min="0" max="100" step="any" inputMode="decimal" className="input-base" value={riskPercent} onChange={(e) => setRiskPercent(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="entry" className="label">Entry price</label>
              <input id="entry" type="number" min="0" step="any" inputMode="decimal" className="input-base" value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="1.0842" />
            </div>
            <div>
              <label htmlFor="stop" className="label">Stop-loss price</label>
              <input id="stop" type="number" min="0" step="any" inputMode="decimal" className="input-base" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} placeholder="1.0810" />
            </div>
          </div>

          <div>
            <label htmlFor="preset" className="label">Instrument</label>
            <select id="preset" className="input-base" value={presetIndex} onChange={(e) => applyPreset(Number(e.target.value))}>
              {pairPresets.map((preset, index) => <option key={preset.label} value={index}>{preset.label}</option>)}
            </select>
          </div>

          {isCustom && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="pip-size" className="label">Pip size</label>
                <input id="pip-size" type="number" min="0" step="any" inputMode="decimal" className="input-base" value={pipSize} onChange={(e) => setPipSize(e.target.value)} />
              </div>
              <div>
                <label htmlFor="pip-value" className="label">Pip value / 1.00 lot ($)</label>
                <input id="pip-value" type="number" min="0" step="any" inputMode="decimal" className="input-base" value={pipValue} onChange={(e) => setPipValue(e.target.value)} />
              </div>
            </div>
          )}
        </div>

        <div className="space-y-6">
          {outcome ? (
            <div className="card">
              <h2 className="text-sm font-semibold text-slate-900">Recommended position</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-[#2563eb] px-4 py-5 text-white">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-blue-100">Standard lots</p>
                  <p className="mt-1 text-3xl font-bold tabular-nums">{outcome.lots.toFixed(2)}</p>
                </div>
                <div className="rounded-lg bg-slate-50 px-4 py-5">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Amount at risk</p>
                  <p className="mt-1 text-3xl font-bold tabular-nums text-slate-950">${outcome.riskAmount.toFixed(2)}</p>
                </div>
              </div>
              <dl className="mt-4 divide-y divide-slate-100 text-sm">
                <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Stop distance</dt><dd className="font-semibold tabular-nums text-slate-900">{outcome.stopPips.toFixed(1)} pips</dd></div>
                <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Mini lots (0.10)</dt><dd className="font-semibold tabular-nums text-slate-900">{outcome.miniLots.toFixed(1)}</dd></div>
                <div className="flex justify-between gap-4 py-3"><dt className="text-slate-500">Micro lots (0.01)</dt><dd className="font-semibold tabular-nums text-slate-900">{outcome.microLots.toFixed(0)}</dd></div>
              </dl>
            </div>
          ) : (
            <div className="card flex min-h-40 flex-col items-center justify-center gap-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-[#2563eb]"><Calculator size={24} aria-hidden="true" /></span>
              <p className="max-w-sm text-sm leading-6 text-slate-500">Fill in balance, risk %, entry and stop-loss to get the exact lot size for your risk.</p>
            </div>
          )}

          <div className="card flex gap-3">
            <Info size={18} className="mt-0.5 shrink-0 text-[#2563eb]" aria-hidden="true" />
            <p className="text-sm leading-6 text-slate-600">
              Pip value varies by account currency and current exchange rates — the presets assume a USD account.
              For JPY pairs and metals, confirm the per-lot pip value with your broker before trading.
            </p>
          </div>
        </div>
      </section>
    </>
  )
}
