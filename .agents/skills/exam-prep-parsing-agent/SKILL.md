---
name: exam-prep-parsing-agent
description: Use when parsing exam-prep books, provider PDFs, SchweserNotes, FRM/CFA-style materials, or when output shows contents pages, OCR-spaced text, junk cards, stale hierarchy, or model-invented section titles.
---

# Exam Prep Parsing Agent

## Core Rule
Use the book's explicit structure as the source of truth. Local parsing creates hard boundaries; the model may only enrich bounded sections after the hierarchy is fixed.

## Required Order
1. Extract text locally, preferring PyMuPDF for PDFs.
2. Preserve physical page numbers.
3. Detect exact hierarchy markers before any LLM call:
   - `STUDY SESSION n - title`
   - `READING n`
   - `MODULE n.n: title`
   - `EXAM FOCUS`
   - `KEY CONCEPTS`
   - `MODULE QUIZ n.n`
   - `ANSWER KEY FOR MODULE QUIZZES`
4. Exclude front matter and navigation pages:
   - welcome/preface
   - contents/table of contents
   - readings and learning objectives
   - copyright/disclaimer/index-only pages
   - contents continuation pages listing `Exam Focus`, `Key Concepts`, and `Answer Key` without real LO/body content
5. Build sections only from real learning pages.
6. Store source page range and original source text for every section.

## Workbook Section Contract
For FRM/CFA/Schweser-style books, sections should follow:

`Book -> Study Session -> Reading -> Module`

The parser must treat this as a hard boundary contract, not a suggestion. A real
`MODULE n.n` marker starts exactly one module section. That section may span its
body pages plus its correlated exam-focus, key-concepts, module-quiz, and
answer-key support blocks, but it must never merge into a neighboring module.

Each module section may include only these student-facing source blocks:
- key concepts from `KEY CONCEPTS` that match the module's LO IDs
- module quiz source questions with the exact same module quiz number
- answer key content with the exact same module quiz number

`EXAM FOCUS` is reading-level context only. It may guide fallback metadata for a
reading that has no modules, but it must not be copied into every module section.
For Schweser/FRM-style modules, the study card summary must come from the matched
LO key-concept text, not from the broad reading-level `EXAM FOCUS` paragraph.

Body text can be retained as source context, but should not become a noisy study card unless needed for the module's concept extraction.

## Mandatory Workbook Blocks
- If a `MODULE QUIZ n.n` marker exists in the source, module `n.n` must store a `MODULE QUIZ n.n` block.
- If `ANSWER KEY FOR MODULE QUIZZES` contains `Module Quiz n.n`, module `n.n` must store only that matching answer-key block.
- If `KEY CONCEPTS` contains `LO n.x` blocks and module `n.n` lists LO `n.x`, module `n.n` must store those matching key-concept paragraphs.
- Do not store unrelated `LO n.x` blocks in neighboring modules.
- Do not store neighboring `MODULE QUIZ m.m` or answer-key blocks in module `n.n`.
- Do not use a whole reading-level answer key as fallback for a missing module answer key.
- Missing one of these correlated blocks is a parse failure unless the block is absent from the source pages.
- Do not summarize module quizzes into concepts; preserve the question style as source context for quiz generation.
- Do not use answer-key explanations as the primary study summary; use them as answer evidence and style guidance.
- A reprocess action must invalidate stale study sections and rebuild from the raw PDF/text hierarchy.

## Correlation Rules
- Build a module-to-LO map from the module body before splitting key concepts.
- Segment `KEY CONCEPTS` by `LO n.x`; attach only segments whose LO IDs belong to that module.
- If a module's detected LO set has a gap inside its own range, such as `LO 1.a`
  and `LO 1.d`, and the official `KEY CONCEPTS` source contains `LO 1.b` and
  `LO 1.c`, include those contiguous missing LO blocks in that module. This is
  a hard recovery rule for OCR/body-heading gaps, not permission to invent LO
  content.
- Never attach an entire reading-level `KEY CONCEPTS` block to every module when LO boundaries exist.
- Pair `MODULE QUIZ n.n` only with `MODULE n.n`; do not leak neighboring module quizzes into the section.
- Pair `ANSWER KEY FOR MODULE QUIZZES -> MODULE QUIZ n.n` only with `MODULE n.n`.
- Source links for a study section must open at the module heading page, not the reading start page, exam-focus page, key-concepts page, or answer-key page.
- Use answer-key and key-concept pages as supporting page range only; they must not replace the module start anchor.
- If key concepts have no LO markers and the reading has only one module, attach the block to that module.
- If key concepts have no LO markers and the reading has multiple modules, prefer keeping them as reading-level support rather than duplicating them into every module.

## Title Rules
- Never create a section title from a sentence.
- Never use contents-page titles as real study sections.
- Never let a stale study session from the table of contents carry into real readings.
- Preserve exact reading/module order from the book.
- Join wrapped all-caps title lines only when they are clearly title continuations.
- Do not append first body subheadings to module titles.

## LLM Boundary
Never send the full PDF to the model after ingestion. Send one bounded module/reading section at a time, with token limits. The model must not invent hierarchy, page ranges, quizzes, answer keys, or exam weights.

## Quality Gates
Reject or reprocess output if:
- preface, contents, or learning-objective pages appear as study cards
- OCR-spaced tokens appear in titles or terms
- terms include generic words like `could`, `process`, `risk` without concept context
- a module title contains a body heading
- a section lacks source page range
- a visible internal id appears in a title, concept, recommendation, or button label
- a module that appears in the source, such as `Module 2.2`, is absent from the parsed module list
- a module quiz or answer-key block exists in the PDF but is missing from that module's stored source text
- generated quiz style ignores the module quiz format in the source

## FRM Part I Guardrail
If the Part I exam weighting table is image-only, preserve the page text and add the canonical rows:
- Foundations of Risk Management: 20%, 20 questions
- Quantitative Analysis: 20%, 20 questions
- Financial Markets and Products: 30%, 30 questions
- Valuation and Risk Models: 30%, 30 questions
