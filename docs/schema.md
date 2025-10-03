# data/schema.md

**Rigveda_Visualizer — Dataset schema & parsing rules**

This document defines the canonical dataset format used by the Rigveda_Visualizer app and the scripts that produce it. Keep `data/raw/` untouched; the parser converts raw files into `data/processed/rigveda_processed.jsonl` where each line is one JSON object representing a single verse (or logical stanza grouping).

---

## 1. Purpose

Provide a deterministic, stable, and minimal schema that supports:

* verse-level browsing (Sanskrit, transliteration, translation)
* metadata-driven filtering (mandala, sukta, deity)
* easy merging of Griffith (public-domain) translations
* reproducible parsing and testing

---

## 2. File format

* **Output:** newline-delimited JSON (JSONL) — `data/processed/rigveda_processed.jsonl`
  Each line → one JSON object (one verse/stanza).
* **Encoding:** UTF-8.
* **Line ending:** `\n`.

---

## 3. Canonical record (fields)

Each JSONL record **must** contain these fields (and follow the types):

```json
{
  "id": "RV-01-001-01",
  "mandala": 1,
  "sukta": 1,
  "verse_index": 1,
  "verse_id": "1.1.1",
  "deity": "Agni",
  "rishi": "Atri",
  "sanskrit": "अग्निमीळे पुरोहितं ...",
  "transliteration": "agni mīḷe purohitaṃ ...",
  "translation": "I hymn Agni, the household priest ...",
  "metre": "Trishtup",
  "source_file": "rigveda_mandala_1.json",
  "page_number": 12,
  "notes": null
}
```

### Field definitions

* **`id`** *(string, required)*
  Unique stable identifier for this record. Recommended format: `RV-<mandala 2 digits>-<sukta 3 digits>-<verse_index 2 digits>` (example: `RV-01-001-01`).

* **`mandala`** *(integer, required)* — Mandala number (1–10 for Sprint 1).

* **`sukta`** *(integer, required)* — Sukta (hymn) number within the mandala.

* **`verse_index`** *(integer, required)* — Verse or stanza index within the sukta. Start at 1.

* **`verse_id`** *(string, optional)* — Human-friendly dot notation: `mandala.sukta.verse`, e.g. `1.1.1`.

* **`deity`** *(string | null)* — Deity or addressed divinity (e.g., `Agni`, `Indra`). `null` if unavailable.

* **`rishi`** *(string | null)* — Named seer/author if present. Else `null`.

* **`sanskrit`** *(string, required)* — Original Sanskrit text (Devanāgarī or available script) for the verse/stanza. Preserve line breaks as in source but trim extraneous whitespace.

* **`transliteration`** *(string | null)* — IAST (or other chosen) transliteration. If not generated yet, set to `null`.

* **`translation`** *(string | null)* — Griffith or other translation. `null` if not merged.

* **`metre`** *(string | null)* — Metre name if available (e.g., `Triṣṭubh`, `Gāyatrī`). Else `null`.

* **`source_file`** *(string, required)* — Filename in `data/raw/` used to create this record.

* **`page_number`** *(integer | null)* — Page number from helper mapping when available.

* **`notes`** *(string | null)* — Parser warnings / ambiguous extraction notes.

---

## 4. Validation rules / best practices

* **Required fields:** `id`, `mandala`, `sukta`, `verse_index`, `sanskrit`, `source_file`.
* Parsers should **raise errors** or emit `notes` for missing required fields.
* `id` **must** be unique across the file. Add a check in tests.
* Normalize all strings to **Unicode NFC**. Trim leading/trailing whitespace.
* `page_number` if present must be a positive integer.
* If the raw source groups multiple logical verses into one block, **preserve that grouping** (do not auto-split unless explicit markers exist).

---

## 5. Extraction heuristics / regex tips

Implement deterministic heuristics in `scripts/utils.py` — conservative by default.

* **Header detection:** header info typically appears in the first 1–3 non-empty lines of `text`. Use these lines to try extracting `deity`, `rishi`, and `metre`.

  * Split `text` into lines and treat the first 1–3 non-empty lines as `header_lines`.
  * Look for common Devanāgarī deity tokens or Latin equivalents.

* **Verse splitting:**

  * If verses are numbered (`1.`, `(1)`, `१.`), split on markers.
  * If not numbered, treat the remaining block as a single stanza and set `verse_index` accordingly.

* **Sanskrit vs. translation detection:**

  * If a line contains mainly Devanāgarī characters (`\u0900-\u097F`), mark it as `sanskrit`.
  * If a line is primarily ASCII/Latin, consider it a candidate for transliteration or translation — but be conservative about overwriting a `translation` field.

* **Transliteration generation (optional):**

  * Use a deterministic library (e.g., `indic-transliteration`) to create IAST transliteration if desired. If unsure, leave `transliteration` as `null`.

---

## 6. Griffith translation mapping

* Keep Griffith translations in `data/translations/griffith/` as CSV or JSONL with explicit keys: `mandala`, `sukta`, `verse_index`, `translation_text`.

* Example CSV header:

  ```csv
  mandala,sukta,verse_index,translation_text
  1,1,1,"I hymn Agni, the household priest..."
  ```

* `scripts/merge_translations.py` should match by `(mandala, sukta, verse_index)` and populate `translation`. If a translation is missing, leave `translation` `null` and append `notes: "griffith_missing"`.

---

## 7. Provenance & versioning

* Add `data/processed/metadata.json` when exporting a snapshot, example:

```json
{
  "dataset_version": "v0.1.0",
  "generated_at": "2025-10-03T07:00:00+05:30",
  "source_files": ["rigveda_mandala_1.json", "..."],
  "translator": "griffith (not merged yet)"
}
```

* When parser logic changes incompatibly, increment `dataset_version`.

---

## 8. Tests & sanity checks (minimal)

`tests/test_parser.py` should include:

* Count check: number of mandalas parsed equals files in `data/raw/` (for 1–10).
* Unique `id` check: no duplicates.
* Required field checks on a random sample of records.
* Log deity coverage; if > 50% `null` per mandala, adjust heuristics.

Run tests with:

```bash
python -m pytest tests/test_parser.py
```

---

## 9. Example records

**Raw sample** (source `text` fragment):

```
अग्निमीळे पुरोहितं यज्ञस्य देवम् ऋत्विजम् ।
होतारं रत्नधातमम् ॥
```

**Parsed JSONL line**:

```json
{"id":"RV-01-001-01","mandala":1,"sukta":1,"verse_index":1,"verse_id":"1.1.1","deity":"Agni","rishi":"Atri","sanskrit":"अग्निमीळे पुरोहितं यज्ञस्य देवम् ऋत्विजम् ।\nहोतारं रत्नधातमम् ॥","transliteration":null,"translation":null,"metre":null,"source_file":"rigveda_mandala_1.json","page_number":12,"notes":null}
```

---

## 10. Parser invocation & repo expectations

* Main parse command:

```bash
python scripts/parse_rigveda.py --input-dir data/raw --output-file data/processed/rigveda_processed.jsonl
```

* Merge translations:

```bash
python scripts/merge_translations.py --dataset data/processed/rigveda_processed.jsonl --griffith data/translations/griffith/griffith_map.csv --out data/processed/rigveda_with_translations.jsonl
```

* Streamlit app expects `data/processed/rigveda_processed.jsonl` (or translations-merged file) at startup.

---

## 11. Notes / edge-cases observed (Sprint 1)

* Headers vary across mandalas — parser should be conservative.
* Some source entries contain English fragments — do not overwrite `translation` unless a trusted mapping matches.
* Keep `data/raw/` immutable to make parsing reproducible.

---

## 12. Future improvements (optional)

* Add `language` field for multiple translations.
* Add `verse_hash` for dedup checks between editions.
* Add per-verse `audio_url` if including recitations.

---

*End of schema.*
