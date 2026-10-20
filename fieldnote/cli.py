"""Command line interface.

    fieldnote build          build the synthetic corpus
    fieldnote ingest         ingest the corpus into a chunk manifest
    fieldnote index          encode the manifest into the vector store
    fieldnote ask "<q>"      ask a question
    fieldnote eval           run the full evaluation and write the report
    fieldnote serve          run the HTTP API
    fieldnote verify         check the fixtures are honest
    fieldnote models         pre-download every model
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import settings

app = typer.Typer(add_completion=False, help="Fieldnote - multimodal RAG for HVAC field service.")
console = Console()


def _manifest_path() -> Path:
    return settings.artifacts_dir / "manifest.jsonl"


@app.command("build")
def build(
    force: bool = typer.Option(False, help="Rebuild the corpus from scratch."),
) -> None:
    """Render the synthetic HVAC corpus (manuals, photos, calls)."""
    from .fixtures import build_corpus

    result = build_corpus(force=force)
    for kind, paths in result.items():
        console.print(f"[green]{kind}[/green]: {len(paths)} files")


@app.command("ingest")
def ingest(
    corpus: Path = typer.Option(None, help="Corpus directory."),
) -> None:
    """Ingest the corpus into a chunk manifest."""
    from .ingest import ingest_corpus, summarize, write_manifest

    chunks = ingest_corpus(corpus)
    path = write_manifest(chunks, _manifest_path())
    console.print(f"[green]ingested[/green] {summarize(chunks)}")
    console.print(f"manifest -> {path}")


@app.command("index")
def index_cmd(
    backend: str = typer.Option(settings.store_backend, help="sqlite | pgvector | qdrant"),
    db_path: str = typer.Option(None, help="Index file or connection target."),
) -> None:
    """Encode the manifest into the vector store."""
    from .ingest import read_manifest
    from .store import build_store, encode_chunks

    chunks = read_manifest(_manifest_path())
    store = build_store(backend, db_path)
    t0 = time.perf_counter()
    store.add(encode_chunks(chunks))
    store.save()
    console.print(f"[green]indexed[/green] {store.count()} in {time.perf_counter() - t0:.1f}s")


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="The question to answer."),
    k: int = typer.Option(settings.final_k, help="Candidates returned by the reranker."),
    backend: str = typer.Option(settings.store_backend),
    db_path: str = typer.Option(None),
    synthesis: str = typer.Option(settings.synthesis, help="extractive | vlm"),
    show_crops: bool = typer.Option(True, help="Print the crop and page for each citation."),
) -> None:
    """Ask a question and print the answer with its citations."""
    from .eval.runner import build_fieldnote_system
    from .ingest import read_manifest

    chunks = read_manifest(_manifest_path())
    system = build_fieldnote_system(
        chunks, backend=backend, db_path=db_path, synthesis=synthesis
    )
    t0 = time.perf_counter()
    result = system.retriever.search(question, k=k)
    answer = system.synthesizer.synthesize(
        question, result.candidates, latency=result.timings, units=result.units
    )
    elapsed = (time.perf_counter() - t0) * 1000

    console.print(f"\n[bold]{question}[/bold]\n")
    console.print(f"[cyan]{answer.answer}[/cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("#")
    table.add_column("modality")
    table.add_column("source")
    table.add_column("page")
    table.add_column("region")
    table.add_column("crop")
    for i, cit in enumerate(answer.citations, start=1):
        table.add_row(
            str(i),
            cit.modality.value,
            cit.doc_title[:38],
            str(cit.page or "-"),
            str(cit.region_label or "-"),
            str(cit.crop_path or "-") if show_crops else "-",
        )
    console.print(table)
    console.print(f"\n[dim]{elapsed:.0f} ms  {result.timings}[/dim]")


@app.command("eval")
def eval_cmd(
    backend: str = typer.Option(settings.store_backend),
    k: int = typer.Option(settings.final_k),
    synthesis: str = typer.Option(settings.synthesis),
) -> None:
    """Run the evaluation and write the report."""
    from .eval.report import render
    from .eval.runner import run_full_eval
    from .ingest import read_manifest

    chunks = read_manifest(_manifest_path())
    report = run_full_eval(
        chunks, backend=backend, k=k, synthesis=synthesis,
        db_path=str(settings.index_dir / "fieldnote.db"),
    )
    text = render(report)
    out = settings.artifacts_dir / "eval_report.md"
    out.write_text(text, encoding="utf-8")
    (settings.artifacts_dir / "eval_report.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    console.print(text)
    console.print(f"[green]report -> {out}[/green]")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    backend: str = typer.Option(settings.store_backend),
) -> None:
    """Run the HTTP API."""
    import uvicorn

    from .serve.app import create_app

    uvicorn.run(create_app(backend=backend), host=host, port=port)


@app.command("verify")
def verify() -> None:
    """Check that the fixtures are honest: no leaks, everything legible."""
    from .fixtures.build import check_collisions, verify_figure_answers
    from .ingest import ingest_corpus

    leaks = check_collisions()
    if leaks:
        console.print("[red]picture-only answers leaked into the text corpus:[/red]")
        for qid, answer, where in leaks:
            console.print(f"  {qid}: {answer!r} in {where}")
    else:
        console.print("[green]no collisions[/green] - picture-only answers are absent from the text")

    problems = verify_figure_answers(ingest_corpus())
    if problems:
        console.print("[red]unreadable figure answers:[/red]")
        for qid, answer, text in problems:
            console.print(f"  {qid}: expected {answer!r}")
    else:
        console.print("[green]legible[/green] - every figure answer is readable from the page")

    raise typer.Exit(1 if (leaks or problems) else 0)


@app.command("models")
def models() -> None:
    """Pre-download every model used by Fieldnote."""
    from .encode.registry import (
        get_audio_encoder,
        get_captioner,
        get_cross_encoder,
        get_image_encoder,
        get_text_encoder,
    )

    get_text_encoder()
    get_image_encoder()
    get_audio_encoder()
    get_cross_encoder()
    get_captioner()
    console.print("[green]all models cached[/green]")


def main() -> int:
    try:
        app()
    except KeyboardInterrupt:
        console.print("\ninterrupted")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
