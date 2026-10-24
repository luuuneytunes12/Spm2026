import type { ClarificationOut } from '../lib/clarifications'
import { formatTimestamp } from '../lib/events'

/** The clarification messages on an event, oldest first, each with its
 *  author and time. Renders nothing when there are none. */
export function ClarificationThread({ items }: { items: ClarificationOut[] }) {
  if (items.length === 0) return null
  return (
    <ol className="activity-list" aria-label="Clarification thread">
      {items.map((c) => (
        <li key={c.id} className="activity-item">
          <p className="activity-change">
            <strong>{c.kind === 'request' ? 'Clarification request' : 'Reply'}</strong>
          </p>
          <p className="activity-meta">
            {c.author_name ?? 'Unknown user'}
            {` · ${formatTimestamp(c.created_at)}`}
          </p>
          <p className="activity-note" style={{ whiteSpace: 'pre-wrap' }}>
            {c.message}
          </p>
        </li>
      ))}
    </ol>
  )
}
