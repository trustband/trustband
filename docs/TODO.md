# TrustBand — TODO & Roadmap

Working notes for after the hackathon submission. Not a public-facing doc.

---

## 1. Making this repo public (planned)

Current state (updated 2026-06-17):

- [x] Created the GitHub org **`trustband`** (free plan).
- [x] Transferred the repo to **`trustband/trustband`** (still **private**).
- [x] Invited **BolynWang** as a repo collaborator (write access; pending accept).
- [ ] (optional) Add BolynWang as a formal **org member** — needs `admin:org` scope
      (`gh auth refresh -h github.com -s admin:org`, then re-run the membership PUT) or the
      org's People → Invite member page.
- [ ] **Rotate the OpenAI-format key** that was pasted in chat (user opted to keep it for now; rotate before sharing more widely).
- [x] Repo is **public** now (`trustband/trustband`); CI (ruff + mypy + pytest + bench) is green.

Note: a **free** org has no `internal` visibility (that is Enterprise-only). "Org-internal"
here means the repo stays **private** and the members/collaborators you add can see it.

Reference commands (`gh` CLI):

```bash
# Option A — transfer the existing repo into the org, then set internal visibility
gh api repos/<your-user>/trustband/transfer -f new_owner=<org>
gh repo edit <org>/trustband --visibility internal   # "internal" = visible to org members (org-owned repos)

# Option B — create fresh under the org and push
gh repo create <org>/trustband --private --source=. --remote=origin --push

# Add a member
gh api -X PUT orgs/<org>/memberships/<github-username> -f role=member
```

**Before flipping to internal/public — checklist:**
- [ ] Rotate any API key that was ever used during development (the OpenAI-format key was pasted in chat; rotate it on the provider).
- [ ] Re-confirm no secrets in the working tree or git history (`git log -p | grep -i -e sk- -e api_key`; already verified clean — keys live only in `~/.config/secrets/api-keys.env`, outside the repo).
- [ ] Keep `.env` and the secrets file out (they already are: `.env` is gitignored, secrets file is outside the repo).
- [ ] Decide whether to keep the provider/proxy name out of the repo (currently kept generic — only env vars).

---

## 2. Future improvements (from the review)

### High leverage — for the Band hackathon specifically
- [ ] **Make ≥1 agent a real Band peer.** Today all 7 agents run in-process and the bus posts to a Band room as a transcript. Run e.g. the Coder as a separate Band participant (Claude Code / Codex via Band's adapter) so it is genuine cross-framework, cross-process A2A — that is Band's actual pitch. (The **human** is already a real Band peer who approves live in the room; the remaining step is making one of the *agents* a separate cross-process Band participant.)
- [x] **Live Band room run** — DONE (2026-06-17). Full 7-agent pipeline ran live over a real Band room with `--llm real` (gpt-5.4-high): every handoff + structured-context message posted to Band, the orchestrator posted the approval request, a **real human approved in the band.ai UI**, and `BandBus._read_decision` parsed it → merged. Verdict TRUSTWORTHY, 0 regressions. Surfaced + fixed three real Band server rules (each message needs ≥1 mention, `cannot_mention_self`, and agents can't self-join an existing room — so we add the human peer as a participant of an agent-created chat). Artifact: `artifacts/BUG-1/PR.md`.
- [ ] **Demo video** (2–4 min): a live real-model run, ideally over a real Band room. The strongest single artifact for judging.
- [ ] **Real-LLM benchmark**: run a few scenarios with `--llm real` and capture the numbers. The current `bench` is canned/deterministic (measures the harness, not model quality).

### Robustness / product
- [x] **Cost guardrail** — DONE. `BudgetedLLM` caps completions per run (`--max-llm-calls`, default 30) and raises instead of silently spending.
- [ ] **Diff/edit-based patches** instead of full-file replacement — scales to large real files, less token cost, no risk of the model dropping code.
- [ ] **Reproducer test-quality check**: confirm the authored failing test fails for the right reason (guard against trivially-true tests that would hollow out the "trust" thesis).
- [ ] **Verifier scoping**: run only affected tests on large repos instead of the whole suite each revision.
- [ ] **`--json` output** for the CLI, so TrustBand can be a real CI step.

### Polish
- [ ] Dedup the baseline pytest run (the Reproducer and the orchestrator both compute it once).
- [ ] Consider raising `--cov-fail-under` (currently 80; actual coverage is 93%).
- [ ] Rendered architecture image (PNG/SVG) for the README and the demo video, not just the mermaid source.
