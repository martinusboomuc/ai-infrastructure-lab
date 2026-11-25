# ADR-0025: A test bench in Nexus that scores real held-out cases as test traffic

**Status:** Accepted
**Date:** 2026-11-25

## Context

The owner wants to use the bank's models, not only read about them. That means picking an
applicant or a transaction, changing a field, and seeing what the production model decides and
why. MLflow shows the evidence for each version but cannot score a case. The API can, but needs
a key and a hand-built request with the history ADR-0009 and ADR-0023 require.

Three things had to be settled.
- **Where the cases come from.** They must be real, in the API's request shape, with their
  history, and not cases the model trained on. Nexus runs with 256 MiB of memory; the Fraud
  replay file is 518 MB decompressed.
- **How the requests are kept out of monitoring.** Drift (ADR-0018) read every logged prediction
  by the production version, whatever its source. An edited applicant is not the population the
  model serves.
- **Which credentials Nexus holds.** The browser must never hold the API key.

## Decision

1. **Examples are a small slice of the replay requests, with their known outcome.**
   - `python -m bankml.monitoring.examples --domain <d>` runs on `docker-01` and writes
     `<domain>/examples.json` to the private `replay` container: 50 cases, 15 of them positive.
   - They are test-split cases the model never trained on, already in the request shape, with
     their history.
   - Positives are over-represented on purpose: about 8% of applicants default and 0.4% of
     transactions are fraud, so an evenly spaced slice would hold almost none. The bench is for
     trying cases, and says so; measuring the model is the performance job's work.
2. **The outcome feed now covers both domains.** Each config names its request id field
   (`request_id_field`: `applicant_id`, `transaction_id`). The outcome table and its lookups key
   ids as strings, because Fraud's are hashes.
3. **The API accepts `X-Traffic-Source: test`.** The prediction is logged like any other, with
   that source. Drift skips it; performance reads only `replay` already.
4. **Nexus holds two credentials, both narrow.**
   - A `nexus` client key (ADR-0017), in the k3s Secret `nexus/bankml-api-key`. The backend calls
     the API; the browser calls only the backend.
   - A read-only SAS URL per domain for that domain's `examples.json` blob, in
     `nexus/bankml-examples`. Nexus holds no account key and can read nothing else.
5. **Only the scored object's own fields are editable**: the applicant, or the transaction. The
   history is sent as recorded. An edited case shows its outcome as unknown.

## Alternatives considered

**Let Nexus read the replay request files.**
- It lost on memory and on scope: 518 MB decompressed for Fraud, and a credential that reads
  every request and outcome.

**Build cases from the raw data in Nexus.**
- It lost because Nexus would need the raw files, which stay on `docker-01` (ADR-0014), and its
  own copy of the feature history logic, which is exactly the skew ADR-0009 avoids.

**Log test requests as `live`.**
- It lost because drift would compare typed and edited applicants with the training population.

**Do not log test requests at all.**
- It lost because every prediction the API serves is in its log, which is the audit trail. The
  source says what each one was.

**Call the API from the browser with the key.**
- It lost because the key would be readable by anyone who opens the page.

## Consequences

- **A case can be scored from Nexus** with its score, threshold, decision, reason codes, and what
  actually happened to it.
- **Two more credentials exist** and are listed in the credentials runbook. The SAS URLs are
  signed with the storage account key, so rotating that key invalidates them, as it does the
  backup SAS.
- **The examples need rebuilding** when the replay requests are rebuilt.
- **The API counts test traffic** in its request metrics. Only drift and performance skip it.
