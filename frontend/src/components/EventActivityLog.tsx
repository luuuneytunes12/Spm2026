import {
  EVENT_STATUS_LABELS,
  formatTimestamp,
  type ActivityEntry,
  type EventStatus,
} from '../lib/events'

function statusLabel(value: string): string {
  return EVENT_STATUS_LABELS[value as EventStatus] ?? value
}

function ActivityLine({ entry }: { entry: ActivityEntry }) {
  const isAssignment =
    entry.from_status !== null &&
    entry.from_status === entry.to_status &&
    (entry.note?.startsWith('Assigned to ') || entry.note?.startsWith('Reassigned from '))
  const timestamp = formatTimestamp(entry.created_at)

  return (
    <li className="activity-item">
      <p className="activity-change">
        {isAssignment ? (
          <strong>Assignment</strong>
        ) : entry.from_status && entry.from_status !== entry.to_status ? (
          <>
            {statusLabel(entry.from_status)} <span aria-hidden="true">→</span>{' '}
            <strong>{statusLabel(entry.to_status)}</strong>
          </>
        ) : entry.from_status === entry.to_status ? (
          <strong>Request update</strong>
        ) : (
          <strong>{statusLabel(entry.to_status)}</strong>
        )}
      </p>
      <p className="activity-meta">
        {entry.changed_by_name ?? 'Unknown user'}
        {timestamp && ` · ${timestamp}`}
      </p>
      {entry.note && <p className="activity-note">{entry.note}</p>}
    </li>
  )
}

export function EventActivityLog({
  status,
  activity,
}: {
  status: string
  activity: ActivityEntry[]
}) {
  return (
    <section className="card">
      <h2>Activity Log</h2>
      <p className="activity-meta">Current status: {statusLabel(status)}</p>
      {activity.length === 0 ? (
        <p className="page-subtitle">No activity recorded yet.</p>
      ) : (
        <ol className="activity-list" aria-label="Activity log">
          {activity.map((entry, index) => (
            <ActivityLine key={`${entry.created_at}-${entry.to_status}-${index}`} entry={entry} />
          ))}
        </ol>
      )}
    </section>
  )
}
