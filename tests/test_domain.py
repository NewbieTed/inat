from datetime import date

from inat.domain import Season, default_application_season


def test_upcoming_summer_uses_current_year_before_june():
    assert default_application_season(date(2027, 3, 15)) == (2027, Season.SUMMER)
    assert default_application_season(date(2027, 5, 31)) == (2027, Season.SUMMER)


def test_upcoming_summer_uses_next_year_beginning_june_first():
    assert default_application_season(date(2027, 6, 1)) == (2028, Season.SUMMER)
    assert default_application_season(date(2027, 12, 31)) == (2028, Season.SUMMER)

