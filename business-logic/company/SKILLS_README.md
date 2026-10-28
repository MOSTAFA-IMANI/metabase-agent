# SouPop Agent Skills

Reusable, modular skills derived from `overview.md`, the supplied SouPop business overview.

## Included skills

| Skill | Use it for |
|---|---|
| `soupop-business-overview` | General business model, roles, and workflow |
| `soupop-customer-demand` | Customer acquisition, activation, engagement, and retention |
| `soupop-vendor-supply` | Vendor recruitment, onboarding, activation, and retention |
| `soupop-transactions-and-revenue` | Transaction flow, invoices, settlement concept, commission revenue |
| `soupop-growth-and-metrics` | Growth planning and business reviews |

Each skill is a standalone `SKILL.md` with YAML frontmatter (`name`, `description`) and task instructions. This format is designed to be portable across agent tools that support the Agent Skills convention, but each platform's installation/import method may differ.

## Quick start

1. Upload this repository to GitHub.
2. For a compatible agent that supports skills, install or reference the relevant folder under `skills/<skill-name>/`.
3. For ChatGPT custom GPTs, use the platform's supported knowledge/instruction configuration. If the interface does not support loading a GitHub skill directory directly, upload the relevant `SKILL.md` files or paste the appropriate instructions. GitHub hosting alone does not automatically connect a repository to ChatGPT.
4. For agents that do not support skills, paste the relevant `SKILL.md` content into the agent's system/project instructions or knowledge source.

## Repository layout and installation

- `.agents/skills/` is the repository-discovery location used by Codex.
- `skills/` is a portable catalog copy for tools that expect a top-level skills directory.
- Keep the five skill folders modular and update the relevant `SKILL.md` when the business model changes.
- Add separate skills for new domains (e.g. credit policy, APIs, analytics) only when there is an authoritative source for them.
- Avoid placing secrets, customer personal data, API keys, or credentials in this repository.

### Codex

Clone this repository, or copy `.agents/skills/` into the root of your existing project. Open that project in Codex; if the skills do not appear, restart Codex.

### ChatGPT

Availability depends on your ChatGPT plan and workspace. If Skills are available, use the supported import/install flow. A GitHub repository does not automatically install itself into ChatGPT. If direct skill installation is not available, upload the relevant `SKILL.md` files as knowledge to a custom GPT or use them as project/reference material.

### Other agents

Use the platform's Agent Skills-compatible import mechanism if available. Otherwise, provide the contents of the relevant `SKILL.md` as project/system instructions or knowledge. Support and installation paths vary by agent.

## Source and grounding

These skills were derived from the supplied `overview.md`. They preserve the stated model: SouPop connects car owners, credit, and contracted automotive vendors; customers use BNPL credit or a loan for services; SouPop earns vendor commission from transactions.

The source does not specify exact commission rates, credit eligibility, settlement timing, financial targets, or detailed accounting rules. The skills instruct agents not to invent these details.

## Example prompts

- "Explain SouPop's business model to a new employee."
- "Map the customer funnel and identify missing metrics."
- "Suggest ways to improve vendor activation without inventing performance data."
- "Explain the difference between allocated credit, transaction value, and commission revenue."
