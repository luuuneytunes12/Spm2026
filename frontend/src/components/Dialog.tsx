import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

interface Props {
  title: string
  /** While something is being saved the dialog cannot be dismissed. */
  busy?: boolean
  onClose: () => void
  children: ReactNode
}

/** A modal dialog: a named region over the page that traps nothing but is
 *  dismissed by Escape or a click outside, and gives focus back to whatever
 *  opened it. Shared by the confirmations that cannot be undone. */
export function Dialog({ title, busy = false, onClose, children }: Props) {
  const titleId = useId()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Return focus to whatever opened the dialog once it closes.
    const opener = document.activeElement as HTMLElement | null
    ref.current?.focus()
    return () => opener?.focus()
  }, [])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [busy, onClose])

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        className="modal card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  )
}
