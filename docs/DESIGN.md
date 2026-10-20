# Design notes

Why Fieldnote is built the way it is, what the alternatives cost, and what
went wrong along the way.

---

## 1. Early fusion vs late fusion

### Early fusion

Early fusion mixes the raw signals *before* the model sees them. The
canonical implementation:

```python
caption = vision_model.describe(image)          # "a graph with a line..."
document = manual_text + " " + caption           # early fusion
vector   = text_encoder(document)                # one vector, one space
```

The retrieval decision is then made in a single space that **never contained
the picture**. Everything the caption dropped is dropped permanently, at
indexing time, before a single question is asked.

### Late fusion

Late fusion keeps the modalities separate all the way to the point where the
system has to commit to an answer:

```python
text_vector  = minilm(prose)            # text space
image_vector = clip.pixels(crop)         # image space
audio_vector = clap.waveform(call)       # audio space

hits = search(text_space) + search(image_space) + search(audio_space)
hits = reciprocal_rank_fusion(hits)      # scale-free merge
hits = cross_encoder.rerank(hits)        # the pair is judged together
```

The picture is still pixels when the question is asked. The cross-encoder sees
the OCR of the crop; the answer layer sees the crop; the citation carries the
crop and the rectangle it came from.

### What late fusion costs

This is not a free upgrade, and pretending otherwise would be dishonest:

| | early fusion | late fusion |
|---|---|---|
| indexes | 1 | 1 per modality |
| query encoders | 1 | 1 per modality |
| fusion | none | required |
| storage | 1 vector per chunk | 1 vector per (chunk, space) |
| OCR / VLM at query time | no | usually yes |
| preserves numbers on charts | **no** | yes |

The measured cost on this corpus, CPU-only, 8 cores: p95 of 2.9 s end to end
at k=20, against a 6 s budget. The early-fusion version is roughly a second
faster, and answers none of the 15 picture-only questions.
Fieldnote pays the extra index, the extra query encoders and the fusion step,
because the numbers are the product. A technician does not need a
description of a curve; they need the 385.

### The fusion has to be scale-free

The three spaces produce scores on incomparable scales. A CLIP cosine of
0.28 and a MiniLM cosine of 0.62 mean nothing relative to each other, and
normalising them by hand is fragile and unprincipled.

**Reciprocal Rank Fusion** only uses ranks:

```
score(d) = sum over spaces of  1 / (k + rank_space(d))
```

It is scale-free by construction, it has one parameter (k, set to 60), and
that parameter is not fitted to the eval set. It is also hard to beat by
accident: a document that is mediocre in one space but good in another can
still win, which is what you want when the question is only answerable in one
of them.

### The audio asymmetry

Audio is indexed in **two** spaces: the waveform in the audio space (CLAP)
and the transcript in the text space (MiniLM). This is not a contradiction of
the "index each modality with its own encoder" rule - it is the point of the
rule, applied honestly.

- A **transcript is language**. Transcribing a call and embedding the
  transcript loses nothing that a question could have asked about. The
  waveform adds what only the waveform has: the sound of a compressor
  short-cycling, a technician's tone, a background rattle.
- A **caption is a summary of a picture**. The summary is what loses the
  information.

So the trap is specific to pictures, and the eval is shaped to make that
visible: the 15 hard questions are all picture-only, and the audio questions
are in the text-answerable group where both systems do well.

The weights follow from this. A cross-encoder decides which call segment
answers the question, so the cross-encoder gets most of the weight for audio
(0.80) and the acoustic similarity gets the rest (0.20). For images the
balance is different again, and deliberately so - see §4.

---

## 2. Why captioning a chart throws away the axis values

This is the whole project in one example.

The question:

> *What is the high-pressure cutout pressure labeled on the R-410A
> pressure-temperature curve?*

The answer: **385**.

The picture contains, in pixels: a title, two curves, two dashed reference
lines, axis tick labels from 0 to 160 and 0 to 400, and two annotations -
`HP CUTOUT 385 PSI` and `LP CUTOUT 92 PSI`.

A captioner sees the *composition*: a line chart, two series, a legend, a
title. It writes something like:

> *"A line graph with a blue line and a red line showing pressure against
> temperature."*

That is a perfectly good caption. It is also useless for this question,
because:

| what the question needs | what the caption has |
|---|---|
| 385 | "blue line" |
| which of the two cutouts | "two lines" |
| the unit, psi | "pressure" |
| the refrigerant, R-410A | nothing |

The caption is a lossy function of the image, and the loss is *not uniform*.
What a caption preserves is layout and topic. What it destroys is **the
numbers and their labels** - which is exactly the class of information a
service question is about.

Fieldnote keeps the pixels, and reads the numbers with OCR:

```
R-410APRESSURE-TEMPERATURECURVE | BUBBLE (LIQUID) | PEAK425PSIG | DEW (VAPOR) |
385.PSI | 400 | 300 | PRESSURE (PSIG) | 200 | 100 | LPCUTOUT92PSI | ...
```

which, after de-mangling, is:

```
R-410A PRESSURE-TEMPERATURE CURVE | BUBBLE LIQUID | PEAK 425 PSIG | DEW VAPOR |
385 PSI | 400 | 300 | PRESSURE PSIG | 200 | 100 | LP CUTOUT 92 PSI | ...
```

Every number the picture contains is still there, with the label it belongs
to. That is the difference between an index and a lossy index.

### OCR is not a caption

OCR has its own failure mode - it has no idea what a *word* is, so it hands
back `LPCUTOUT92PSI` and `FIELDSUPPLY:240V3PH60HZ`. That is a tokenisation
problem, not a semantic one, and it is fixable:

- the de-mangler segments a run-together token against a domain vocabulary;
- it only accepts a segmentation that accounts for the **whole** token
  (`NORTHPOINTMANUFACTURING` is left alone, because guessing would corrupt it);
- hyphens survive, because `NP-42` and `LP-2` are identifiers a technician
  has to read back.

The difference in the end: a caption loses the numbers permanently, at
indexing time, and OCR loses a space, recoverably, at ingestion time.

---

## 3. The module map

| module | responsibility |
|---|---|
| `schema.py` | `Chunk`, `Modality`, `Citation`. The modality tag is on every chunk, and every chunk knows how to point back at its pixels or its audio. |
| `textutil.py` | Normalisation, sentence splitting, HVAC synonym groups. The synonym map is explicit and small so a reviewer can audit exactly what counts as the same concept. |
| `encode/` | One encoder per modality. `registry.py` loads them lazily; the models are ~2 GB and not every command needs all of them. |
| `ingest/pdf.py` | Renders pages, cuts figure regions out of them, OCRs each crop, attaches the figure's printed caption. |
| `vision/demangle.py` | OCR tokenisation repair. |
| `store/` | `sqlite` (default, no infrastructure), `pgvector`, `qdrant`. One collection per space. |
| `retrieve/fuse.py` | RRF and the alternatives. |
| `retrieve/rerank.py` | Cross-encoder over a shortlist, then over evidence units. |
| `answer/units.py` | Chunks -> evidence units; the scoring model. |
| `answer/synthesize.py` | Extractive (default) and VLM synthesis. |
| `baseline/caption_only.py` | The trap, implemented properly so the comparison is fair. |
| `eval/` | Dataset, grader, runner, report. |
| `fixtures/` | The synthetic corpus, and the two checks that keep it honest. |

### The retrieval cascade, and why it is shaped that way

```
query
  |
  +-- encode into three spaces                 (MiniLM / CLIP text / CLAP text)
  +-- parallel search, three spaces            (~20 ms)
  +-- Reciprocal Rank Fusion                    (~1 ms)
  +-- shortlist: top-8 per space + top-12 fused (~30 chunks)
  +-- cross-encoder over the shortlist          (~700 ms)
  +-- expand the best 6 chunks into units       (sentences, OCR phrases, transcript lines)
  +-- cross-encoder over the units              (~900 ms)
  +-- answer + citations
```

The shortlist is short on purpose. A cross-encoder cannot be precomputed, so
every pair it judges is paid for on every question. Judging 30 pairs takes
about a second; judging 150 takes about five, and buys almost nothing.

The shortlist is built from **two** sources. The best few from each space
guarantee every modality is represented - a question about a chart must not
be answered from prose. The best few by fused rank stop a chunk being
dropped because one space's encoder happened to rank it poorly: an audio
segment is ranked *acoustically* by CLAP, and acoustic similarity says nothing
about which segment mentions roof B.

---

## 4. Scoring model, and the reasoning behind it

Two stages, with different signals, because the evidence is different.

**Chunk level** (which documents matter):

| signal | text | image | audio |
|---|---|---|---|
| cross-encoder | 1.00 | 0.40 | 0.80 |
| joint space (CLIP / CLAP) | - | 0.60 | 0.20 |
| VLM cross-encoder | - | 0.60 | - |

**Unit level** (which fragment answers the question): a cross-encoder score, a
lexical overlap against the question, a *focus* overlap, a chunk-relevance
term, a value-quality term, and modality-specific weights.

Three things are worth calling out.

**A caption is a pointer, not the evidence.** A figure caption describes a
figure; it does not state what the figure says. If the question asks for a
value, a fragment that states no value cannot be the answer, and is pushed
down hard. The same applies to a figure's *title* - the topmost line of a
chart says what the chart is, never what it says.

**A bare axis label is not a value.** "300" on the y-axis of a pressure
curve is a tick. "385 PSI" is a value. The scoring prefers the second, which
is how "300" loses to "HP CUTOUT 385 PSI".

**The question has two jobs, and only one of them picks the answer.** "What
field supply voltage is printed **on the YSC072 unit 7 wiring diagram**?"
locates the figure *and* asks for a value. The first part must not decide
the answer, or the title "UNIT 7 FIELD WIRING DIAGRAM" wins and the reply is
"7". So the question is split into a focus (what is being asked for) and a
locator (where to look), and only the focus is allowed to break ties. For a
"which <thing>" question the focus is decisive, because the answer *is* the
named thing.

**The cross-encoder is a poor judge of OCR fragments.** ms-marco scores
"2400 CFM" at **-11** for a question it answers perfectly: it was trained on
long passages, and a table cell is not one. Normalising the cross-encoder
across all candidates let that one outlier compress the whole image group to
zero, and no image answer could ever win. The fix was to stop trusting it
for image units: the lexical match against the label the question points at
is the signal that actually works there.

---

## 5. The interface

A field tool has to be usable in one motion, on a phone, in sunlight, by
someone holding a manifold gauge in the other hand. So:

- the **answer is the hero** - one fragment, large, with a copy button;
- the **evidence is immediately below it**, visible without scrolling far, with
  the actual crop rather than a description of it;
- the **retrieval trace is shown, not hidden** - 40 text hits, 40 picture
  hits, 19 audio hits, 99 fused, 29 reranked, 27 fragments read, and the
  winning fragment verbatim. A service manager asking "why did it say that?"
  can be answered without a developer;
- the question lives in the URL, so an answer is a shareable link.

The interface changed shape during the build. The first version had a large
hero and twelve example questions, which pushed the answer below the fold on
a laptop. Once there is an answer, the hero shrinks and the example list
collapses to three per group - the marketing copy gets out of the way exactly
when it stops being useful.

The crop is shown at full width and the *whole page* is one click away, with
the cited region outlined. That view - full page, region marked - is the one
that settles a disagreement with a customer, and it is the reason the system
keeps a rectangle for every citation instead of just a path.

---

## 6. What went wrong

Kept here because the failures are the interesting part.

**Chunk id collision.** The caption-only baseline kept the same `chunk_id` as
the image chunk it replaced. In the fusion step the two collided, and the
picture silently became its own caption. Symptom: 0% on every picture-only
question, with no error anywhere. The clue was that the text space contained
79 rows when the corpus had 35 text chunks. Fixed by giving the caption its
own id namespace (`caption::...`).

**A shared database.** Both systems were writing to the same SQLite file, so
the baseline's caption chunks ended up inside Fieldnote's text space. Two
indexes, two files.

**The sentence splitter ate the unit.** `re.split(r"(?<=[.!?])\s+")` turned
*"0.5 in. w.c."* into two sentences, and the answer became "0.5 in." - the
value without its unit. The fix was an abbreviation-aware splitter that
knows "in", "w.c.", "lb" and "Figure 14" are not sentence ends.

**Page text was line-wrapped.** A PDF paragraph comes back with a newline in
the middle of a sentence, so the same splitter cut "…between the condensing
unit and the | evaporator on every 5-ton R-410A circuit." in half. Fixed by
rebuilding page text from PDF *blocks* rather than lines.

**"R-410A" is not a measurement.** The value detector looked for any digit,
so a sentence that only mentioned the refrigerant counted as stating a value
and was never penalised. And "Class 2" - a reference, not a measurement -
counted too. Now a number has to stand on its own, and a number that follows
"Class", "Figure", "Section" is a reference.

**Centring a label pushes half of it out of the axes.** A matplotlib
annotation with the default `ha="center"` put "HIGH PRESSURE CUTOUT 385 PSI"
half outside the plot, and OCR lost the front of it. Left-aligned labels, with
a white plate behind them, are legible.

**A test that was wrong, and the code that was.** The boundary rule for
matching answers has to be careful: "18" must not match inside "187V", "14"
must not match inside "XC14", but "NP-42" has to match inside "MODEL NP-42".
The first version used word boundaries and failed the second case, because
OCR ran the words together. The fix was to fix the *input* - de-mangle the
OCR - rather than to loosen the rule, and to keep the rule strict.

**Latency was 28 seconds.** The reranker was re-encoding all 44 image crops
and 19 audio clips on every question, when their vectors were already in the
index. Dotting the stored vector with the stored query vector instead took the
p95 from 17 s to under 3 s. The other half of the problem was running the
cross-encoder over 150 fused candidates; a shortlist of 30 does the same job.

---

## 7. Deployment

The service is a plain FastAPI app with a static browser UI beside it. Three
ways to run it, in increasing order of permanence:

| | command | good for |
|---|---|---|
| local | `fieldnote serve` | a laptop on a bench |
| LAN | `fieldnote serve --host 0.0.0.0` | a shop floor, tablets on wifi |
| published | `docker compose up -d --build` | a VPS, a cluster, a demo |

The Docker image is deliberately plain: CPU-only torch (the CUDA build is 2 GB
larger and would be unused), models baked in at build time so the first
request is not a download, a non-root user, a healthcheck, and the corpus and
index built on first start into a volume.

**A note on the environment this was built in.** The machine the project was
developed on is itself a guest without nested virtualization, so Docker
Desktop's Linux engine cannot start there - WSL2 needs the host to expose
virtualization to the guest. The compose file validates
(`docker compose config`), the Dockerfile is written for a standard
`python:3.11-slim` base, and `scripts/docker_up.sh` / `.ps1` wrap the whole
build-healthy-tunnel sequence into one command. The live link that was
published during development was served directly by the process behind
`cloudflared`, from exactly the same code the container runs.

---

## 8. What I would do next

- **A real corpus.** Everything above is measured on a synthetic one. The
  first thing I would change is the figure detection: real manuals have
  figures in every orientation, and the region cutter is the part that would
  suffer most.
- **A VLM in the loop for charts with no labels.** The OCR-plus-geometry
  path reads a *labelled* value. Reading a curve's value at an arbitrary
  point needs a model that can interpolate - and the answer should be
  labelled as an estimate.
- **Table structure recovery.** The current table handling uses raw OCR
  geometry. A real table needs row and column detection, and the same
  questions asked of a table with merged cells would fail.
- **Cross-encoder fine-tuning.** The eval's failures were mostly cases where
  a general-purpose relevance model did not know HVAC. A model fine-tuned on
  service questions would close the gap that the lexical layer is currently
  covering.
- **A second opinion on the answer.** Not a bigger model - a check that the
  cited crop actually contains the value that was quoted, before the answer
  leaves the building.
