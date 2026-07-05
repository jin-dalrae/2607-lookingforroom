CREATE TABLE IF NOT EXISTS applications (
  listing_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'draft',
  notes TEXT DEFAULT '',
  channel TEXT,
  sent_at TEXT,
  replied_at TEXT,
  toured_at TEXT,
  rejected_at TEXT,
  skipped_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listing_flags (
  listing_id TEXT PRIMARY KEY,
  liked INTEGER NOT NULL DEFAULT 0,
  is_scam_likely INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);