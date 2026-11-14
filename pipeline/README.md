# Pipeline

One command per stage, each writing a file the next stage reads, so a judge can run it on a
target we have never seen. Record model version and seed in every output.

```
generate/   target + contig -> candidate sequences/structures   (JapanFold, RFD4-Proteina, inverse folding)
score/      candidates -> structure, interface, affinity-proxy and developability scores
filter/     scores -> ranked table -> designs/submission.csv (<= 10)
```

Rules we hold ourselves to:

- Every score column names its model and version. No anonymous numbers.
- Multiple seeds, and the spread reported — not the best run.
- Re-score binding after any liability fix.
- One unseen case run end to end before the pitch. The judges will do this to us.
