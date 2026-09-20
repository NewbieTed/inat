PRAGMA foreign_keys = OFF;

CREATE TABLE application_statuses (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    is_builtin INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0, 1)),
    CHECK (length(trim(name)) BETWEEN 1 AND 40)
);

INSERT INTO application_statuses (name, is_builtin) VALUES
    ('applied', 1),
    ('OA', 1),
    ('interview', 1),
    ('offer', 1),
    ('rejected', 1),
    ('withdrawn', 1);

INSERT OR IGNORE INTO application_statuses (name, is_builtin)
SELECT DISTINCT
    CASE status
        WHEN 'assessment' THEN 'OA'
        WHEN 'interviewing' THEN 'interview'
        ELSE status
    END,
    0
FROM applications;

CREATE TABLE applications_v4 (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 8),
    company TEXT NOT NULL CHECK (length(trim(company)) > 0),
    position TEXT NOT NULL CHECK (length(trim(position)) > 0),
    start_at TEXT NOT NULL,
    date_applied TEXT NOT NULL,
    status TEXT NOT NULL REFERENCES application_statuses(name)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    status_updated_at TEXT NOT NULL,
    application_season TEXT NOT NULL CHECK (
        application_season IN ('winter', 'spring', 'summer', 'fall')
    ),
    application_year INTEGER NOT NULL CHECK (application_year BETWEEN 1900 AND 9999),
    company_size_type TEXT,
    career_page_url TEXT NOT NULL CHECK (length(trim(career_page_url)) > 0),
    notes TEXT,
    search_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO applications_v4 (
    id, public_id, company, position, start_at, date_applied, status,
    status_updated_at, application_season, application_year,
    company_size_type, career_page_url, notes, search_text, created_at, updated_at
)
SELECT
    id, public_id, company, position, start_at, date_applied,
    CASE status
        WHEN 'assessment' THEN 'OA'
        WHEN 'interviewing' THEN 'interview'
        ELSE status
    END,
    status_updated_at, application_season, application_year,
    company_size_type, career_page_url, notes, search_text, created_at, updated_at
FROM applications;

DROP TABLE applications;
ALTER TABLE applications_v4 RENAME TO applications;

CREATE INDEX applications_company_idx ON applications(company);
CREATE INDEX applications_status_idx ON applications(status);
CREATE INDEX applications_season_idx
    ON applications(application_year, application_season);

UPDATE status_history SET old_status = 'OA' WHERE old_status = 'assessment';
UPDATE status_history SET new_status = 'OA' WHERE new_status = 'assessment';
UPDATE status_history SET old_status = 'interview' WHERE old_status = 'interviewing';
UPDATE status_history SET new_status = 'interview' WHERE new_status = 'interviewing';

PRAGMA user_version = 4;
PRAGMA foreign_keys = ON;

