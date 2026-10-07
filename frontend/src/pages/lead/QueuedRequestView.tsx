import { Link } from 'react-router'
import { assignEvent, getQueuedRequest } from '../../lib/coordinatorLead'
import { CoordinatorPicker } from './CoordinatorPicker'
import { LeadRequestReview } from './LeadRequestReview'

/** A queued Event Request for the Coordinator Lead to review (read-only). */
export function QueuedRequestView() {
  return (
    <LeadRequestReview
      load={getQueuedRequest}
      backTo="/coordinator-lead/queue"
      backLabel="← Back to the Unassigned Queue"
      notFoundText="This request is not in the Unassigned Queue."
      actions={(event) => (
        <CoordinatorPicker
          heading="Assign to an Event Coordinator"
          label="Event Coordinator"
          confirmLabel="Assign"
          onConfirm={async (coordinatorId) => (await assignEvent(event.id, coordinatorId)).coordinator?.name ?? ''}
          doneText={(name) => `Assigned to ${name}. The request is now Under Review and has left the queue.`}
          next={<Link to="/coordinator-lead/queue">← Back to the Unassigned Queue</Link>}
        />
      )}
    />
  )
}
