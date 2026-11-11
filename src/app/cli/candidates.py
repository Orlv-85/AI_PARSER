"""Source candidate commands: import, validate, review outcomes (src/app/cli/main.md)."""
import typer

from app.cli import deps
from app.usecases.sources.onboarding import batch_outcomes, import_batch
from app.usecases.sources.validation import validate_batch

app = typer.Typer()
_VALIDATE_BATCH_ID_OPTION = typer.Option(None, "--batch-id", min=1)
_VALIDATE_CANDIDATE_ID_OPTION = typer.Option([], "--candidate-id", min=1)


@app.command("import-candidates")
def import_candidates(
    raw_text: str = typer.Argument(
        ...,
        help="Raw text containing candidate URLs or markdown links.",
    ),
) -> None:
    deps.create_all()
    result = import_batch(deps.SessionLocal, raw_text)
    typer.echo(
        "source import complete: "
        f"batch_id={result.batch_id} "
        f"parsed={result.parsed_count} "
        f"accepted={result.accepted_count} "
        f"rejected={result.rejected_count}"
    )


@app.command("validate-candidates")
def validate_candidates(
    batch_id: int | None = _VALIDATE_BATCH_ID_OPTION,
    candidate_id: list[int] = _VALIDATE_CANDIDATE_ID_OPTION,
) -> None:
    candidate_ids = list(candidate_id)
    if batch_id is None and not candidate_ids:
        raise typer.BadParameter("Provide --batch-id or at least one --candidate-id.")

    deps.create_all()
    results = validate_batch(deps.SessionLocal, batch_id=batch_id,
                             candidate_ids=candidate_ids or None)

    typer.echo(f"source validation complete: validated={len(results)}")
    for result in results:
        detail = result.validation_error or "ok"
        typer.echo(
            f"{result.candidate_id}\t{result.detected_type}\t{result.status}\t{detail}"
        )


@app.command("review-batch-outcomes")
def review_batch_outcomes(
    batch_id: int = typer.Option(..., "--batch-id", min=1),
) -> None:
    deps.create_all()
    summary = batch_outcomes(deps.SessionLocal, batch_id)
    if summary is None:
        raise typer.BadParameter(f"source import batch not found: {batch_id}")

    typer.echo(
        "batch review outcomes: "
        f"batch_id={summary['batch_id']} "
        f"total={summary['total_candidates']} "
        f"pending_review={summary['pending_review_count']} "
        f"validated={summary['validated_count']} "
        f"approved={summary['approved_count']} "
        f"rejected={summary['rejected_count']} "
        f"duplicates={summary['duplicate_count']}"
    )
