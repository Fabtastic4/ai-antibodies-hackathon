# SETUP — run these in order

Everyone on team-4 (6 people). Target: working by 11:00. Submission closes **18:00**.

Credentials live in the Slack folder (`Files from slack/extracted/participant-05/`). Never in git,
never pasted into chat, never into a prompt. Point tools at the file path.

---

## 1. Clone the repo

```bash
git clone https://github.com/Fabtastic4/ai-antibodies-hackathon.git
cd ai-antibodies-hackathon
```

Copy the Slack folder next to it yourself — it is gitignored and will never arrive via git.
Ask in Slack if you do not have `participant-05.zip` and `japanfold-oslo-hackathon-codes 4.txt`.

## 2. ONE HOME DIRECTORY, ONE GPU — WORK IN `~/<your name>`

Read this before you touch the VM. Per the Slack paste from Davide: **everyone in team-4 uses the
same user and the same key, so we all share one home directory and one H100.** Make a folder for
yourself and stay in it:

```bash
mkdir -p ~/josef && cd ~/josef     # use your own name
```

Do not write to `~` directly. Do not start a second GPU job without saying so in Slack — there is
one H100 for six people.

## 3. Connect to the VM

Download the key from the Bitwarden Send link in the team Slack channel (link not reproduced here
on purpose). Then, on macOS/Linux:

```bash
mv ~/Downloads/team-4 ~/.ssh/team-4
chmod 600 ~/.ssh/team-4
ssh -i ~/.ssh/team-4 hackathon@89.169.99.24
```

Windows: the same `ssh` commands work from PowerShell or WSL, just point `-i` at wherever you saved
the key. (TODO: confirm the Windows equivalent of `chmod 600` if ssh rejects the key file.)

| VM | |
| --- | --- |
| GPU | 1 × NVIDIA H100 |
| CPU / RAM | 16 vCPU / 200 GB |
| Disk | 500 GB |
| OS | Ubuntu 24.04 LTS |
| User / IP | `hackathon` @ `89.169.99.24` |

**The machines are shut down at the end of Saturday 14 November.** Anything you want to keep gets
copied off the VM and committed before then. Nothing on that disk survives the day.

## 4. Use what is already on the VM — do not reinstall it

Per the task PDF, every team machine ships with:

- **Claude Code**, with credits from Anthropic.
- **Apheris Foundry models as Docker images**, already downloaded. List them with
  `foundry-toolkit module list`; `Tutorial.html` (Hackathon VM tab) shows how to run each one.
- **RCSB MCP**, for fast access to known protein structures.
- **Read-only credentials for the hackathon data bucket**, `s3://apheris-oslo-hackathon`.
- **abguard**, the CLI that checks a design against the hard filters before submission.
  At `~/.local/bin/abguard` — a `uv` tool, **not** a Foundry Docker image, and on `PATH` in a
  **login shell only**. Scripts need `bash -lc "abguard ..."` or the absolute path, otherwise it
  looks missing. Do not reinstall it. Run the gate on every candidate:
  `bash pipeline/filter/gate.sh` — see [`abguard.md`](abguard.md).

Pull data onto the machine (example straight from the PDF):

```bash
aws s3 sync s3://apheris-oslo-hackathon/<folder> ./data
```

The organisers may add data or scripts to the bucket during the event. The RFD4-Proteina
step-by-step guide, example inputs and a ready-made HER2 script are in the bucket under
`rfd4-proteina/docs/` — open `Tutorial.html`.

## 5. Nebius Scientific AI — pick one of two ways

About 60 models are already hosted. Nothing to install, no GPU needed for them.

**Way 1, browser, ~2 min.** Open the `workbench_url` from `credentials.private.json` and sign in
with the login and password in the same file.

- In chat, **pick the model GLM 5.3 Flash**. The default one is slow for this.
- **Apps** lists the models you can use.
- **Workspace** is our bucket, with ~700 public example files including molecular-dynamics starters.

**Way 2, Claude Code, ~5 min.** Needs Python 3 and Claude Code. From inside the
`participant-05` folder:

```bash
bash agent/install.sh
export NEBIUS_CREDS="$PWD/credentials.private.json"
python3 ~/.claude/skills/nebius-scientific-ai/forge.py models
```

That last command prints the callable models and how long each takes. Then start `claude` in that
folder; it picks up the skills by itself (51 official model skills plus the `forge.py` client).
If you want to work in another folder, put the `export` line in your shell profile first or the
tools will say they cannot find a credentials file.

**Never ask Claude for the full model catalog.** That answer is ~930 KB and fills the whole
context. Use `forge.py models` and `forge.py schema <model>`.

Every run prints an id like `op-1234abcd`. Keep it:

```bash
F=~/.claude/skills/nebius-scientific-ai/forge.py
python3 "$F" runs
python3 "$F" wait op-1234abcd
python3 "$F" fetch op-1234abcd --dest results/run1
```

Never submit the same job twice — you only wait twice. First call to a model is the slow one
(the model has to load) and 16 teams share the queue, so **start long jobs early**.

## 6. JapanFold

The key is in `japanfold-oslo-hackathon-codes 4.txt` in the Slack folder. Do not copy it into any
file in this repo, and do not paste it in chat.

Reason to bother: JapanFold is the only route to **RoseTTAFold3, OpenDDE and AF2-IG**. It connects
as an MCP server to Claude Code and the models are then callable directly from Claude Code.

**Connect command** (confirmed 14 Nov against the live endpoint — the server returns it in its
own unauthenticated error, so this no longer needs the txt file):

```bash
export JAPANFOLD_API_KEY=...        # from the Slack txt; your shell only, never a repo file
claude mcp add --transport http japanfold https://api.japanfold.aiand.com/mcp \
  --header "Authorization: Bearer $JAPANFOLD_API_KEY"
```

`.mcp.json` in the repo root already declares it with `${JAPANFOLD_API_KEY}` expanded from the
environment, so exporting the variable is enough — a new Claude Code session picks it up and the
key stays out of the commit.

Every MCP tool is also plain HTTPS under `https://api.japanfold.aiand.com/v1` with the same
bearer header, so a job started in one place can be fetched anywhere with the same key.
`GET /v1/models` needs no key at all and lists every model with what past jobs billed.

**What it unlocks for our submission.** `af2ig` takes a designed complex — target coordinates
plus the binder sequence, which is what `results/cofold/*/model.cif` already is — and reports
**ipTM and interface pAE**, the two columns `rank.py` wants for axis 1 and that
`docs/tools-nebius.md` records as unobtainable on the hosted lane. With `write_pae: true` it also
returns the full PAE matrix, which JapanFold describes as the one Adaptyv's ipSAE pipeline reads.
`opendde-abag` co-folds antibody–antigen with `site` constraints, so a refold can be steered onto
the 19 HER2 epitope residues. Scoring all 18 folded designs costs about $0.09.

Driver and details: [`../viz/README.md`](../viz/README.md), `python3 viz/japanfold.py --check`.

## 7. AMASS — NEEDS AN OWNER, CLAIM IT NOW

Each team gets **$100 in API credits** and **one person per team claims them** at
platform.amass.tech. Nobody has claimed ours. Whoever does it, say so in Slack so we do not burn
two claims. AMASS searches papers, clinical trials, patents and drug records with plain-language
questions and links back to the source — useful for checking claims and for design leads.
(AMASS also picks the team with the best use of their platform for a separate prize.)

## 8. Git hygiene

`.gitignore` already excludes `*.private.json`, `credentials*.json`, `Files from slack/`,
`**/japanfold*codes*`, `*.pem`, `id_*` and `team-4*`.

The rule, no exceptions:

- Credentials come from the Slack folder. Never from git. Never pasted in chat or into a prompt.
- If you need to mention a value in a doc, write `<REDACTED - see Slack folder>`.
- Our submission is a public GitHub repository.

`results/` and `nebius-runs/` hold run ids and outputs with **no keys**, and we must show where
every score came from — so they **should be committed**.

> **Resolved 13:20 (W1).** The blanket `nebius-runs/` and `results/` ignores are gone, replaced by
> patterns that ignore only the blobs inside them (`*.cif`, `*.pdb`, `*.tar`, `*.gz`) so run ids
> and score tables commit normally. Verified: `credentials*.json`, `*.private.json`, `*.pem`,
> `id_*`, `team-4*` and `Files from slack/` are still ignored, including inside those folders.
> Nothing needs `git add -f` any more. Still run `git status` before every push.

Before `git push`, run `git status` and look at what is staged. One leaked key ends the day.

## 9. The five things that cost people time

From START-HERE.md:

| Symptom | Do this |
| --- | --- |
| A run looks stuck | It is **queued, not broken**. `forge.py status op-xxxx`. A first call can wait 15 min |
| "private storage is temporarily unavailable" | Platform hiccup. `forge.py resume op-xxxx`. Do **not** resubmit |
| The model refuses your input | `forge.py schema <model>` and fix the named argument. Do not try shapes at random |
| MD says "missing required fields: request" | Add `--wrap-request`. All five MD engines need it. Send the tar still gzipped |
| Python on a Mac cannot verify the certificate | Run `Install Certificates.command` from the Python folder in Applications |

Known failures from the resource map:

| Symptom | Action |
| --- | --- |
| Looks stuck | `forge.py status`. First call can wait 15 min |
| Private storage unavailable | `forge.py resume`. Do not resubmit |
| Input refused | `forge.py schema`, fix the named field once |
| MD missing request | `--wrap-request`. Send the tar still gzipped |
| OpenFold2 | Endpoint did not start (failed twice on 12 Nov, 55 min each). Use `openfold3` or `boltz2` |

Also from the resource map: `boltz2` returns **no ipTM** — do not report one. Start `rfd4-proteina`
and `mosaic` before the short folds. On the H100, drivers only: `uv pip install torch`, then
`torch.cuda.is_available()` must print `True`. Do not install a model that is already hosted
(NanoBodyBuilder2, ABodyBuilder3, AntiFold, ESM-IF1, IgBert, Chai-1, the ESM C / ESM-2 / SaProt
families are all hosted since 12 Nov).

## Stuck?

Apheris team on site for anything VM- or Foundry-shaped. Nebius mentor on site for platform jobs —
bring the run id.
