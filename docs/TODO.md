# TrustBand — TODO & Roadmap

Working notes for after the hackathon submission. Not a public-facing doc.

---

## 1. Making this repo public (planned)

This repo is **private** for now — it is a hackathon entry. The intended path:

1. Finish and submit the hackathon project on this private repo.
2. Create a GitHub **organization** (team/product org).
3. Move this repo under the org (transfer or re-push), then add members.
4. Set repo visibility to **internal** (visible to all org members) — or public when ready.

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
- [ ] **Make ≥1 agent a real Band peer.** Today all 7 agents run in-process and the bus posts to a Band room as a transcript. Run e.g. the Coder as a separate Band participant (Claude Code / Codex via Band's adapter) so it is genuine cross-framework, cross-process A2A — that is Band's actual pitch.
- [ ] **Live Band room run** (`--bus band --band-room <id>`): verify `BandBus._read_decision` (human-approval parsing) against the real API shape, then record it. The LLM path is live-verified; the Band-room path is not yet.
- [ ] **Demo video** (2–4 min): a live real-model run, ideally over a real Band room. The strongest single artifact for judging.
- [ ] **Real-LLM benchmark**: run a few scenarios with `--llm real` and capture the numbers. The current `bench` is canned/deterministic (measures the harness, not model quality).

### Robustness / product
- [ ] **Cost guardrail**: per-run LLM call cap / token budget. A real run makes ~4–9 large-prompt calls; nothing bounds spend today.
- [ ] **Diff/edit-based patches** instead of full-file replacement — scales to large real files, less token cost, no risk of the model dropping code.
- [ ] **Reproducer test-quality check**: confirm the authored failing test fails for the right reason (guard against trivially-true tests that would hollow out the "trust" thesis).
- [ ] **Verifier scoping**: run only affected tests on large repos instead of the whole suite each revision.
- [ ] **`--json` output** for the CLI, so TrustBand can be a real CI step.

### Polish
- [ ] Dedup the baseline pytest run (the Reproducer and the orchestrator both compute it once).
- [ ] Consider raising `--cov-fail-under` (currently 80; actual coverage is 93%).
- [ ] Rendered architecture image (PNG/SVG) for the README and the demo video, not just the mermaid source.
