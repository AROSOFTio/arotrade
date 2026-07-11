import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

type EmptyStateProps = {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
        <Icon size={22} aria-hidden="true" />
      </div>
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
