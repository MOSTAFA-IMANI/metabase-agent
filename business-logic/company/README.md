# Company: Soupop business model

| Path | What it is |
|---|---|
| `overview.md` | Soupop business model overview (Persian): roles, core flow, value flow, planning frame |
| `skills/` | Source copy of the five Soupop business skills, from https://github.com/MOSTAFA-IMANI/SoupopSkills |
| `SKILLS_README.md`, `SOURCE_NOTES.md` | That repository's guide and notes on what the source does and doesn't confirm |

The agent loads the skills from `.agents/skills/soupop-*`, which are copies of `skills/`. When a skill changes, edit it here and copy it over:

```bash
cp -R business-logic/company/skills/. .agents/skills/
```

The overview does not state commission rates, credit eligibility, settlement timing or targets. The skills tell agents not to invent them; use the domain guides and live data instead.
