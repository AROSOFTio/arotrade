type StatusBadgeProps = {
  value: string
}

const styles: Record<string, string> = {
  open: 'border-blue-200 bg-blue-50 text-blue-700',
  approved: 'border-blue-200 bg-blue-50 text-blue-700',
  pending: 'border-amber-200 bg-amber-50 text-amber-700',
  executed_demo: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  closed: 'border-slate-200 bg-slate-100 text-slate-700',
  rejected: 'border-red-200 bg-red-50 text-red-700',
  cancelled: 'border-red-200 bg-red-50 text-red-700',
  filled: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  inactive: 'border-slate-200 bg-slate-100 text-slate-600',
  active: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  win: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  loss: 'border-red-200 bg-red-50 text-red-700',
  breakeven: 'border-slate-200 bg-slate-100 text-slate-700',
}

export function StatusBadge({ value }: StatusBadgeProps) {
  const normalized = value.toLowerCase()
  const label = normalized.replace(/_/g, ' ')
  return (
    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-semibold capitalize ${styles[normalized] || 'border-slate-200 bg-slate-50 text-slate-600'}`}>
      {label}
    </span>
  )
}
