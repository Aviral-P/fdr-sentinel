import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cva, type VariantProps } from 'class-variance-authority'
import { AlertCircle, Check, LoaderCircle, X } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { cn, titleCase } from '../lib/utils'

const buttonStyles = cva('inline-flex items-center justify-center gap-2 rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50', {
  variants: {
    variant: { primary: 'bg-ink-900 text-white hover:bg-ink-800', secondary: 'border border-line bg-white text-ink-800 hover:bg-slate-50', ghost: 'text-ink-700 hover:bg-slate-100', danger: 'bg-rose-700 text-white hover:bg-rose-700/90', teal: 'bg-teal-700 text-white hover:bg-teal-700/90' },
    size: { md: 'h-10 px-4', sm: 'h-8 px-3 text-xs', icon: 'h-9 w-9' },
  }, defaultVariants: { variant: 'primary', size: 'md' },
})
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonStyles> {}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => <button ref={ref} className={cn(buttonStyles({ variant, size, className }))} {...props} />)
Button.displayName = 'Button'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => <input ref={ref} className={cn('h-9 w-full rounded-md border border-line bg-white px-3 text-sm text-ink-900 outline-none placeholder:text-slate-400 focus:border-teal-700 focus:ring-2 focus:ring-teal-700/10 disabled:bg-slate-100', className)} {...props} />)
Input.displayName = 'Input'
export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) { return <select className={cn('h-9 rounded-md border border-line bg-white px-3 text-sm text-ink-800 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-700/10', className)} {...props}>{children}</select> }
export function Card({ className, children }: { className?: string; children: ReactNode }) { return <section className={cn('rounded-md border border-line bg-white shadow-panel', className)}>{children}</section> }
export function CardTitle({ children, className }: { children: ReactNode; className?: string }) { return <h2 className={cn('text-sm font-semibold text-ink-900', className)}>{children}</h2> }
export function Badge({ children, tone = 'slate', className }: { children: ReactNode; tone?: 'slate' | 'green' | 'amber' | 'red' | 'blue' | 'purple'; className?: string }) {
  const tones = { slate: 'bg-slate-100 text-slate-700', green: 'bg-teal-100 text-teal-700', amber: 'bg-amber-100 text-amber-700', red: 'bg-rose-100 text-rose-700', blue: 'bg-blue-50 text-blue-700', purple: 'bg-violet-50 text-violet-700' }
  return <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize', tones[tone], className)}>{children}</span>
}
export function StatusBadge({ status }: { status: string }) {
  const tone = /approved|released|reviewed|resolved|satisfied/.test(status) ? 'green' : /matured|urgent|critical|rejected|discrepancy|overdue/.test(status) ? 'red' : /pending|scrutiny|clarification|open|high|medium/.test(status) ? 'amber' : 'slate'
  return <Badge tone={tone} className="rounded-sm px-2 py-0.5 text-[10px]">{titleCase(status)}</Badge>
}
function RegistryStatus({ status, category }: { status: string; category: 'lifecycle' | 'verification' | 'priority' }) {
  const styles: Record<string, string> = {
    draft: 'border-slate-300 bg-slate-50 text-slate-700', submitted: 'border-sky-200 bg-sky-50 text-sky-800',
    under_scrutiny: 'border-indigo-200 bg-indigo-50 text-indigo-800', clarification_required: 'border-amber-200 bg-amber-50 text-amber-800',
    approved: 'border-emerald-200 bg-emerald-50 text-emerald-800', rejected: 'border-rose-200 bg-rose-50 text-rose-800',
    release_pending: 'border-violet-200 bg-violet-50 text-violet-800', released: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    matured: 'border-orange-200 bg-orange-50 text-orange-800', superseded: 'border-slate-300 bg-slate-100 text-slate-700',
    not_checked: 'border-slate-300 bg-slate-50 text-slate-700', pending_review: 'border-blue-200 bg-blue-50 text-blue-800',
    discrepancy_flagged: 'border-amber-200 bg-amber-50 text-amber-800', reviewed: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    low: 'border-slate-300 bg-white text-slate-600', normal: 'border-slate-300 bg-slate-100 text-slate-700',
    high: 'border-amber-200 bg-amber-50 text-amber-800', urgent: 'border-rose-200 bg-rose-50 text-rose-800',
  }
  return <span className={cn('inline-flex items-center whitespace-nowrap rounded-sm border px-2 py-0.5 text-[10px] font-semibold leading-4', styles[status] || 'border-slate-300 bg-white text-slate-700')} data-status-category={category}>{titleCase(status)}</span>
}
export function LifecycleStatusBadge({ status }: { status: string }) { return <RegistryStatus status={status} category="lifecycle" /> }
export function VerificationStatusBadge({ status }: { status: string }) { return <RegistryStatus status={status} category="verification" /> }
export function PriorityBadge({ status }: { status: string }) { return <RegistryStatus status={status} category="priority" /> }
export function OriginBadge({ origin }: { origin: string }) {
  const label = ({ user_submitted: 'Institution submitted', extracted: 'Extracted', system_generated: 'System flagged', independently_verified: 'Officially reviewed', synthetic_demo: 'Synthetic demo' } as Record<string, string>)[origin] || titleCase(origin)
  const tone = origin === 'independently_verified' ? 'green' : origin === 'extracted' ? 'blue' : origin === 'system_generated' ? 'amber' : 'slate'
  return <Badge tone={tone}>{label}</Badge>
}
export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-5 flex flex-col justify-between gap-3 border-b border-line pb-4 sm:flex-row sm:items-end"><div>{eyebrow && <div className="mb-1.5 text-[10px] font-bold uppercase tracking-[.12em] text-teal-700">{eyebrow}</div>}<h1 className="text-[22px] font-semibold leading-7 tracking-tight text-ink-950">{title}</h1>{description && <p className="mt-1 max-w-3xl text-[13px] leading-5 text-slate-600">{description}</p>}</div>{action}</div>
}
export function DataTable({ caption, minWidth = '720px', className, children }: { caption: string; minWidth?: string; className?: string; children: ReactNode }) {
  return <div role="region" aria-label={caption} tabIndex={0} className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700"><table className={cn('w-full text-left text-xs', className)} style={{ minWidth }}><caption className="sr-only">{caption}</caption>{children}</table></div>
}
export function LoadingState({ label = 'Loading records…' }: { label?: string }) { return <div className="flex min-h-36 items-center justify-center gap-2 text-sm text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin text-teal-700" aria-hidden="true" />{label}</div> }
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-100 bg-rose-50 p-4 text-sm text-rose-700"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><div className="flex-1"><p className="font-semibold">Couldn’t load this view</p><p className="mt-1">{message}</p>{onRetry && <button onClick={onRetry} className="mt-2 underline underline-offset-2">Try again</button>}</div></div> }
export function EmptyState({ title, description, icon: Icon = Check }: { title: string; description: string; icon?: typeof Check }) { return <div className="flex min-h-44 flex-col items-center justify-center px-6 text-center"><div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-500"><Icon className="h-5 w-5" /></div><p className="text-sm font-semibold text-ink-800">{title}</p><p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">{description}</p></div> }
export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) { return <label className="block space-y-1.5"><span className="text-xs font-semibold text-ink-700">{label}</span>{children}{hint && <span className="block text-[11px] text-slate-500">{hint}</span>}</label> }
export function DividerLabel({ children }: { children: ReactNode }) { return <div className="flex items-center gap-3 py-2"><span className="h-px flex-1 bg-line" /><span className="text-[10px] font-bold uppercase tracking-[.15em] text-slate-400">{children}</span><span className="h-px flex-1 bg-line" /></div> }

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = 'Confirm', destructive = false, onConfirm }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; confirmLabel?: string; destructive?: boolean; onConfirm: () => void }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink-950/35 backdrop-blur-[2px]" /><DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-white p-6 shadow-2xl focus:outline-none"><div className="flex items-start justify-between"><div><DialogPrimitive.Title className="text-lg font-semibold text-ink-950">{title}</DialogPrimitive.Title><DialogPrimitive.Description className="mt-2 text-sm leading-6 text-slate-500">{description}</DialogPrimitive.Description></div><DialogPrimitive.Close aria-label="Close" className="rounded-md p-1 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></DialogPrimitive.Close></div><div className="mt-6 flex justify-end gap-2"><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant={destructive ? 'danger' : 'primary'} onClick={() => { onConfirm(); onOpenChange(false) }}>{confirmLabel}</Button></div></DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>
}
