// Mirror of backend/app/core/communication.py -- keep string values
// byte-identical.

export const CommunicationPreference = {
  EMAIL: 'email',
  SMS: 'sms',
  PHONE_CALL: 'phone_call',
} as const
export type CommunicationPreference =
  (typeof CommunicationPreference)[keyof typeof CommunicationPreference]

export const COMMUNICATION_PREFERENCE_LABELS: Record<CommunicationPreference, string> = {
  [CommunicationPreference.EMAIL]: 'Email',
  [CommunicationPreference.SMS]: 'SMS',
  [CommunicationPreference.PHONE_CALL]: 'Phone call',
}
