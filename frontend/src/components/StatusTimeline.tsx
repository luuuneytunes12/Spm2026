import {
  EVENT_STATUS_BRANCH_TONE,
  EVENT_STATUS_DESCRIPTIONS,
  EVENT_STATUS_LABELS,
  EVENT_STATUS_PIPELINE,
} from '../lib/events'
import type { EventStatus } from '../lib/events'

/** The only part of an activity entry the timeline reads. Newest first, as
 *  every event view receives it. */
export interface TimelineActivity {
  from_status: string | null
}

/** Where on the pipeline the event has actually reached, or -1 if it has not
 *  entered the Coordinator-facing pipeline yet (a Draft, in the rare case
 *  one is visible here at all -- see EVENT_STATUS_PIPELINE).
 *
 *  If the current status IS a pipeline stage, that is the answer. If it is
 *  a branch (Awaiting Organiser Reply / Event Rejected / Event Cancelled), the answer comes
 *  from the event's own activity log -- the `from_status` of its most
 *  recent transition is the stage it was AT when it branched off, and a
 *  branch can leave the path from more than one stage, so this is read
 *  from what actually happened rather than assumed. */
function reachedPipelineIndex(status: EventStatus, activity: TimelineActivity[]): number {
  const own = EVENT_STATUS_PIPELINE.indexOf(status)
  if (own !== -1) return own
  const departedFrom = activity[0]?.from_status
  return departedFrom ? EVENT_STATUS_PIPELINE.indexOf(departedFrom as EventStatus) : -1
}

/** The full lifecycle a request moves through, with the event's actual
 *  progress marked on it -- not just the single word "Submitted", but where
 *  that sits between Draft and Completed.
 *
 *  A status that branches off the main path (Awaiting Organiser Reply / Event Rejected /
 *  Event Cancelled) is drawn as an extra node after the stage it departed from,
 *  rather than forced into the fixed sequence -- it isn't the 8th step of
 *  a 7-step process, it's an exit from one of the earlier steps. */
export function StatusTimeline({ status, activity }: { status: EventStatus; activity: TimelineActivity[] }) {
  const onPipeline = EVENT_STATUS_PIPELINE.includes(status)
  const reached = reachedPipelineIndex(status, activity)
  const branchTone = !onPipeline ? EVENT_STATUS_BRANCH_TONE[status] : undefined

  return (
    <div>
      <ol className="status-timeline" aria-label="Status timeline">
        {EVENT_STATUS_PIPELINE.map((step, i) => {
          const state = i < reached ? 'done' : i === reached ? (onPipeline ? 'current' : 'done') : 'upcoming'
          return (
            <li
              key={step}
              className={`status-step status-step-${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="status-step-dot" aria-hidden="true" />
              <span className="status-step-label">
                {EVENT_STATUS_LABELS[step]}
              </span>
            </li>
          )
        })}
        {branchTone && (
          <li
            className={`status-step status-step-branch status-step-branch-${branchTone}`}
            aria-current="step"
          >
            <span className="status-step-dot" aria-hidden="true" />
            <span className="status-step-label">{EVENT_STATUS_LABELS[status] ?? status}</span>
          </li>
        )}
      </ol>
      <p className="page-subtitle status-description">{EVENT_STATUS_DESCRIPTIONS[status]}</p>
    </div>
  )
}
