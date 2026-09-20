from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from inat.adapters import EmbeddingModelError
from inat.config import default_db_path
from inat.domain import (
    Application,
    ApplicationDraft,
    SearchMatch,
    SearchMode,
    Season,
)
from inat.infrastructure import Database
from inat.services import ApplicationService, VectorService, VectorUnavailableError
from inat.services.applications import UNSET


app = typer.Typer(
    no_args_is_help=True,
    help="Local-first internship application tracker.",
    pretty_exceptions_show_locals=False,
)
vectors_app = typer.Typer(help="Manage optional BGE-M3 semantic search.")
statuses_app = typer.Typer(help="List and customize application statuses.")
app.add_typer(vectors_app, name="vectors")
app.add_typer(statuses_app, name="statuses")
console = Console()


def _database(path: Path | None) -> Database:
    return Database(path or default_db_path())


def _core_service(path: Path | None) -> ApplicationService:
    service = ApplicationService(_database(path))
    service.initialize()
    return service


def _search_service(path: Path | None, mode: SearchMode) -> ApplicationService:
    database = _database(path)
    semantic = VectorService(database) if mode in {SearchMode.VECTOR, SearchMode.HYBRID} else None
    service = ApplicationService(database, semantic_search=semantic)
    service.initialize()
    return service


def _show_applications(applications: list[Application]) -> None:
    if not applications:
        console.print("No applications found.")
        return
    table = Table("ID", "Company", "Position", "Start At", "Season", "Status", "Applied")
    for item in applications:
        table.add_row(
            item.id,
            item.company,
            item.position,
            item.start_at,
            f"{item.application_season.value} {item.application_year}",
            item.status,
            item.date_applied.isoformat(),
        )
    console.print(table)


def _show_matches(matches: list[SearchMatch]) -> None:
    if not matches:
        console.print("No matching applications found.")
        return
    table = Table("ID", "Company", "Position", "Status", "Match", "Score")
    for match in matches:
        table.add_row(
            match.application.id,
            match.application.company,
            match.application.position,
            match.application.status,
            match.reason,
            f"{match.score:.1f}",
        )
    console.print(table)


@app.command("init")
def initialize(
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Create or migrate the local database."""
    service = _core_service(db)
    console.print(f"Database ready: [bold]{service.database.path}[/bold]")


@statuses_app.command("list")
def list_statuses(
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """List built-in and custom application statuses."""
    table = Table("Status", "Type")
    for name, is_builtin in _core_service(db).statuses():
        table.add_row(name, "built-in" if is_builtin else "custom")
    console.print(table)


@statuses_app.command("add")
def add_status(
    name: Annotated[str, typer.Argument(help="Custom status name.")],
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Add a custom application status."""
    try:
        created = _core_service(db).add_status(name)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Added custom status [bold]{created}[/bold].")


@statuses_app.command("rename")
def rename_status(
    current: Annotated[str, typer.Argument(help="Current custom status name.")],
    new: Annotated[str, typer.Argument(help="New custom status name.")],
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Rename a custom status and update applications using it."""
    try:
        renamed = _core_service(db).rename_status(current, new)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Renamed custom status to [bold]{renamed}[/bold].")


@statuses_app.command("remove")
def remove_status(
    name: Annotated[str, typer.Argument(help="Unused custom status name.")],
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Remove a custom status that no application currently uses."""
    try:
        removed = _core_service(db).remove_status(name)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Removed custom status [bold]{removed}[/bold].")


@app.command("add")
def add_application(
    company: Annotated[str, typer.Argument(help="Company name.")],
    position: Annotated[str, typer.Argument(help="Position title.")],
    url: Annotated[str, typer.Argument(help="Career/application page URL.")],
    start_at: Annotated[
        str | None,
        typer.Option(
            "--start-at",
            help="Start date (YYYY-MM-DD or N/A); defaults to next summer.",
        ),
    ] = None,
    status: Annotated[str, typer.Option(help="Initial built-in or custom status.")] = "applied",
    company_size_type: Annotated[
        str | None,
        typer.Option(
            "--company-size-type",
            "--company-size",
            help="Optional company size/type.",
        ),
    ] = None,
    notes: Annotated[str | None, typer.Option(help="Optional notes.")] = None,
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Add an application without running similarity or vector search."""
    try:
        result = _core_service(db).add(
            ApplicationDraft(
                company=company,
                position=position,
                start_at=start_at,
                company_size_type=company_size_type,
                career_page_url=url,
                notes=notes,
            ),
            status=status,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(
        f"Added [bold]{result.id}[/bold]: {result.company} — {result.position} "
        f"({result.application_season.value} {result.application_year})."
    )


@app.command("update")
def update_application(
    application_id: Annotated[str, typer.Argument(help="Eight-character application ID.")],
    status: Annotated[str | None, typer.Option(help="New built-in or custom status.")] = None,
    company_size_type: Annotated[
        str | None,
        typer.Option(
            "--company-size-type",
            "--company-size",
            help="Set company size/type; pass an empty value to clear.",
        ),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option(help="Set notes; pass an empty value to clear."),
    ] = None,
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Update status and automatically timestamp the change."""
    service = _core_service(db)
    if status is None:
        choices = [name for name, _ in service.statuses()]
        selected = Prompt.ask(
            "Status",
            choices=choices,
            default="applied",
        )
        status = selected
    try:
        result = service.update_status(
            application_id,
            status,
            company_size_type=company_size_type if company_size_type is not None else UNSET,
            notes=notes if notes is not None else UNSET,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(
        f"Updated [bold]{result.application_id}[/bold]: "
        f"{result.old_status} → {result.new_status} at "
        f"{result.changed_at.isoformat()}."
    )


@app.command("list")
def list_applications(
    status: Annotated[str | None, typer.Option(help="Filter by status.")] = None,
    year: Annotated[int | None, typer.Option(help="Filter by application year.")] = None,
    season: Annotated[Season | None, typer.Option(help="Filter by application season.")] = None,
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """List applications, ordered by start date."""
    _show_applications(_core_service(db).list(status=status, year=year, season=season))


@app.command("ls", hidden=True)
def list_applications_alias(
    status: Annotated[str | None, typer.Option(help="Filter by status.")] = None,
    year: Annotated[int | None, typer.Option(help="Filter by application year.")] = None,
    season: Annotated[Season | None, typer.Option(help="Filter by application season.")] = None,
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    list_applications(status=status, year=year, season=season, db=db)


@app.command("show")
def show_application(
    application_id: Annotated[str, typer.Argument(help="Eight-character application ID.")],
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Show every stored field for one application."""
    try:
        item = _core_service(db).get(application_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    table = Table(show_header=False, box=None)
    rows = (
        ("ID", item.id),
        ("Company", item.company),
        ("Position", item.position),
        ("Start at", item.start_at),
        ("Date applied", item.date_applied.isoformat()),
        ("Status", item.status),
        ("Status updated", item.status_updated_at.isoformat()),
        ("Application season", item.application_season.value),
        ("Application year", str(item.application_year)),
        ("Company size/type", item.company_size_type or ""),
        ("Career/application page", item.career_page_url),
        ("Notes", item.notes or ""),
    )
    for label, value in rows:
        table.add_row(f"[bold]{label}[/bold]", value)
    console.print(table)


@app.command("search")
def search_applications(
    query: Annotated[str, typer.Argument(help="Words or meaning to search for.")],
    mode: Annotated[
        SearchMode,
        typer.Option(help="text avoids vectors; vector and hybrid use the vector index."),
    ] = SearchMode.HYBRID,
    status: Annotated[str | None, typer.Option(help="Filter by status.")] = None,
    year: Annotated[int | None, typer.Option(help="Filter by application year.")] = None,
    season: Annotated[Season | None, typer.Option(help="Filter by application season.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Search by text, vector similarity, or reciprocal-rank hybrid matching."""
    try:
        matches = _search_service(db, mode).search(
            query,
            mode=mode,
            status=status,
            year=year,
            season=season,
            limit=limit,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    _show_matches(matches)


@app.command("history")
def show_history(
    application_id: Annotated[str, typer.Argument(help="Eight-character application ID.")],
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Show status changes for one application."""
    try:
        changes = _core_service(db).history(application_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    table = Table("Changed at", "From", "To")
    for change in changes:
        table.add_row(
            change.changed_at.isoformat(),
            change.old_status if change.old_status is not None else "—",
            change.new_status,
        )
    console.print(table)


@vectors_app.command("status")
def vectors_status(
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Show optional model, extension, and index status."""
    result = VectorService(_database(db)).status()
    table = Table("Component", "Status")
    table.add_row("Model", result.model_name)
    table.add_row("Model cache", "ready" if result.model_cached else "not downloaded")
    table.add_row("sqlite-vec", "ready" if result.extension_available else "unavailable")
    table.add_row("Indexed", f"{result.indexed_applications}/{result.total_applications}")
    table.add_row("Stale", str(result.stale_applications))
    console.print(table)


@vectors_app.command("setup")
def vectors_setup(
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Download BGE-M3 when needed and initialize vector storage."""
    service = VectorService(_database(db))
    action = "Loading cached" if service.embedder.is_cached else "Downloading"
    console.print(f"{action} [bold]{service.embedder.model_name}[/bold]...")
    try:
        dimensions = service.setup()
    except (EmbeddingModelError, VectorUnavailableError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Model ready ({dimensions} dimensions). Run `inat vectors rebuild`.")


@vectors_app.command("rebuild")
def vectors_rebuild(
    db: Annotated[Path | None, typer.Option(help="Database path.")] = None,
) -> None:
    """Embed only new or changed applications."""
    try:
        result = VectorService(_database(db)).rebuild(show_progress=True)
    except (EmbeddingModelError, VectorUnavailableError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    console.print(
        f"Indexed {result.embedded_applications}; skipped "
        f"{result.skipped_applications}; {result.total_applications} total."
    )


def main() -> None:
    app()
