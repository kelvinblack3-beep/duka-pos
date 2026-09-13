# M-Pesa (Safaricom Daraja) — M3.2 + M3.3

Status: **IMPLEMENTED** (sandbox-oriented HTTP client, callback, STK Push Query
reconciliation). Not claimed production-ready without live Safaricom validation.

## What is implemented

- OAuth client-credentials (`GET /oauth/v1/generate?grant_type=client_credentials`)
- STK Push / Lipa Na M-Pesa Online (`POST /mpesa/stkpush/v1/processrequest`)
- STK result callback (`POST /callbacks/daraja/stk`)
- STK Push Query reconciliation (`POST /mpesa/stkpushquery/v1/query`)
- Domain service `reconciliation.reconcile_payment`
- Authenticated manual reconcile (`POST /payments/{payment_id}/reconcile`)
- Phone normalization to `2547…` / `2541…`
- Provider refs: `MerchantRequestID`, `CheckoutRequestID`, `MpesaReceiptNumber`
- Correlation on callback and query (checkout, merchant, optional phone)
- Idempotent confirmation via M3.1 `confirm_payment_and_complete_sale`

## What is not implemented

- Live production cut-over validation
- Transaction Status API (requires initiator / SecurityCredential)
- C2B register URL / B2C / B2B
- eTIMS
- In-process scheduler / aggressive polling

## Configuration (env only)

See `.env.example`:

| Variable | Purpose |
|---|---|
| `DARAJA_ENVIRONMENT` | `sandbox` or `production` |
| `DARAJA_CONSUMER_KEY` | App consumer key |
| `DARAJA_CONSUMER_SECRET` | App consumer secret |
| `DARAJA_SHORTCODE` | Paybill / till shortcode |
| `DARAJA_PASSKEY` | Lipa Na M-Pesa Online passkey |
| `DARAJA_CALLBACK_URL` | Public HTTPS URL for STK results |
| `DARAJA_TIMEOUT_SECONDS` | Optional HTTP timeout (default 30) |

Never commit real credentials. Tokens are process-local only and never logged.

## Flow

1. `POST /sales` with `payment_method=MPESA` and `phone_number`
2. Local SQLite creates `PENDING_PAYMENT` / `PENDING` (no stock, no receipt)
3. **After commit**, STK HTTP runs; Checkout/Merchant IDs stored
4. Daraja later POSTs to `/callbacks/daraja/stk` **or** staff calls
   `POST /payments/{id}/reconcile` (STK Query) if callback was lost
5. Success → atomic confirm (amount check, stock, receipt, COMPLETED)

STK acceptance ≠ payment success. Only callback ResultCode 0 or STK Query
ResultCode 0 (with correlation) may confirm.

## Reconciliation notes

- Query uses the same OAuth + Lipa password construction as STK Push.
- If query omits amount metadata, local `payment.amount_cents` is used as the
  expected amount for confirmation (bound at STK time).
- Ambiguous / unknown ResultCodes leave the payment PENDING (no stock change).
- Callback and reconcile racing is safe: at most one stock deduction and one receipt.
