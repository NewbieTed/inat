import re

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
