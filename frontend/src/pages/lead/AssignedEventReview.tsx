import { Link } from 'react-router'
import { getAssignedEventForLead, reassignEvent } from '../../lib/coordinatorLead'
import { CoordinatorPicker } from './CoordinatorPicker'
import { LeadRequestReview } from './LeadRequestReview'

/** An active, assigned Event for the Coordinator Lead to review, with the
 *  option to move it to another Coordinator. The Event's own details are
 *  read-only. */
export function AssignedEventReview() {
  return (
    <LeadRequestReview
      load={getAssignedEventForLead}
      backTo="/coordinator-lead/assignments"
      backLabel="← Back to Coordinator Assignments"
      notFoundText="This Event is not an active Coordinator assignment."
      actions={(event) => (
        <CoordinatorPicker
          heading="Reassign to another Event Coordinator"
          label="New Event Coordinator"
          confirmLabel="Reassign"
          excludeId={event.coordinator_id}
          onConfirm={async (coordinatorId) => (await reassignEvent(event.id, coordinatorId)).coordinator?.name ?? ''}
          doneText={(name) => `Reassigned to ${name}. The status and history are unchanged.`}
          next={<Link to="/coordinator-lead/assignments">← Back to Coordinator Assignments</Link>}
        />
      )}
    />
  )
}
