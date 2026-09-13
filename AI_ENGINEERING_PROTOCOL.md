# AI engineering protocol — Duka POS

This project is built by a multi-AI team under a human owner. The protocol
exists so that generated code is inspected, tested, reviewed, documented,
and committed on purpose — not dumped into git.

## Source of truth

**GitHub is the single source of truth.**

AI conversation claims are **not** project state. The following are
authoritative:

- files in `kelvinblack3-beep/duka-pos`
- commits and branches
- tests that were actually run
- labels in `PROJECT_STATUS.md`

If a chat says “M-Pesa works” and GitHub has no tested Daraja adapter, M-Pesa
does not work.

Never claim something is implemented or tested unless it has actually been
implemented or tested in this repository.

## Roles

| Role | Actor | Authority |
|---|---|---|
| Lead architect / reviewer / integration authority | ChatGPT | Architecture, scope, milestone approval |
| Primary implementation engineer | Grok | Write code, tests, docs; commit working M-sized slices |
| Technical reviewer | DeepSeek | Review, debugging, alternative analysis, architecture critique |
| External research | Perplexity | Current Daraja, eTIMS, hardware, library, regulatory facts |
| Source of truth | GitHub | Actual project state |

The human project owner can override any AI.

Major architectural changes require lead-architect approval. Another AI must
not silently change the stack, the source of truth, or the milestone sequence.

## Honesty labels

Use exactly these words in status writing:

- **PLANNED**
- **IMPLEMENTED**
- **TESTED**
- **PRODUCTION-READY**

Do not mark PRODUCTION-READY because a unit test passed on a laptop.
Do not mark IMPLEMENTED because an ADR exists.

## Working rules

1. Build in small verified increments. Do not generate an unfinished POS.
2. Every feature: purpose → implement → test → review → document if needed → commit only when working.
3. Do not skip Milestone 0 / Milestone 1 sequencing set by the architect.
4. Do not invent M-Pesa, eTIMS, printer, or scale behaviour.
5. Do not commit secrets, tokens, private keys, or live Daraja/eTIMS credentials.
6. Do not copy GPL/AGPL code into this tree without license review.
7. Do not modify kifaa as part of this project.
8. Prefer simple modules over speculative frameworks.
9. Failed tests are reported as failures. Do not hide them.

## Git

Branches:

- `main` — stable
- `dev` — integration
- `feature/*` — work in progress

Do not push unverified production changes straight to `main` once M0 is in
place. Meaningful commit messages, for example:

```
feat: initialize local POS architecture
feat: add product management
test: add weighted product sale tests
fix: prevent duplicate sale submission
```

No fake commits. No “tests passed” unless pytest (or the named command) was run.

## Review expectations for AI-generated code

Before a slice is called done:

1. Inspect the diff. Does it match the approved milestone?
2. Run the tests. Paste the actual command and result into the engineering log when it matters.
3. Check that no secrets landed in git.
4. Update `PROJECT_STATUS.md` only for things that now exist.
5. Wait for architect review when the milestone says to stop.

## Integrations research

Perplexity (or equivalent current research) must be used before claiming:

- Daraja endpoint behaviour
- eTIMS legal/technical requirements
- a specific printer or scale protocol

Cached model memory is not a substitute for current provider documentation.
