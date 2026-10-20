# Fieldnote

**Multimodal retrieval for HVAC field service.** Manuals with wiring diagrams
and pressure curves, job-site photos, and recorded support calls — one index,
one question, and an answer the technician can check against the page.

> A tech standing on a roof asks why unit 7 keeps tripping on high pressure.
> The answer is not in a paragraph. It is a labelled point on a pressure-
> temperature curve on page 112 of a service manual, a stamped nameplate on a
> job-site photo, and a two-word answer to a question on a recorded call to
> the manufacturer's support line. All three have to be reachable by typing a
> question.

---

## The claim, and the evidence for it

Most "multimodal" RAG systems are text pipelines wearing a costume: every
image is captioned by a vision model, the caption is embedded with a text
encoder, and the result is searched as if it were a paragraph.

That works right up until the question needs a number.

> A caption of a pressure-temperature curve says *"a graph with a line going
> up from left to right"*. The question needs **385**. The caption does not
> have 385 in it, and no amount of clever retrieval will put it back.

Fieldnote indexes pictures **as pictures**, and the eval measures the
difference against a caption-only baseline that is otherwise identical -
same reranker, same grader, same synthesis, same latency budget.

### Results

40-question eval, 15 of which are provably unanswerable from text alone.
CPU-only, 8 cores, no GPU.

| metric | fieldnote | caption-only baseline | delta |
|---|---|---|---|
| accuracy, all 40 questions | **100.0%** | 60.0% | +40.0 pts |
| **accuracy, 15 picture-only questions** | **100.0%** | **0.0%** | **+100.0 pts** |
| accuracy, 25 text-answerable questions | **100.0%** | 96.0% | +4.0 pts |

| latency (ms, end to end) | p50 | p95 | p99 | max |
|---|---|---|---|---|
| fieldnote | 2223 | **2699** | 3189 | 3189 |
| caption-only baseline | 1800 | 3024 | 4287 | 4287 |

| citation compliance | fieldnote | caption-only baseline |
|---|---|---|
| answers carrying a cropped image | **40 / 40** | 0 / 40 |
| answers carrying a page number | 36 / 40 | 40 / 40 |
| citation points at the right page | 90.0% | 87.5% |

| source modality of the winning evidence | fieldnote | caption-only baseline |
|---|---|---|
| image | **11** | 2 |
| audio | 5 | 6 |
| text | 24 | 32 |

The four answers without a page number are the job-site photos, which have
no page to cite. Everything else points at a page and a rectangle.

Full report: [`data/artifacts/eval_report.md`](data/artifacts/eval_report.md)
(regenerate with `fieldnote eval`).

### Why the baseline scores 0% and not 40%

The 15 picture-only answers are **verified absent** from the text corpus at
run time — prose, figure captions and call transcripts are all searched, and
the check is part of the eval, not a claim in the README:

```
## 7. Unanswerability verification
No picture-only answer appears in the text corpus.
All 15 are genuinely unanswerable from text alone.
```

The baseline still *retrieves* the right figure in several cases - the
caption says "a graph with a line..." and the question says "pressure-
temperature curve", so the retriever finds it. It just cannot read the number
off it. That is the whole argument in one number: **retrieval is not the
problem, the lossy step in the middle is.**

Note the modality table above. The baseline's winning evidence came from a
picture 2 times and from prose 32 times - but in the baseline, a "text" chunk
can be a caption of a picture. That is the costume.

---

## How it works

### Late fusion, three spaces, one cross-encoder

```
                    question (text)
                          |
        +-----------------+------------------+
        |                 |                  |
   MiniLM(text)      CLIP text tower    CLAP text tower
        |                 |                  |
   text space         image space        audio space
   (prose +          (pixels)           (waveform)
    transcripts)
        |                 |                  |
        +------ parallel search -----------+
                          |
                 Reciprocal Rank Fusion
                          |
            cross-encoder rerank (shortlist)
                          |
            expand best chunks into units
            (sentences / OCR phrases / transcript lines)
                          |
            cross-encoder rerank (units)
                          |
                  answer + citations
```

- **Each modality has its own encoder.** Images are embedded by CLIP's image
  tower from their pixels. Audio is embedded by CLAP from its waveform. Prose
  is embedded by MiniLM. Nothing is routed through a caption.
- **A typed question reaches the picture index** because CLIP's text tower
  shares a space with its image tower, and CLAP's text tower shares a space
  with its audio tower. This is the single most important detail in the
  design: without it the question never reaches two thirds of the index.
- **Audio is indexed twice, on purpose.** The waveform lives in the audio
  space; the transcript also lives in the text space. A transcript is
  language, not a lossy summary of a picture - flattening a call to a caption
  would be as silly as flattening a chart. Images get no such second
  projection, and that is exactly the point.
- **Fusion is Reciprocal Rank Fusion**, not a score sum. The three spaces
  produce scores on incomparable scales, and RRF only uses ranks, so it is
  scale-free and has no parameter that can be quietly fitted to the eval set.
- **The cross-encoder runs twice**: once over a shortlist of chunks to pick
  which evidence matters, and once over the *evidence units* inside those
  chunks. A 900-character chunk is the wrong granularity for an answer; the
  sentence that says "15 minutes" is the right one.

### Reading a chart without a vision model

The picture-only questions are answered by OCR plus geometry, not by a VLM:

- the manual page is rendered and the **figure regions are cut out**
  (`fieldnote/vision/regions.py` uses PyMuPDF's drawing clusters, image
  rects and table detection);
- each crop is **OCR'd**, and the OCR text is **de-mangled** - OCR does not
  know where words end, so `LPCUTOUT92PSI` becomes `LP CUTOUT 92 PSI`
  (`fieldnote/vision/demangle.py`). The splitter only accepts a segmentation
  that accounts for the *whole* token; anything it cannot fully explain is
  left alone, because a wrong split corrupts the evidence;
- the OCR boxes carry **geometry**, so a table cell is paired with its column
  header and its row label (`2400 CFM` is "maximum indoor airflow" for the
  6-ton unit because of where it sits, not because of what it says);
- a **question focus** is extracted - "what field supply voltage is printed
  **on the YSC072 unit 7 wiring diagram**" is two questions, one locating the
  figure and one asking for a value, and only the second one should decide
  the answer.

A vision-language model is available as an alternative synthesiser
(`FIELDNOTE_SYNTHESIS=vlm`, SmolVLM by default) and as a true cross-attention
image reranker, but the default path is deterministic, runs on CPU, and fits
the latency budget.

---

## Running it

```bash
git clone https://github.com/Gunjannnn30/fieldnote.git
cd fieldnote

pip install -e ".[dev]"

fieldnote models        # pre-download the six models (~2 GB)
fieldnote build         # render the synthetic corpus
fieldnote ingest        # manuals -> pages, crops, OCR, transcripts
fieldnote index         # encode into the vector store
fieldnote ask "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?"
```

```
What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?

385 (385 PSI)

 #  modality  source                            page  region   crop
 1  image     Trane Precedent YSC072 Service M…   11   chart    …/p0011-r00-chart.png
 2  text      Trane Precedent YSC072 Service M…   11   page_te… -
 3  image     Trane Precedent YSC072 Service M…   12   wiring…  …/p0012-r00-wiring_diagram.png
```

Run the eval, the API and the tests:

```bash
fieldnote eval                       # writes data/artifacts/eval_report.md
fieldnote serve --port 8000          # POST /ask returns the crop as base64
pytest -m slow                       # integration tests
pytest                               # fast unit tests
```

### The corpus is synthetic, and that is a deliberate limitation

There are no real HVAC manuals in this repository. `fieldnote/fixtures/spec.py`
is the single source of truth for both the corpus *and* the eval set, so a
question can never point at evidence that is not there. It renders:

- **4 service manuals** (Trane, Carrier, Lennox, Johnson Controls) with
  realistic prose, rasterised charts, wiring diagrams and spec tables;
- **3 job-site photos** - a nameplate, a gauge reading, a control-board fault
  display;
- **2 recorded support calls**, synthesised with the Windows speech engine so
  that Whisper has genuine audio to transcribe.

Two checks keep the benchmark honest, and both run in CI-ish fashion via
`fieldnote verify`:

1. **Collision check** - no picture-only answer appears in the prose, the
   captions or the transcripts. If one did, the "unanswerable from text
   alone" claim would be false.
2. **Legibility check** - every picture-only answer survives the real OCR
   pipeline on the *ingested* crop, not on a fresh render. A page render
   downsamples the figure, and a value that reads fine on its own can be
   unreadable once it has been through a PDF.

A benchmark where the evidence is not legible measures the fixture, not the
system. Both checks fail the build loudly.

### The honest limitations

- The corpus is synthetic. The system is real, but the *numbers* above are
  measured on a corpus we generated, and a real corpus of 300 scanned manuals
  will be harder - noisier OCR, worse figure detection, more languages.
- Latency is measured on 8 CPU cores. The p95 of 2.7 s is under the 6 s gate
  with headroom to spare; the VLM synthesiser path is far slower and is not
  what the gate is measured against.- The answer synthesiser is extractive by default: it picks the best-supported
  fragment and states it. It does not write prose. That is deliberate for a
  field tool, where a number that can be traced beats a paragraph that reads
  well, and it is what makes the citations meaningful.
- Audio was never the hard modality. The baseline gets the audio questions
  nearly right too, because a transcript *is* text. The interesting result is
  the one about images, and the eval is shaped to make that result visible.

---

## Design notes

[`docs/DESIGN.md`](docs/DESIGN.md) covers early fusion versus late fusion, why
converting a chart to a caption throws away the axis values the question
actually needed, the module map, the scoring model, and the things that went
wrong on the way.

## Layout

```
fieldnote/
  schema.py            Chunk, Modality, Citation - the modality tag lives here
  config.py            every tunable, every model id
  textutil.py          normalisation, sentence splitting, domain synonyms
  encode/              text (MiniLM), image (CLIP), audio (CLAP) encoders
  ingest/              pdf, images, audio -> chunks
  vision/              region detection, OCR, OCR de-mangling
  store/               sqlite | pgvector | qdrant, one space per modality
  retrieve/            parallel search, RRF fusion, cross-encoder reranking
  answer/              evidence units, synthesis, citations, VLM engine
  baseline/            the caption-only system, implemented properly
  eval/                dataset, grader, runner, report
  fixtures/            the synthetic corpus and its self-checks
  serve/               FastAPI app
  cli.py               fieldnote build | ingest | index | ask | eval | serve
scripts/
  download_models.py   pre-fetch every model
  verify_fixtures.py   the two honesty checks
  run_eval.py          the eval, without the CLI
  debug_query.py       trace one query through every stage
  sanity_check.py      confirm the joint spaces actually line up
```

## Licence

MIT.
