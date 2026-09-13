# KRA eTIMS

Status: **PLANNED**

Planned flow:

```
LOCAL SALE → LOCAL RECORD → eTIMS QUEUE → SUBMISSION → KRA RESPONSE → LOCAL SYNC STATUS
```

If KRA is unreachable, the till keeps the sale and retries later.

This folder has no adapter code, no OSCU/VSCU credentials, and no claim of
tax compliance. Do not add a fake eTIMS implementation.
