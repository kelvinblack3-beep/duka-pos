# Third-party licenses — Duka POS

This project may study and reuse legitimate open-source ideas and components.
Third-party software is **not** our proprietary code.

Before adding a dependency:

1. Identify the license.
2. Record it in this file.
3. Do **not** copy GPL or AGPL code into this repository without an explicit
   license review and architect approval. GPL/AGPL can force the whole POS
   to be distributed under the same terms.

## Policy

- Prefer MIT, BSD, Apache-2.0, or similarly permissive libraries.
- Record name, version constraint, license, and homepage.
- Transitive dependencies are accepted from the declared direct packages;
  a lockfile may be added in a later milestone. Until then, record direct
  dependencies here and review new ones when they are introduced.
- Do not vendor third-party source unless there is a documented reason.

## Direct dependencies declared in Milestone 0

These packages are listed in `pyproject.toml`. Declaring them is not a claim
that Duka POS implements a FastAPI application yet.

| Package | Constraint | License | Notes |
|---|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | `>=0.115.0` | MIT | HTTP framework; unused in M0 code |
| [Uvicorn](https://github.com/encode/uvicorn) | `>=0.32.0` (`[standard]`) | BSD-3-Clause | ASGI server; unused in M0 code |
| [pytest](https://github.com/pytest-dev/pytest) | `>=8.0.0` (optional extra `dev`) | MIT | Test runner |

License texts are those published by the upstream projects. This table is
based on upstream LICENSE files as commonly distributed; it is not legal
advice.

## Notable transitive packages (informational)

Pulled in by the direct dependencies above when installed. Not all will be
imported by M0 code.

| Package | Typical license |
|---|---|
| Starlette | BSD-3-Clause |
| Pydantic | MIT |
| anyio | MIT |
| click | BSD-3-Clause |
| h11 | MIT |
| httptools | MIT |
| uvloop | MIT |
| watchfiles | MIT |
| websockets | BSD-3-Clause |
| python-dotenv | BSD-3-Clause |
| PyYAML | MIT |

## Project license

The Duka POS application license has not been chosen. Until it is, treat the
repository as private unpublished source. Do not relicense third-party code.
