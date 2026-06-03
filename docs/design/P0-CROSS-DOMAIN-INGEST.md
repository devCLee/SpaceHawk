# P0 Design — Cross-Domain / Data-Diode Ingest

**Status:** Stage 0 design artifact (accredited-in-principle target). The program's
**longest pole** — accreditation engagement starts at **M0**, not M3 (roadmap O7).
**Drivers:** roadmap P0 ("cross-domain ingest design accredited-in-principle");
dev-plan §4.6, §5 Stage 0/2 (the diode must be live before Space-Track crosses in).

## 1. Problem

External SDA feeds (Space-Track, Celestrak, DISCOS, Leolabs) live on lower-trust
networks. The operational enclave is air-gapped/high-side. We need a **one-way,
accredited** path to bring catalog/CDM/TLE data *in* without any return channel and
without weakening the enclave.

## 2. Design principles

- **One-way transfer only.** A hardware **data diode** (or accredited cross-domain
  solution, CDS) enforces physical/sanctioned unidirectionality — low-side → high-side.
- **Design to an already-accredited pattern.** Do not invent a diode; adopt an
  accredited diode/CDS product and pattern (roadmap risk #3) to de-risk accreditation.
- **Validate at the boundary.** All crossing data is schema-validated and
  content-checked (CCSDS/OMM canonical model, see `../data-model/CANONICAL-OBJECT-MODEL.md`)
  on the high side before it touches the catalog.
- **Source authentication & consistency bounds.** Guard against spoofed/poisoned TLEs
  (roadmap P2a risk): authenticate sources and cross-check across feeds before trust.

## 3. Reference flow

```
[low-side collector]                  DIODE / CDS                 [high-side enclave]
 Space-Track / Celestrak  ──pull──>  guard + one-way  ──>  validation+normalize ──> catalog
 DISCOS / Leolabs                    (no return path)        (canonical model)       (Postgres)
```

- **Low side:** authenticated pollers fetch from the external APIs (credentials never
  cross into the enclave).
- **Diode/guard:** schema/type/size filtering; allow-list of message types
  (SATCAT/GP/CDM/TIP); one-way only.
- **High side:** the Orbital Engine's ingestion layer normalizes to the canonical
  model, applies source-authentication/consistency checks, and upserts.

## 4. Sequencing constraints (hard rules)

- The diode path **must be operational before Space-Track ingest crosses into the
  enclave** (dev-plan Stage 2 hard-ordering rule (a)).
- Mirrors (`../infra/OFFLINE-SUPPLY-CHAIN.md`) cover *build/runtime* dependencies; the
  diode covers *operational data*. They are independent and neither bypasses the other.

## 5. Open items for the ARB

- Select the accredited diode/CDS product + pattern to design against.
- Confirm the allow-listed message types and the high-side validation owner.
- Agree the accreditation milestones (engagement starts M0; accredited-in-principle by
  the P0 gate; full accreditation tracked into Stage 5).
