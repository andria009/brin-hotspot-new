from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

import typer

from brin_hotspot.config import Settings, get_settings
from brin_hotspot.logging_config import configure_logging

app = typer.Typer(
    add_completion=False,
    help="BRIN hotspot processing command line tools.",
)
ingest_app = typer.Typer(help="Run satellite ingestion workflows.")
admin_app = typer.Typer(help="Manage reference and administrative data.")
db_app = typer.Typer(help="Manage database schema and migrations.")
raster_app = typer.Typer(help="Manage raster metadata workflows.")
worker_app = typer.Typer(help="Run operational worker cycles.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(admin_app, name="admin")
app.add_typer(db_app, name="db")
app.add_typer(raster_app, name="raster")
app.add_typer(worker_app, name="worker")


def _bootstrap() -> Settings:
    settings = get_settings()
    configure_logging(settings)
    return settings


@app.command()
def health(
    check_database: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Check database connectivity."),
    ] = False,
) -> None:
    """Check application configuration and optional external dependencies."""
    settings = _bootstrap()
    logger = logging.getLogger(__name__)
    run_id = str(uuid4())
    logger.info(
        "health_check_started",
        extra={
            "run_id": run_id,
            "environment": settings.environment,
            "input_dir": str(settings.paths.input_dir),
            "output_dir": str(settings.paths.output_dir),
        },
    )

    settings.ensure_runtime_directories()

    if check_database:
        from brin_hotspot.db import check_database_connection

        check_database_connection(settings.hotspot_database)
        logger.info(
            "database_connection_ok",
            extra={"run_id": run_id, "database": settings.hotspot_database.name},
        )

    logger.info("health_check_completed", extra={"run_id": run_id})
    typer.echo("ok")


@app.command()
def config() -> None:
    """Print sanitized runtime configuration."""
    settings = _bootstrap()
    typer.echo(settings.sanitized_json())


@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option("--reload/--no-reload")] = False,
) -> None:
    """Serve the read-only hotspot API."""
    import uvicorn

    _bootstrap()
    uvicorn.run("brin_hotspot.api.app:app", host=host, port=port, reload=reload)


@db_app.command("migrate")
def migrate_command() -> None:
    """Apply versioned schema migrations."""
    from brin_hotspot.migrations import apply_hotspot_migrations, apply_raster_migrations

    settings = _bootstrap()
    hotspot_results = apply_hotspot_migrations(settings.hotspot_database)
    raster_results = apply_raster_migrations(settings.raster_database)
    for database_name, results in (
        ("hotspot", hotspot_results),
        ("raster", raster_results),
    ):
        for result in results:
            state = "applied" if result.applied else "skipped"
            typer.echo(f"{database_name} {state} {result.version}")


@ingest_app.command("snpp")
def ingest_snpp_command(
    input_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--input-dir",
            help=(
                "SNPP input directory. Repeat for multiple roots. "
                "Defaults to HOTSPOT_INPUT_DIR/snpp."
            ),
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Parse SNPP hotspot files, cluster detections, and write CSV outputs."""
    from brin_hotspot.ingestion.snpp import ingest_snpp

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)

    summary = ingest_snpp(
        settings,
        input_dirs=tuple(input_dirs) if input_dirs else None,
        persist=persist,
        enrich=enrich,
    )
    _echo_ingestion_summary(summary)


@ingest_app.command("noaa20")
def ingest_noaa20_command(
    input_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--input-dir",
            help=(
                "NOAA20 input directory. Repeat for multiple roots. "
                "Defaults to HOTSPOT_INPUT_DIR/noaa20."
            ),
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Parse NOAA20 hotspot files, cluster detections, and write CSV outputs."""
    from brin_hotspot.ingestion.noaa20 import ingest_noaa20

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)

    summary = ingest_noaa20(
        settings,
        input_dirs=tuple(input_dirs) if input_dirs else None,
        persist=persist,
        enrich=enrich,
    )
    _echo_ingestion_summary(summary)


@ingest_app.command("aqua")
def ingest_aqua_command(
    input_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--input-dir",
            help=(
                "AQUA MODIS input directory. Repeat for multiple roots. "
                "Defaults to HOTSPOT_INPUT_DIR/aqua."
            ),
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Parse AQUA MODIS HDF hotspot files, cluster detections, and write CSV outputs."""
    from brin_hotspot.ingestion.modis import ingest_aqua

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)

    summary = ingest_aqua(
        settings,
        input_dirs=tuple(input_dirs) if input_dirs else None,
        persist=persist,
        enrich=enrich,
    )
    _echo_ingestion_summary(summary)


@ingest_app.command("tera")
def ingest_tera_command(
    input_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--input-dir",
            help=(
                "TERA MODIS input directory. Repeat for multiple roots. "
                "Defaults to HOTSPOT_INPUT_DIR/tera."
            ),
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Parse TERA MODIS HDF hotspot files, cluster detections, and write CSV outputs."""
    from brin_hotspot.ingestion.modis import ingest_tera

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)

    summary = ingest_tera(
        settings,
        input_dirs=tuple(input_dirs) if input_dirs else None,
        persist=persist,
        enrich=enrich,
    )
    _echo_ingestion_summary(summary)


@ingest_app.command("landsat8")
def ingest_landsat8_command(
    input_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--input-dir",
            help=(
                "Landsat 8 input directory. Repeat for multiple roots. "
                "Defaults to HOTSPOT_INPUT_DIR/landsat8."
            ),
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Parse Landsat 8 firepixels text files, cluster detections, and write CSV outputs."""
    from brin_hotspot.ingestion.landsat8 import ingest_landsat8

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)

    summary = ingest_landsat8(
        settings,
        input_dirs=tuple(input_dirs) if input_dirs else None,
        persist=persist,
        enrich=enrich,
    )
    _echo_ingestion_summary(summary)


def _echo_ingestion_summary(summary) -> None:
    typer.echo(
        f"ok satellite={summary.satellite} parsed={summary.parsed_count} "
        f"enriched={summary.enriched_count} filtered={summary.filtered_count} "
        f"clusters={summary.cluster_count} persisted_clusters={summary.persisted_cluster_count} "
        f"skipped_files={len(summary.skipped_files)} run_id={summary.run_id}"
    )


@admin_app.command("runs")
def list_runs_command(
    satellite: Annotated[str | None, typer.Option("--satellite")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 20,
) -> None:
    """List recent ingestion runs."""
    from brin_hotspot.repositories.operations_repository import OperationsRepository

    settings = _bootstrap()
    rows = OperationsRepository(settings.hotspot_database).list_runs(
        satellite=satellite,
        status=status,
        limit=limit,
    )
    _echo_records(
        [
            {
                "id": row.id,
                "satellite": row.satellite,
                "status": row.status,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else "",
                "message": row.message or "",
            }
            for row in rows
        ]
    )


@admin_app.command("sources")
def list_sources_command(
    satellite: Annotated[str | None, typer.Option("--satellite")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 20,
) -> None:
    """List source-file processing status."""
    from brin_hotspot.repositories.operations_repository import OperationsRepository

    settings = _bootstrap()
    rows = OperationsRepository(settings.hotspot_database).list_source_files(
        satellite=satellite,
        status=status,
        limit=limit,
    )
    _echo_records(
        [
            {
                "satellite": row.satellite,
                "status": row.status,
                "observed_at": row.observed_at.isoformat() if row.observed_at else "",
                "path": row.path,
                "last_error": row.last_error or "",
            }
            for row in rows
        ]
    )


@admin_app.command("replay-source")
def replay_source_command(
    satellite: Annotated[str, typer.Option("--satellite")],
    path: Annotated[str, typer.Option("--path")],
) -> None:
    """Mark one source file as pending so a later ingestion run can process it again."""
    from brin_hotspot.repositories.operations_repository import OperationsRepository

    settings = _bootstrap()
    updated = OperationsRepository(settings.hotspot_database).mark_source_file_pending(
        satellite=satellite,
        path=path,
    )
    if not updated:
        typer.echo("source file not found", err=True)
        raise typer.Exit(1)
    typer.echo(f"ok satellite={satellite} status=pending path={path}")


@admin_app.command("replay-satellite")
def replay_satellite_command(
    satellite: Annotated[str, typer.Option("--satellite")],
    status: Annotated[str | None, typer.Option("--status")] = "completed",
) -> None:
    """Mark many source files as pending so they can be reprocessed."""
    from brin_hotspot.repositories.operations_repository import OperationsRepository

    settings = _bootstrap()
    updated = OperationsRepository(settings.hotspot_database).mark_satellite_sources_pending(
        satellite=satellite,
        status=status,
    )
    status_text = status if status is not None else "any"
    typer.echo(f"ok satellite={satellite} previous_status={status_text} reset={updated}")


@admin_app.command("reset-running")
def reset_running_sources_command(
    satellite: Annotated[str | None, typer.Option("--satellite")] = None,
) -> None:
    """Reset interrupted running source files to pending for retry."""
    from brin_hotspot.repositories.operations_repository import OperationsRepository

    settings = _bootstrap()
    updated = OperationsRepository(settings.hotspot_database).reset_running_sources(
        satellite=satellite,
        message="reset by operator",
    )
    typer.echo(f"ok reset={updated}")


@raster_app.command("scan")
def scan_rasters_command(
    input_dir: Annotated[Path, typer.Option("--input-dir", exists=True, file_okay=False)],
    raster_type: Annotated[str, typer.Option("--type")] = "FI",
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist raster metadata to PostGIS."),
    ] = False,
) -> None:
    """Scan GeoTIFF rasters, derive footprint metadata, and optionally persist it."""
    from brin_hotspot.raster import scan_rasters

    settings = _bootstrap()
    summary = scan_rasters(
        settings,
        input_dir=input_dir,
        raster_type=raster_type,
        persist=persist,
    )
    typer.echo(
        f"ok discovered={summary.discovered_count} persisted={summary.persisted_count} "
        f"skipped={summary.skipped_count}"
    )


@raster_app.command("tile")
def tile_rasters_command(
    input_dir: Annotated[Path, typer.Option("--input-dir", exists=True, file_okay=False)],
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
    raster_type: Annotated[str, typer.Option("--type")] = "FI",
    zoom: Annotated[str, typer.Option("--zoom")] = "5-12",
    processes: Annotated[int, typer.Option("--processes", min=1, max=16)] = 1,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1)] = 1800,
) -> None:
    """Generate web tiles from GeoTIFF rasters using GDAL."""
    from brin_hotspot.raster import generate_tiles

    settings = _bootstrap()
    summary = generate_tiles(
        input_dir=input_dir,
        output_dir=output_dir or settings.paths.output_dir / "tiles",
        raster_type=raster_type,
        zoom=zoom,
        processes=processes,
        timeout_seconds=timeout_seconds,
    )
    typer.echo(
        f"ok discovered={summary.discovered_count} tiled={summary.tiled_count} "
        f"skipped={summary.skipped_count}"
    )


@worker_app.command("run-once")
def worker_run_once_command(
    satellites: Annotated[
        list[str] | None,
        typer.Option("--satellite", help="Satellite to process. Repeatable."),
    ] = None,
    input_overrides: Annotated[
        list[str] | None,
        typer.Option(
            "--input",
            help="Override one satellite input as satellite=/path. Repeatable.",
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
) -> None:
    """Run one ingestion cycle across selected satellite inputs."""
    from brin_hotspot.worker import run_ingestion_cycle

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)
    summaries = run_ingestion_cycle(
        settings,
        satellites=tuple(satellites or ["snpp", "noaa20", "aqua", "tera", "landsat8"]),
        input_dirs=_parse_worker_input_dirs(input_overrides),
        persist=persist,
        enrich=enrich,
    )
    for summary in summaries:
        _echo_ingestion_summary(summary)


@worker_app.command("loop")
def worker_loop_command(
    satellites: Annotated[
        list[str] | None,
        typer.Option("--satellite", help="Satellite to process. Repeatable."),
    ] = None,
    input_overrides: Annotated[
        list[str] | None,
        typer.Option(
            "--input",
            help="Override one satellite input as satellite=/path. Repeatable.",
        ),
    ] = None,
    persist: Annotated[
        bool,
        typer.Option("--database/--no-database", help="Persist clusters and pixels to PostGIS."),
    ] = False,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Apply admin-boundary, anomaly, and duplicate filtering from PostGIS.",
        ),
    ] = False,
    interval_seconds: Annotated[int, typer.Option("--interval-seconds", min=1)] = 180,
    max_cycles: Annotated[
        int,
        typer.Option("--max-cycles", min=0, help="Number of cycles. Use 0 to run forever."),
    ] = 0,
    continue_on_error: Annotated[
        bool,
        typer.Option(
            "--continue-on-error/--fail-fast",
            help="Continue with later satellites and cycles after a satellite error.",
        ),
    ] = True,
) -> None:
    """Run repeated ingestion cycles with a fixed sleep interval."""
    from brin_hotspot.worker import run_worker_loop

    settings = _bootstrap()
    if enrich and not persist:
        typer.echo("--enrich requires --database", err=True)
        raise typer.Exit(2)
    summary = run_worker_loop(
        settings,
        satellites=tuple(satellites or ["snpp", "noaa20", "aqua", "tera", "landsat8"]),
        input_dirs=_parse_worker_input_dirs(input_overrides),
        persist=persist,
        enrich=enrich,
        interval_seconds=interval_seconds,
        max_cycles=max_cycles or None,
        continue_on_error=continue_on_error,
    )
    typer.echo(
        f"ok cycles={summary.cycle_count} ingestions={len(summary.ingestion_summaries)}"
    )


def _parse_worker_input_dirs(input_overrides: list[str] | None) -> dict[str, tuple[Path, ...]]:
    input_dirs: dict[str, list[Path]] = {}
    for value in input_overrides or []:
        satellite, separator, path = value.partition("=")
        if not separator or not satellite or not path:
            typer.echo("--input must use satellite=/path format", err=True)
            raise typer.Exit(2)
        input_dirs.setdefault(satellite.strip().lower(), []).append(Path(path))
    return {satellite: tuple(paths) for satellite, paths in input_dirs.items()}


def _echo_records(rows: list[dict[str, Any]]) -> None:
    if not rows:
        typer.echo("no rows")
        return
    for row in rows:
        typer.echo(" ".join(f"{key}={value}" for key, value in row.items()))


@admin_app.command("import-geojson")
def import_geojson_command(
    dataset: Annotated[
        str,
        typer.Argument(help="One of: province, kabupaten, kecamatan, anomaly."),
    ],
    path: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False)],
    id_field: Annotated[str, typer.Option("--id-field")] = "gid",
    name_field: Annotated[str, typer.Option("--name-field")] = "wa",
    prov_id_field: Annotated[str | None, typer.Option("--prov-id-field")] = None,
    kab_id_field: Annotated[str | None, typer.Option("--kab-id-field")] = None,
) -> None:
    """Import reference polygons from a GeoJSON FeatureCollection into PostGIS."""
    from brin_hotspot.repositories.reference_repository import (
        ReferenceDataset,
        ReferenceRepository,
        load_geojson_features,
    )

    settings = _bootstrap()
    allowed = {"province", "kabupaten", "kecamatan", "anomaly"}
    if dataset not in allowed:
        typer.echo(f"dataset must be one of: {', '.join(sorted(allowed))}", err=True)
        raise typer.Exit(2)

    features = load_geojson_features(
        path,
        id_field=id_field,
        name_field=name_field,
        prov_id_field=prov_id_field,
        kab_id_field=kab_id_field,
    )
    repository = ReferenceRepository(settings.hotspot_database)
    imported_count = repository.import_features(cast(ReferenceDataset, dataset), features)
    typer.echo(f"ok dataset={dataset} imported={imported_count}")


if __name__ == "__main__":
    app()
