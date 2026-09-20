CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 8),
    company TEXT NOT NULL CHECK (length(trim(company)) > 0),
    position TEXT NOT NULL CHECK (length(trim(position)) > 0),
    deadline TEXT NOT NULL,
    start_at TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (length(trim(platform)) > 0),
    date_applied TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('planned', 'applied', 'assessment', 'interviewing',
                   'offer', 'rejected', 'withdrawn')
    ),
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

CREATE TABLE status_history (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE INDEX applications_company_idx ON applications(company);
CREATE INDEX applications_status_idx ON applications(status);
CREATE INDEX applications_season_idx
    ON applications(application_year, application_season);
CREATE INDEX status_history_application_idx
    ON status_history(application_id, changed_at);

PRAGMA user_version = 1;

