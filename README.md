# Fieldnote

**Find the answer in the manuals, the photos and the calls — and get it back
with the picture it was read from.**

[![Fieldnote](docs/images/rooftop-hvac.jpg)](docs/images/rooftop-hvac.jpg)
<sub>Rooftop HVAC unit being craned into position. Photo: Los Angeles Air Force Base, public domain, via Wikimedia Commons.</sub>

---

## Contents

1. [What HVAC is, and what the work actually looks like](#1-what-hvac-is-and-what-the-work-actually-looks-like)
2. [The problem: the answer is a picture](#2-the-problem-the-answer-is-a-picture)
3. [What Fieldnote does](#3-what-fieldnote-does)
4. [Reading the screen](#4-reading-the-screen)
5. [The results](#5-the-results)
6. [How it works, step by step](#6-how-it-works-step-by-step)
7. [Run it](#7-run-it)
8. [Deploy it](#8-deploy-it)
9. [The API](#9-the-api)
10. [How to explain this to someone else](#10-how-to-explain-this-to-someone-else)
11. [Honest limitations](#11-honest-limitations)
12. [Design notes, layout, tests](#12-design-notes-layout-tests)

---

## 1. What HVAC is, and what the work actually looks like

**HVAC** stands for **Heating, Ventilation and Air Conditioning**. It is the
trade that keeps buildings at a temperature people can work in, moves the air
around them, and strips the moisture out of it. Almost every commercial
building runs on it, usually from equipment you never see.

The equipment splits into two halves, and the split matters for everything
that follows:

| | what it does | where you find it |
|---|---|---|
| **Air handling** | moves and conditions the air — filters, coils, blowers, dampers | a plant room, a mechanical room, the ceiling of an office |
| **Refrigeration** | moves heat from inside to outside — compressors, condensers, expansion valves, refrigerant | on the roof, or in a plant room |

<p align="center">
  <img src="docs/images/air-handler.jpg" width="32%" alt="An air handling unit in a plant room">
  <img src="docs/images/chiller.jpg" width="32%" alt="An air cooled liquid chiller">
  <img src="docs/images/outdoor-unit.jpg" width="32%" alt="Outdoor condensing units on a rooftop">
</p>
<sub>Left: an air handling unit. Centre: an air-cooled chiller. Right: outdoor condensing units on a rooftop. All via Wikimedia Commons — see <a href="docs/images/CREDITS.md">credits</a>.</sub>

**The work** is done by field technicians, and it is harder than it looks. A
commercial HVAC contractor might run 40 technicians, each of them driving to a
different building every day, and none of them can memorise the service manual
for every make of rooftop unit their customers own. A technician's week is a
sequence of:

- reading a fault on a control board and working out what it means;
- finding the right procedure in a 300-page manual for a machine they have
  never seen before;
- reading a **pressure-temperature curve** to work out what a gauge reading
  *should* be at today's outdoor temperature;
- matching a **wiring diagram** to a field-wired panel with somebody else's
  workmanship in it;
- recognising a failed part from a **photograph** — a bulged capacitor, a
  pitted contactor, a corroded coil;
- calling the manufacturer's support line, being put on hold, and being asked
  questions they answered on the first call.

Every one of those steps is a **knowledge lookup**, and almost all of them
turn into "open the right document, find the right page, read the right number".

<p align="center">
  <img src="docs/images/rooftop-units-brisbane.jpg" width="86%" alt="Air handling units on the roof of a large commercial building">
</p>
<sub>Rooftop units on a large commercial building. Photo: Kgbo, CC BY-SA 4.0, via Wikimedia Commons.</sub>

### The vocabulary, in one place

The interface explains these where they appear, but here they are in one list
so the rest of this document makes sense.

| term | what it actually means |
|---|---|
| **Rooftop unit (RTU)** | one self-contained box on the roof that does the heating, cooling and ventilation for a building |
| **Pressure-temperature curve (P-T curve)** | the chart that tells you what pressure a refrigerant *should* be at a given temperature. If the gauge does not match the curve, something is wrong. |
| **Cutout** | a safety switch that shuts the machine down when a limit is reached, so it cannot damage itself |
| **High / low pressure cutout** | the high-side and low-side safety limits, usually printed on the curve |
| **Nameplate / data plate** | the sticker on the machine with its model number, voltage and refrigerant |
| **Superheat** | how far the refrigerant gas is above the temperature it should be boiling at |
| **Subcooling** | how far the liquid refrigerant is below the temperature it should be condensing at |
| **Economizer** | the part that lets cool outside air in instead of conditioning recirculated air |
| **TXV** | thermostatic expansion valve — meters refrigerant into the evaporator |
| **Contactor / capacitor** | the switch that starts the compressor, and the part that helps the motors start |
| **PSI / PSIG** | pounds per square inch — how hard the refrigerant is being pushed |
| **Fault code** | what the unit's control board displays when it thinks something is wrong |

---

## 2. The problem: the answer is a picture

Here is a real question from that world:

> **"Why does unit 7 keep tripping on high pressure?"**

Where is the answer? Not in a paragraph. It is in three places at once:

| where | what is there | what it looks like |
|---|---|---|
| the service manual, page 112 | the high-pressure cutout setting for that refrigerant | a **labelled point on a graph** — "HP CUTOUT 385 PSI" |
| the job-site photo | the actual model of the unit on that roof, which is not the model on the paperwork | a **stamped nameplate** |
| the recorded support call | which roof the unit is on, and what the technician was told to check | **two sentences of speech** |

This is the shape of almost every field-service question. The knowledge is
spread across three media, and the part that matters most — the number —
lives in a **picture**.

### Why the usual approach fails

The standard way to make a picture searchable is to describe it and search the
description:

```
image  ──►  "a line graph with a blue line and a red line"  ──►  text embedding
```

This works right up until the question needs a number. A caption of a
pressure-temperature curve says *"a graph with a line going up"*. The question
needs **385**. The caption does not contain 385 — and because the captioning
happened when the document was **indexed**, nothing that happens afterwards
can put it back. The number was destroyed before anyone asked a question.

That is the trap this project exists to avoid. It is a text pipeline wearing a
costume.

---

## 3. What Fieldnote does

Fieldnote keeps pictures **as pictures**. It gives each kind of evidence its
own searcher, searches all of them at once, and then reads the answer out of
the evidence that actually contains it — handing back the picture so the
person reading it can check it.

![The Fieldnote interface answering a question about a pressure-temperature curve](docs/images/ui-answer.png)

Four things happen when you ask a question:

1. **Three searchers run in parallel** — one that reads words, one that looks
   at pixels, one that listens to waveforms. A typed question reaches all
   three, because each model has a text side that shares a space with its own
   picture and sound side.
2. **The result lists are merged** with Reciprocal Rank Fusion, which only
   looks at *ranks*, so it does not care that the three searchers score on
   different scales.
3. **A relevance model re-checks the shortlist**, then re-checks the
   individual lines inside the winners — because the sentence that says
   "15 minutes" is the answer, and the 900-character block it came from is not.
4. **The answer is read out of the pixels**, using OCR plus the layout of the
   page, and it comes back with the page number, the cropped region, and the
   full page to check it against.

And for anyone who does not speak HVAC, the answer comes with a **plain-English
version** and every technical term in it is clickable.

---

## 4. Reading the screen

<p align="center">
  <img src="docs/images/ui-home.png" width="92%" alt="The Fieldnote home screen">
</p>

- **The box at the top** is the whole interface. Type a question, press
  <kbd>Enter</kbd>. Press <kbd>/</kbd> from anywhere to jump back to it.
- **The example questions** are grouped by where the answer lives — from the
  manuals, from the job photos, from the support calls. Click one to run it.
- **Answer** is the value, with a **Copy** button.
- **In plain English** is the same answer, said without the jargon: *"The unit
  switches itself off when the refrigerant pressure reaches 385 psi. That is the
  safety limit printed on the chart — it is there to protect the compressor
  from damage."*
- **The little blue chips** are the technical terms in play. Click one and it
  explains itself: *cutout pressure — a safety switch that shuts the machine
  down when a limit is reached*.
- **How we found it** is the search trace in plain words: 40 words found, 40
  pictures found, 19 calls found → 99 combined → 27 best matches → 70 lines
  read. Below it, **the exact words the answer came from**, with the page, the
  region and the relevance score. This is the part that answers *"why did it
  say that?"*.
- **The evidence** is the picture, the region and the score for each
  candidate. Click any image to enlarge it; **full page** opens the page with
  the cited region outlined; **raw** opens the underlying chunk including its
  OCR text.
- A question in the URL runs itself, so an answer can be shared as a link.
- **How it works** (top right) opens a plain-language explanation of the
  whole thing.

---

## 5. The results

40 questions. 15 of them are **provably** unanswerable from text — the eval
checks the prose, the captions and the transcripts at run time and fails if a
picture-only answer turns up in any of them. CPU only, 8 cores, no GPU.

| metric | fieldnote | caption-only baseline | delta |
|---|---|---|---|
| accuracy, all 40 questions | **100.0%** | 60.0% | +40.0 pts |
| **accuracy, 15 picture-only questions** | **100.0%** | **0.0%** | **+100.0 pts** |
| accuracy, 25 text-answerable questions | **100.0%** | 96.0% | +4.0 pts |

| latency (ms, end to end) | p50 | p95 | p99 | max |
|---|---|---|---|---|
| fieldnote | 1919 | **2387** | 2615 | 2615 |
| caption-only baseline | 1203 | 2276 | 2535 | 2535 |

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

The four answers without a page number are the job-site photos, which have no
page to cite. Everything else points at a page and a rectangle.

**The baseline is not a strawman.** It is the same system with the same
reranker, grader, synthesis and latency budget — the only difference is that
every image is captioned and embedded as text. Notice that the baseline still
*retrieves* the right chart: it finds the figure, and then cannot read the
number off it. Retrieval was never the problem. The lossy step in the middle
was.

Full report: [`data/artifacts/eval_report.md`](data/artifacts/eval_report.md) —
regenerate with `fieldnote eval`.

---

## 6. How it works, step by step

### 6.1 The corpus

The knowledge a contractor has looks like this:

- **300 service manuals** (PDF). Prose, wiring diagrams, pressure-temperature
  curves, performance charts, spec tables, torque specs.
- **4,000 job-site photos**. Nameplates, gauges, control boards, failed parts.
- **Recorded calls** to the manufacturer's support line.

The project ships a synthetic version of all three, generated from a single
spec file that produces **both the corpus and the eval set** — so a question
can never point at evidence that is not there.

```bash
fieldnote build     # render the corpus
fieldnote ingest    # manuals -> pages, crops, OCR, transcripts
```

`ingest` is where the multimodal work starts:

- **PDFs** are opened with PyMuPDF. Each page is rendered at 200 dpi, and the
  **figure regions are cut out of it** — PyMuPDF's drawing clusters, image
  rectangles and table detection give the geometry, and the regions are
  classified as chart, wiring diagram, table, figure or photo. Each region
  becomes its own image chunk, and the page's prose becomes text chunks.
  Running headers and footers are excluded, because a page number is not
  knowledge.
- **Photos** become image chunks, OCR'd for nameplates, gauge readings and
  fault codes.
- **Calls** are transcribed by Whisper into timestamped segments, so a chunk
  can point at the exact second of the call it came from.

Every chunk carries a **modality tag** and knows how to point back at its
pixels or its audio. That is the central invariant of the whole system.

### 6.2 Three encoders, three spaces

| modality | encoder | space | good at |
|---|---|---|---|
| text | MiniLM (mean pooling) | 384-d | prose, transcripts, OCR strings |
| image | CLIP image tower | 512-d | pixels, charts, nameplates |
| audio | CLAP audio tower | 512-d | waveforms, acoustics |

Nothing is routed through a caption. **Images get no text projection at all** —
that is the whole point.

The subtlety that makes it work: CLIP's *text* tower and its *image* tower
share a space, so a typed question can reach the picture index. Same for CLAP
and audio. Without that, the question never gets to two thirds of the index.

**Audio is indexed twice, on purpose** — the waveform in the audio space, and
the transcript in the text space. A transcript is language, not a lossy summary
of a picture. Flattening a call to a caption would be as silly as flattening a
chart; flattening a chart is the bug.

### 6.3 Retrieval: parallel search, then fusion, then rerank

```
                 question (text)
                        │
        ┌───────────────┼───────────────┐
   MiniLM(words)   CLIP text tower   CLAP text tower
        │               │               │
   text space       image space      audio space
 (prose + tx)       (pixels)         (waveform)
        │               │               │
        └────── parallel search ─────────┘
                        │
             Reciprocal Rank Fusion
                        │
         relevance rerank (shortlist)
                        │
        expand the best chunks into lines
      (sentences · OCR phrases · call lines)
                        │
          relevance rerank (lines)
                        │
                answer  +  citations
```

**Why Reciprocal Rank Fusion and not a score sum?** The three spaces produce
scores on incomparable scales — a CLIP cosine of 0.28 and a MiniLM cosine of
0.62 mean nothing relative to each other, and normalising them by hand is
fragile and unfalsifiable. RRF only uses ranks, so it is scale-free by
construction and has one parameter that is not fitted to the eval set.

**Why rerank twice?** A relevance model judges a question and a passage
*together*, which is why it beats a bi-encoder — but it cannot be
precomputed, so every pair it judges is paid for on every question. Judging
30 pairs takes about a second; judging 150 takes five and buys nothing. So
the first pass picks the right *documents*, and the second picks the right
*line inside them*.

**Why expand into lines?** Because the answer to "how long must the unit run
before the subcooling is checked?" is the sentence that says *15 minutes*, not
the 900-character block it came from.

### 6.4 Reading the number off a chart

The picture-only questions are answered by OCR and geometry, not by a vision
model:

1. **The region is cut out** of the rendered page.
2. **OCR reads it** — and OCR does not know where words end, so it hands back
   `LPCUTOUT92PSI`. A **de-mangler** repairs that against an HVAC vocabulary,
   producing `LP CUTOUT 92 PSI`. It only accepts a segmentation that accounts
   for the *whole* token; anything it cannot fully explain is left alone,
   because a wrong split corrupts the evidence.
3. **The OCR boxes carry geometry.** A table cell is paired with its column
   header and its row label, so `2400 CFM` is known to be "maximum indoor
   airflow" for the 6-ton unit because of *where it sits*, not because of
   what it says.
4. **The question is split** into the thing being asked for and the place to
   look. "What field supply voltage is printed **on the YSC072 unit 7 wiring
   diagram**?" is two questions; only the first may decide the answer.
5. **A caption is refused.** A figure caption describes a figure; it does not
   state what the figure says, so it can never be the answer to a question
   about a value. Neither can a bare axis label like "300".

### 6.5 The answer, and its citations

The answer is a fragment plus its provenance:

```
385 (385 PSI)
  page 11 · chart · trane ysc072 service manual · crop attached
```

`40 / 40` answers carry a cropped image, and `GET /page/{chunk_id}` returns
the **whole page with the cited region outlined** — the view that settles a
disagreement with a customer.

### 6.6 The plain-language layer

A separate module turns a fragment of HVAC documentation into a sentence a
non-specialist can act on, by recognising what kind of value the question asked
for and what the unit means:

| the question asks about | the answer says |
|---|---|
| a pressure | *"The unit switches itself off when the refrigerant pressure reaches 385 psi. That is the safety limit printed on the chart — it is there to protect the compressor from damage."* |
| a voltage | *"This unit is wired for 240 V. If the power at the site does not match, the machine will not run correctly."* |
| a model | *"This unit is a NP-42. Everything about it — the parts, the settings, the procedure — follows from that number."* |
| a fault code | *"The control board is reporting LP-2. That code is the unit telling you what it thinks is wrong."* |

A glossary of ~40 terms ships with it, and the interface renders the terms
that appear in a given answer as clickable chips.

---

## 7. Run it

```bash
git clone https://github.com/Gunjannnn30/fieldnote.git
cd fieldnote
pip install -e ".[dev]"

fieldnote models        # pre-download the six models (~2 GB)
fieldnote build         # render the synthetic corpus
fieldnote ingest        # manuals -> pages, crops, OCR, transcripts
fieldnote index         # encode into the vector store
fieldnote serve         # http://127.0.0.1:8000/
```

`build`, `ingest` and `index` are one-time setup. After that it is just
`fieldnote serve`.

| command | what it does |
|---|---|
| `fieldnote build` | render the synthetic corpus (manuals, photos, calls) |
| `fieldnote ingest` | turn the corpus into a chunk manifest |
| `fieldnote index` | encode the manifest into the vector store |
| `fieldnote ask "..."` | one question, with citations, in the terminal |
| `fieldnote serve` | the API and the browser UI |
| `fieldnote serve --tunnel` | the same, plus a public https URL |
| `fieldnote eval` | run the evaluation, write the report |
| `fieldnote verify` | check the fixtures are honest |
| `fieldnote models` | pre-download every model |

### Asking from the terminal

```bash
fieldnote ask "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?"
```

```
385 (385 PSI)

 #  modality  source                            page  region   crop
 1  image     Trane Precedent YSC072 Service M…   11   chart    …/p0011-r00-chart.png
 2  text      Trane Precedent YSC072 Service M…   11   page_te… -
 3  image     Trane Precedent YSC072 Service M…   12   wiring…  …/p0012-r00-wiring_diagram.png
```

---

## 8. Deploy it

### Docker (one command)

```bash
docker compose up -d --build
```

The image is CPU-only (no CUDA, ~2 GB smaller), ships the models so the first
request is not a two-gigabyte download, runs as a non-root user, has a
healthcheck, and builds the corpus and the index on first start into a named
volume. `docker compose ps` tells you when it is ready.

```bash
./scripts/docker_up.sh        # macOS / Linux: build, wait, publish, print the URL
./scripts/docker_up.ps1       # Windows
```

Both wrap the whole sequence — build, start, wait for healthy, open a public
https tunnel, print the URL — into one command.

### A durable, self-healing publication

`fieldnote serve --tunnel` publishes a URL that lasts as long as the process.
For something that stays up across reboots, use the publisher script:

```bash
powershell -ExecutionPolicy Bypass -File scripts\publish.ps1
```

It starts the API and the tunnel **detached**, waits for both, writes the
public URL to `data/artifacts/live_url.txt`, and **restarts either of them if
they die**. Register it to run at every logon:

```bash
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
```

### A plain VPS

```bash
git clone https://github.com/Gunjannnn30/fieldnote.git && cd fieldnote
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

fieldnote models
fieldnote build && fieldnote ingest && fieldnote index
```

Then run it under systemd, with nginx or Caddy in front for TLS — or just
`scripts/publish.ps1`/`docker_up.sh` if you want the tunnel.

### Point it at your own data

Nothing in the system assumes the synthetic corpus. `ingest` walks a directory
and dispatches by file type — `.pdf` for manuals, images for job photos,
`.wav` / `.mp3` / `.m4a` for calls:

```bash
export FIELDNOTE_CORPUS_DIR=/srv/hvac-corpus
fieldnote ingest
fieldnote index
```

`FIELDNOTE_DATA_DIR` moves the whole data tree (corpus, index, artefacts),
which is what the container volume uses.

---

## 9. The API

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What model number is stamped on the nameplate in the job site photo?","include_crops":true}'
```

```json
{
  "answer": "MODEL NP-42",
  "explanation": "This unit is a NP-42. Everything about it - the parts, the settings, the procedure - follows from that number.",
  "headline": "Model: NP-42",
  "glossary": [{"term": "model number", "meaning": "the code that identifies which exact machine this is"}],
  "latency_ms": 2732.4,
  "answerable": true,
  "citations": [{
    "chunk_id": "job-photo-unit-7-nameplate-img:job_photo_unit_7_nameplate",
    "modality": "image",
    "doc_title": "Job Photo - Unit 7 Nameplate",
    "page": null,
    "region": "job_photo",
    "crop_b64": "data:image/png;base64,iVBORw0KGgo..."
  }],
  "trace": {
    "spaces": {"text": 40, "image": 40, "audio": 19},
    "fused": 99, "shortlist": 27, "units": 27,
    "winner": {"chunk_id": "...", "modality": "image", "text": "MODEL NP-42", "page": null}
  }
}
```

| endpoint | what it does |
|---|---|
| `POST /ask` | ask a question; returns the answer, the plain-English version, the citations and the trace |
| `GET /` | the browser UI |
| `GET /health` | liveness, and the state of the corpus and index |
| `GET /page/{chunk_id}` | the full page with the cited region outlined (PNG) |
| `GET /evidence/{chunk_id}` | the raw chunk behind a citation, including its OCR text |
| `GET /docs` | interactive OpenAPI documentation |

---

## 10. How to explain this to someone else

**Ten seconds**

> It's a search engine for HVAC technicians. The answer is usually a number
> printed on a graph. Most AI tools throw those numbers away by describing the
> picture instead of reading it. This one keeps the picture as a picture, so it
> can tell you the number — and shows you the picture so you can check it.

**Thirty seconds**

> A tech on a roof types one question. Fieldnote searches the manuals, the job
> photos and the recorded support calls at the same time, with a different
> searcher for each — one that reads words, one that looks at pictures, one
> that listens to sound. It then ranks what each one found and picks the best
> evidence.
>
> The important part: the picture searcher works on the actual pixels. A
> pressure-temperature curve is never turned into a description like "a line
> going up", because that description does not contain the 385 the technician
> needs. Fieldnote reads the number off the graph and hands back the answer
> with a crop of the exact spot, so the tech can verify it against the manual.

**Two minutes**

> **The problem.** A commercial HVAC contractor runs 40 field technicians
> across 300 manuals with wiring diagrams and pressure curves, 4,000 photos of
> failed parts, and recorded calls to the manufacturer's support line. A tech
> asking "why does unit 7 keep tripping on high pressure" needs a number from
> a chart on page 112, a model number off a nameplate, and a location from a
> phone call.
>
> **The trap.** The standard approach to "multimodal" search is to caption
> every image with a vision model and embed the caption as text. It works right
> up until the question needs a number. A caption of a pressure curve says "a
> graph with a line going up" — it has no 385 in it, and because the captioning
> happened at *indexing* time, nothing downstream can get it back. That is a
> text pipeline wearing a costume.
>
> **The approach.** Fieldnote indexes each modality in the space where its
> signal is strongest — pixels for images, waveforms for audio, tokens for
> prose — and fuses the three result lists with Reciprocal Rank Fusion before
> a relevance model makes the final call. The picture is still pixels at the
> moment the question is asked, so the numbers are still there.
>
> **The evidence.** On a 40-question eval where 15 questions are *provably*
> unanswerable from text, Fieldnote scores 100% against the caption-only
> baseline's 0%. The baseline is implemented properly — same reranker, same
> grader, same synthesis — so the only difference is whether the images were
> flattened. Notably the baseline still *retrieves* the right chart; it just
> cannot read the number off it. Retrieval was never the problem. The lossy
> step in the middle was.
>
> **The honest caveat.** The corpus is synthetic, because the real manuals are
> not in this repository. The system is real; the numbers are measured on a
> corpus we generated. A real corpus of 300 scanned manuals will be harder.

---

## 11. Honest limitations

- **The corpus is synthetic.** There are no real HVAC manuals in this
  repository. The system is real, but the numbers above are measured on a
  corpus we generated, and 300 scanned manuals will be harder — noisier OCR,
  worse figure detection, more languages.
- **Latency is measured on 8 CPU cores** with the deterministic synthesiser.
  The p95 of 2.4 s is under the 6 s budget. The VLM synthesiser path
  (`FIELDNOTE_SYNTHESIS=vlm`) is far slower and is not what the gate is
  measured against.
- **The answer is extractive by default**: it picks the best-supported
  fragment and states it, rather than writing prose. That is deliberate for a
  field tool — a number that can be traced beats a paragraph that reads well —
  and it is what makes the citations meaningful. The plain-English layer is
  generated, but from a template matched to the kind of value the question
  asked for, not by a language model.
- **The charts it reads best are charts with labels.** A value printed *on* a
  curve is read exactly. A value at an arbitrary point on an unmarked curve
  needs a model that can interpolate, and the answer should be marked as an
  estimate when it is one.
- **Audio was never the hard modality.** The baseline gets the audio questions
  nearly right too, because a transcript *is* text. The interesting result is
  the one about images, and the eval is shaped to make that visible.
- **The public tunnel URL changes when the tunnel restarts.** For a fixed
  address you need a named tunnel on your own domain. Everything else —
  Docker, the systemd unit, the reverse proxy — is fixed.

---

## 12. Design notes, layout, tests

**[docs/DESIGN.md](docs/DESIGN.md)** covers early fusion versus late fusion in
full, why converting a chart to a caption throws away the axis values the
question actually needed, the module map, the scoring model and its weights,
the interface decisions, and the bugs that cost the most time — including a
chunk-id collision that silently turned every picture into its own caption, a
28-second latency that was really 150 relevance-model calls and 63
re-encodings per question, and an application-control policy that made
`scikit-learn` unloadable and took `sentence-transformers` out of the
dependency tree.

```
fieldnote/
  schema.py            Chunk, Modality, Citation, Trace - the modality tag lives here
  config.py            every tunable, every model id
  textutil.py          normalisation, sentence splitting, domain synonyms
  encode/              text (MiniLM), image (CLIP), audio (CLAP) encoders
  ingest/              pdf, images, audio -> chunks
  vision/              region detection, OCR, OCR de-mangling
  store/               sqlite | pgvector | qdrant, one space per modality
  retrieve/            parallel search, RRF fusion, relevance reranking
  answer/              evidence units, plain English, synthesis, citations
  baseline/            the caption-only system, implemented properly
  eval/                dataset, grader, runner, report
  fixtures/            the synthetic corpus and its self-checks
  serve/               FastAPI app and the browser UI
  cli.py               fieldnote build | ingest | index | ask | eval | serve
Dockerfile             CPU-only image, models baked in, non-root
docker-compose.yml     one command to a running service
docs/images/           README photography and UI screenshots
```

```bash
pytest                 # fast unit tests
pytest -m slow         # integration tests (needs the models and the corpus)
ruff check .           # lint
fieldnote eval         # regenerate the report
```

## Licence

MIT. The photographs in `docs/images/` are used under the licences recorded in
[`docs/images/CREDITS.md`](docs/images/CREDITS.md).
