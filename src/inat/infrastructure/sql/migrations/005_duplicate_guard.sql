CREATE TRIGGER prevent_duplicate_application_insert
BEFORE INSERT ON applications
WHEN EXISTS (
    SELECT 1
    FROM applications AS existing
    WHERE existing.company = NEW.company
      AND existing.position = NEW.position
      AND existing.career_page_url = NEW.career_page_url
      AND existing.application_year = NEW.application_year
      AND existing.application_season = NEW.application_season
)
BEGIN
    SELECT RAISE(ABORT, 'duplicate application');
END;

CREATE TRIGGER prevent_duplicate_application_update
BEFORE UPDATE OF company, position, career_page_url,
                 application_year, application_season ON applications
WHEN EXISTS (
    SELECT 1
    FROM applications AS existing
    WHERE existing.id != NEW.id
      AND existing.company = NEW.company
      AND existing.position = NEW.position
      AND existing.career_page_url = NEW.career_page_url
      AND existing.application_year = NEW.application_year
      AND existing.application_season = NEW.application_season
)
BEGIN
    SELECT RAISE(ABORT, 'duplicate application');
END;

PRAGMA user_version = 5;

