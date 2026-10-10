-- Preserve the original local administrator's intended Pro entitlement after
-- the Phase 2 subscription model becomes authoritative.  This is a one-time
-- migration record, not a recurring product rule.
INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note,created_at,updated_at)
SELECT 'bootstrap-pro-' || u.id,u.id,'pro-v1','active',u.created_at,u.created_at + INTERVAL '3650 days','migrated local administrator entitlement',NOW(),NOW()
FROM users u
JOIN user_roles ur ON ur.user_id=u.id
JOIN roles r ON r.id=ur.role_id AND r.name='admin'
WHERE u.plan_version='pro-v1'
  AND NOT EXISTS(SELECT 1 FROM subscriptions s WHERE s.user_id=u.id);
