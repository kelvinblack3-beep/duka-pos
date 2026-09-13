# Testing

## Milestone 0

`tests/test_environment.py` originally checked that the `duka_pos` package
imported and contained *only* `__init__.py`. That second assertion was
intentionally replaced in Milestone 1 (see ENGINEERING_LOG.md) once
business-logic modules were added.

## Milestone 1

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -v
```

64 tests, all passing as of the M1 engineering log entry, covering:

- database initialization, pragmas, and transaction rollback
  (`test_db.py`)
- product creation/retrieval, units, stock addition, weighted quantity
  (`test_products.py`)
- the locked weighted rice acceptance scenario: 1.35 kg → 21600 cents
  total, 48650 milli-kg remaining stock, 5400 cents gross profit
  (`test_sales_rice.py`)
- idempotent sale submission via `client_reference` (`test_idempotency.py`)
- atomic rollback of the whole sale on insufficient stock or a missing
  product (`test_rollback.py`)
- invalid quantity, invalid money, non-exact line totals, unsupported
  payment methods, empty sales (`test_validation.py`)
- the FastAPI HTTP layer end-to-end, including error status codes
  (`test_api.py`)

## Not yet written

- Authentication / roles
- Payment states other than cash (MPESA/CARD/OTHER are modelled in the
  schema but explicitly rejected by the domain layer in M1)
- Integration tests against Daraja or eTIMS
- Cashier UI tests
- Concurrent-write / multi-terminal load tests

Do not record those as TESTED until the tests exist and have been run.
