-- Phase 2's initial free-period creation could normalize the bootstrap admin
-- to free-v1 before a subscription existed. Restore the explicitly intended
-- local administrator entitlement once, without affecting ordinary members.
UPDATE users u SET plan_version='pro-v1',updated_at=NOW()
WHERE EXISTS(SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=u.id AND r.name='admin')
  AND NOT EXISTS(SELECT 1 FROM subscriptions s WHERE s.user_id=u.id);

INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note,created_at,updated_at)
SELECT 'bootstrap-pro-restored-' || u.id,u.id,'pro-v1','active',u.created_at,u.created_at + INTERVAL '3650 days','migrated local administrator entitlement',NOW(),NOW()
FROM users u
JOIN user_roles ur ON ur.user_id=u.id
JOIN roles r ON r.id=ur.role_id AND r.name='admin'
WHERE u.plan_version='pro-v1'
  AND NOT EXISTS(SELECT 1 FROM subscriptions s WHERE s.user_id=u.id);
