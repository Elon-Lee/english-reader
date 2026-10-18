export const MEMBERSHIP_LIMIT_EVENT = 'shiyue:membership-limit'

export function handleMembershipLimit(error, { onClose, onContinue } = {}) {
  if (!['media_capacity_exceeded', 'quota_exceeded', 'library_capacity_exceeded'].includes(error?.code)) return false
  onClose?.()
  window.dispatchEvent(new CustomEvent(MEMBERSHIP_LIMIT_EVENT, { detail: { message: error.message, onContinue } }))
  return true
}
