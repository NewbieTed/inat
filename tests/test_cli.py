import re
import sqlite3

from typer.testing import CliRunner

from inat.presentation.cli import app


runner = CliRunner()


def add_args(database):
    return [
        "add",
        "Acme",
        "Software Engineering Intern",
        "https://example.com/jobs/123",
        "--start-at",
        "2027-06-01",
        "--db",
        str(database),
    ]


def test_add_list_update_and_show(tmp_path):
    database = tmp_path / "inat.db"
    added = runner.invoke(app, add_args(database))

    assert added.exit_code == 0
    application_id = re.search(r"Added ([A-Z0-9]{8})", added.output).group(1)

    listed = runner.invoke(app, ["list", "--db", str(database)])
    assert listed.exit_code == 0
    assert application_id in listed.output
    assert "summer" in listed.output

    updated = runner.invoke(
        app,
        [
            "update",
            application_id,
            "--status",
            "interview",
            "--db",
            str(database),
        ],
    )
    assert updated.exit_code == 0
    assert "applied → interview" in updated.output

    shown = runner.invoke(app, ["show", application_id, "--db", str(database)])
    assert shown.exit_code == 0
    assert "Date applied" in shown.output
    assert "Status updated" in shown.output
    assert "interview" in shown.output


def test_text_search_is_available_without_vector_dependencies(tmp_path):
    database = tmp_path / "inat.db"
    assert runner.invoke(app, add_args(database)).exit_code == 0

    result = runner.invoke(
        app,
        ["search", "Acme", "--mode", "text", "--db", str(database)],
    )

    assert result.exit_code == 0
    assert "Acme" in result.output
    assert "exact" in result.output


def test_default_hybrid_search_falls_back_to_text_without_vectors(tmp_path):
    database = tmp_path / "inat.db"
    assert runner.invoke(app, add_args(database)).exit_code == 0

    result = runner.invoke(app, ["search", "Acme", "--db", str(database)])

    assert result.exit_code == 0
    assert "Acme" in result.output


def test_search_can_filter_by_status_without_query(tmp_path):
    database = tmp_path / "inat.db"
    assert runner.invoke(app, add_args(database)).exit_code == 0

    result = runner.invoke(
        app,
        ["search", "--status", "applied", "--db", str(database)],
    )

    assert result.exit_code == 0
    assert "Acme" in result.output
    assert "filter" in result.output


def test_search_can_filter_by_season_without_query(tmp_path):
    database = tmp_path / "inat.db"
    assert runner.invoke(app, add_args(database)).exit_code == 0

    result = runner.invoke(
        app,
        [
            "search",
            "--season",
            "summer",
            "--year",
            "2027",
            "--db",
            str(database),
        ],
    )

    assert result.exit_code == 0
    assert "Acme" in result.output


def test_search_without_query_or_filter_uses_current_application_year(tmp_path):
    result = runner.invoke(app, ["search", "--db", str(tmp_path / "inat.db")])

    assert result.exit_code == 0
    assert "No matching applications found" in result.output


def test_search_year_all_disables_current_year_default(tmp_path):
    database = tmp_path / "inat.db"
    added = runner.invoke(app, add_args(database))
    application_id = re.search(r"Added ([A-Z0-9]{8})", added.output).group(1)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE applications SET application_year = 2028 WHERE public_id = ?",
            (application_id,),
        )

    default_year = runner.invoke(app, ["search", "--db", str(database)])
    all_years = runner.invoke(
        app, ["search", "--year", "all", "--db", str(database)]
    )
    explicit_year = runner.invoke(
        app, ["search", "--year", "2028", "--db", str(database)]
    )

    assert "No matching applications found" in default_year.output
    assert application_id in all_years.output
    assert application_id in explicit_year.output


def test_search_rejects_invalid_year_value(tmp_path):
    result = runner.invoke(
        app,
        ["search", "--year", "recent", "--db", str(tmp_path / "inat.db")],
    )

    assert result.exit_code != 0
    assert "four-digit year or 'all'" in result.output


def test_search_results_are_paginated_without_result_limit(tmp_path):
    database = tmp_path / "inat.db"
    for index in range(25):
        args = add_args(database)
        args[2] = f"Intern {index:02d}"
        args[3] = f"https://example.com/jobs/{index}"
        assert runner.invoke(app, args).exit_code == 0

    result = runner.invoke(
        app,
        [
            "search",
            "--status",
            "applied",
            "--page",
            "2",
            "--page-size",
            "10",
            "--db",
            str(database),
        ],
    )

    assert result.exit_code == 0
    assert "Page 2/3" in result.output
    assert "25 matches" in result.output


def test_search_stops_and_reports_overly_broad_scope(tmp_path, monkeypatch):
    database = tmp_path / "inat.db"
    for index in range(3):
        args = add_args(database)
        args[2] = f"Intern {index}"
        args[3] = f"https://example.com/jobs/{index}"
        assert runner.invoke(app, args).exit_code == 0
    monkeypatch.setattr("inat.presentation.cli.MAX_SEARCH_CANDIDATES", 2)

    result = runner.invoke(
        app,
        ["search", "Intern", "--mode", "text", "--db", str(database)],
    )

    assert result.exit_code == 1
    assert "Search scope contains 3 applications" in result.output
    assert "Refine it" in result.output


def test_custom_status_cli_workflow(tmp_path):
    database = tmp_path / "inat.db"
    created = runner.invoke(
        app,
        ["statuses", "add", "phone screen", "--db", str(database)],
    )
    assert created.exit_code == 0

    args = add_args(database)
    args.extend(["--status", "phone screen"])
    added = runner.invoke(app, args)
    listed = runner.invoke(app, ["statuses", "list", "--db", str(database)])

    assert added.exit_code == 0
    assert listed.exit_code == 0
    assert "phone screen" in listed.output
    assert "custom" in listed.output


def test_add_rejects_non_iso_date(tmp_path):
    args = add_args(tmp_path / "inat.db")
    args[args.index("2027-06-01")] = "June 1"

    result = runner.invoke(app, args)

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output


def test_add_accepts_date_applied_in_mm_dd_yyyy_format(tmp_path):
    database = tmp_path / "inat.db"
    args = add_args(database)
    args.extend(["--date-applied", "08/31/2026"])

    added = runner.invoke(app, args)
    application_id = re.search(r"Added ([A-Z0-9]{8})", added.output).group(1)
    shown = runner.invoke(app, ["show", application_id, "--db", str(database)])

    assert added.exit_code == 0
    assert shown.exit_code == 0
    assert "2026-08-31" in shown.output


def test_add_rejects_other_date_applied_formats(tmp_path):
    args = add_args(tmp_path / "inat.db")
    args.extend(["--date-applied", "2026-08-31"])

    result = runner.invoke(app, args)

    assert result.exit_code != 0
    assert "MM/DD/YYYY" in result.output


def test_add_rejects_exact_duplicate_and_prints_existing_id(tmp_path):
    database = tmp_path / "inat.db"
    first = runner.invoke(app, add_args(database))
    application_id = re.search(r"Added ([A-Z0-9]{8})", first.output).group(1)

    duplicate = runner.invoke(app, add_args(database))

    assert first.exit_code == 0
    assert duplicate.exit_code == 1
    assert "Duplicate application" in duplicate.output
    assert application_id in duplicate.output


def test_remove_by_id_with_yes_flag(tmp_path):
    database = tmp_path / "inat.db"
    added = runner.invoke(app, add_args(database))
    application_id = re.search(r"Added ([A-Z0-9]{8})", added.output).group(1)

    removed = runner.invoke(
        app, ["remove", application_id, "--yes", "--db", str(database)]
    )
    listed = runner.invoke(app, ["list", "--db", str(database)])

    assert removed.exit_code == 0
    assert f"Removed {application_id}" in removed.output
    assert "No applications found" in listed.output


def test_remove_confirmation_can_cancel(tmp_path):
    database = tmp_path / "inat.db"
    added = runner.invoke(app, add_args(database))
    application_id = re.search(r"Added ([A-Z0-9]{8})", added.output).group(1)

    cancelled = runner.invoke(
        app,
        ["remove", application_id, "--db", str(database)],
        input="n\n",
    )
    shown = runner.invoke(app, ["show", application_id, "--db", str(database)])

    assert cancelled.exit_code != 0
    assert shown.exit_code == 0
