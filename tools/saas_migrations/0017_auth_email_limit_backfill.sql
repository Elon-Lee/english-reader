-- Existing successful invitation uses each produced one verification email.
-- Carry that history into the new lifetime cap without ever reducing a newer
-- counter value.

UPDATE invitations
SET verification_email_count = GREATEST(verification_email_count, LEAST(3, used_count));
