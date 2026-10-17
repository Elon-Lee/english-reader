-- Free AI analysis limits are enforced per Asia/Shanghai calendar day by the
-- membership service. Keep the plan snapshot aligned for new contexts/admin UI.
UPDATE plan_versions
SET quotas_json = quotas_json || '{"ai_context_generations":50,"ai_grammar_generations":20}'::jsonb
WHERE id='free-v2';
