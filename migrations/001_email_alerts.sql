-- Run once on existing Postgres databases (SQLModel create_all won't add columns).
ALTER TABLE hackathon ADD COLUMN IF NOT EXISTS format_type VARCHAR DEFAULT 'in_person';
ALTER TABLE subscriber ADD COLUMN IF NOT EXISTS region VARCHAR DEFAULT 'all';
ALTER TABLE subscriber ADD COLUMN IF NOT EXISTS in_person_only BOOLEAN DEFAULT FALSE;
