CREATE TABLE vocabulary_review_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
  state_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id,request_key)
);
CREATE UNIQUE INDEX vocabulary_review_one_active ON vocabulary_review_sessions(user_id) WHERE status='active';
CREATE INDEX vocabulary_review_recent ON vocabulary_review_sessions(user_id,updated_at DESC);

CREATE TABLE vocabulary_review_answers (
  session_id TEXT NOT NULL REFERENCES vocabulary_review_sessions(id) ON DELETE CASCADE,
  step INTEGER NOT NULL,
  attempt_key TEXT NOT NULL,
  vocabulary_id BIGINT NOT NULL,
  rating TEXT NOT NULL CHECK (rating IN ('again','hard','good','easy','skip')),
  repeated BOOLEAN NOT NULL,
  hinted BOOLEAN NOT NULL,
  activity_day DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(session_id,step),
  UNIQUE(session_id,attempt_key)
);
CREATE INDEX vocabulary_review_answers_day ON vocabulary_review_answers(activity_day,session_id);
