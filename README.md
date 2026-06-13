[English](./README_EN.md)

# TrustBand

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)
![Built on Band](https://img.shields.io/badge/Built%20on-Band-7c3aed.svg)

> 一支在 [Band](https://www.band.ai/) 上协作的 agent band,把 bug/issue 变成"可信到敢合"的修复 PR。
>
> **Don't just write code — earn the merge.**

## 它解决什么

让 AI 写代码已经不稀奇,难的是**敢不敢合**。TrustBand 把多个专业化 agent 编排在 Band 的共享 room 里协作:规划、改代码、**验证**、评审、人工审批,最后产出一个带"可信背书"的 PR。

差异点在 **Verifier agent**:它不靠 LLM 自评,而是跑真实路径测试 + 回归检查 + 轨迹断言,用确定性证据决定这个修复值不值得合。

## Agents

| Agent | 职责 | 产物 |
|---|---|---|
| Planner | 读 issue + repo 上下文,定位根因 | `FixPlan` |
| Coder | 按 plan 出补丁(可接 Claude Code / Codex) | `Patch` |
| **Verifier** | 真实路径测试 + 回归 + 轨迹断言 | `VerdictReport` |
| Reviewer | 批评式 review,可要求改稿 | `ReviewReport` |
| Human gate | 看证据后 approve / decline | `Decision` |

所有 handoff、结构化上下文交换、人审都经由 Band(`--bus band`),也可用内存假总线离线运行(`--bus memory`)。

## 快速开始(离线、免费、确定性)

```bash
uv sync
uv run pytest -q
uv run trustband run --repo fixtures/buggy_app --issue fixtures/buggy_app/ISSUE.md --bus memory --llm fake
```

离线模式不需要任何 API key。接真 Band / 真 LLM 见 [SETUP.md](./SETUP.md)。

## 状态

开发中(Band of Agents Hackathon,2026-06)。架构图与 demo 见 Phase 5 产物。
