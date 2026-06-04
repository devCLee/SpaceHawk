# Stage 3 — render load test & payload budget

Validates the roadmap KPI of **≥10,000 objects** at interactive rates and sets
the streaming payload budget (dev-plan Stage 3 testing; §4.1).

## Running

```
npm run load-test --workspace apps/web
```

Benchmarks the per-tick SGP4 cost (the scalability bottleneck the Web Worker
offloads — `apps/web/src/app/workers/propagation.worker.ts`) at 10k / 20k / 30k
objects and prints the binary state-payload budget. Exits non-zero if a per-tick
propagation exceeds the budget, so it can gate CI.

## Budget

- **Per-tick propagation:** ≤ 100 ms per 10k objects. At the 1 Hz update cadence
  this keeps the worker thread ≳90% idle, leaving headroom for the main thread
  to do only GPU point writes.
- **State payload:** stream positions as `Float32` (lon/lat/alt = **12 B/object**)
  rather than per-satellite JSON/HTML (§4.1). ~352 KB per snapshot for 30k
  objects; ~117 KB for 10k. `Float64` doubles this and is unnecessary for
  display precision.

## Reference result (local dev machine)

| objects | parse ms | propagate ms | Float32 payload | budget |
|--------:|---------:|-------------:|----------------:|:------:|
| 10,000  | ~41      | ~34          | 117 KB          | PASS (≤100 ms) |
| 20,000  | ~63      | ~24          | 234 KB          | PASS (≤200 ms) |
| 30,000  | ~74      | ~34          | 352 KB          | PASS (≤300 ms) |

Absolute numbers are machine-dependent; the **budget gate** is the contract.

## Rendering notes (manual, needs a browser)

FPS / GPU-memory at 10k–30k and globe visual-regression are verified in-browser
against the `PointPrimitiveCollection` renderer (not per-object `Entity`,
§4.3) — out of scope for this headless CPU/payload gate. Capture them during QA
on the deployed dev enclave.
