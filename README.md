# Fab4 — AI × Antibodies Hackathon (Oslo, 14 Nov 2026)

One-day hackathon at BI Startup Village. Task released 09:30, **pitch + repo due 18:00**.

> The official task is released on the day and lives in the event Slack. Once we have it,
> it goes in [`docs/task.md`](docs/task.md) verbatim and this README gets the one-paragraph
> version. Everything below is pre-read distilled from the organizers' participant guide.

## How we are judged

| Criterion | Weight | What it means |
|---|---|---|
| **Judgment** | 40% | Clear reasoning behind the molecules we chose |
| Execution | 20% | A reproducible pipeline in this repo |
| User fit | 20% | What the design is for, and who needs it |
| Path to value | 20% | A credible route to real use — molecule or method |

Two extra notes from the guide: a judge runs our skill/pipeline on a **case we have not seen**,
and every team must hand in **score tables saying where each score came from**.

Prize conditions worth knowing: the monetary prize (Apheris + OpenFold, 3,000 USD) requires
**Apheris' version of OpenFold in our pipeline**. AMASS gives 100 USD credits for the most
creative use of AMASS. Adaptyv tests ~5 designs per team (VHH, Fab or scFv — not whole IgG);
results are published on Proteinbase under ODC-BY.

## The work, in four steps

1. **Generate** — hundreds of VHH / scFv / Fab candidates, de novo or by editing a known binder.
2. **Score** — structure, interface, affinity and physics-flavoured models.
3. **Filter** — pick **≤ 10** to submit, on more than one score; developability is a real filter here.
4. **Test** — Adaptyv does this after the event, not us.

Start wide: every step throws candidates away. Confidence scores (pLDDT, ipTM, PAE, ipSAE) rank
candidates; none of them is an affinity. Re-score binding after any liability fix.

## Repo layout

```
docs/        task.md (the official brief), hackathon-brief.md (pre-read), decision-log.md
pipeline/    the reproducible run: generate -> score -> filter
scripts/     one-off tools and glue
data/        inputs: target structures, reference sequences (large files stay out of git)
designs/     candidate sets + submission.csv (the ≤10 we put forward)
reports/     score tables, figures, pitch material
notebooks/   exploration
```

## Tools we have access to

- **JapanFold** — structure prediction + binder design workbench (RFD4-Proteina et al.), https://japanfold.aiand.com/
- **Nebius** — model catalog / GPUs, https://forge.nebius.cloud/models/
- **Apheris Foundry** — incl. their OpenFold build (**required for the cash prize**)
- **AMASS** — literature search and verification, https://amass.tech/oslo-ai-antibodies-hackathon
- **Claude Max credits** — agent glue across all of the above

## Ground rules

All outputs and this repository must be created during the hackathon. Pre-existing startup or
business ideas must be disclosed to the organizers. Team max 5.

## Links

- Event site: https://oslo-ai-antibodies-hackathon.vercel.app/
- Participant guide: https://oslo-ai-antibodies-hackathon.vercel.app/participant_guide
- Competition terms: https://proteinbase.com/competitions/anthropic-adaptyv-2026/terms
