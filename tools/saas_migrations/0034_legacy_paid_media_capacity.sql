-- Legacy paid subscriptions predate media collection capacities. Preserve their
-- existing storage, term and explicit limits while adding the missing benefits.
UPDATE plan_versions AS pv
SET quotas_json = defaults.limits || pv.quotas_json
FROM (VALUES
  ('advanced-v1', '{"video_library_capacity":20,"audio_library_capacity":50}'::jsonb),
  ('pro-v1', '{"video_library_capacity":100,"audio_library_capacity":200}'::jsonb)
) AS defaults(id, limits)
WHERE pv.id = defaults.id
  AND (NOT pv.quotas_json ? 'video_library_capacity'
    OR NOT pv.quotas_json ? 'audio_library_capacity');

-- Usage periods are snapshots: correcting the plan alone would leave current
-- periods returning zero and rejecting imports/unlocks until the next cycle.
-- Only fill absent media fields; explicit limits (including zero) remain intact.
UPDATE usage_periods AS up
SET limits_json = jsonb_strip_nulls(jsonb_build_object(
    'video_library_capacity', pv.quotas_json -> 'video_library_capacity',
    'audio_library_capacity', pv.quotas_json -> 'audio_library_capacity'
  )) || up.limits_json
FROM plan_versions AS pv
WHERE up.plan_version_id = pv.id
  AND up.period_key NOT LIKE 'ai-day:%'
  AND ((NOT up.limits_json ? 'video_library_capacity' AND pv.quotas_json ? 'video_library_capacity')
    OR (NOT up.limits_json ? 'audio_library_capacity' AND pv.quotas_json ? 'audio_library_capacity'));
