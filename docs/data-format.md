# Data format

One folder with up to six CSV files and `settings.json`. Only `users.csv` is required; every other file adds its area. Column names are matched case-insensitively with the aliases below, so the CSV you download from admin.atlassian.com loads without renaming. `Yes`, `True`, `1` and `Has access` all count as yes; `Never`, `Never accessed` and empty count as no date.

## users.csv (Atlassian administration → Directory → Users → Export users)

| Column (aliases) | Used for |
|---|---|
| `Account id` (user id, id) | identity; falls back to the email when missing |
| `Name` (user name, display name) | shown in the lists; also checked for service-account words |
| `Email` | identity, domain (managed or external), group membership |
| `Status` (user status) | `Active`, `Suspended…`, `Deactivated`: anything not active with product access is a licence to reclaim |
| `Account type` | `atlassian` (default), `app`, `customer`: app and portal-only customer accounts are not licences |
| `Added to org` (added, created) | grace period for new joiners (`never_used_days`) |
| `Jira` / `Jira Software`, `Confluence`, `Jira Service Management` (agent) | product access per user |
| `Last seen in Jira`, `Last seen in Confluence`, `Last seen in Jira Service Management` | inactivity per product; `Last active` is used for every product when the per-product columns are missing |

## group_members.csv

`Group`, `Member` (email or account id). One row per membership. Used to find admins (`admin_groups`) and to show which groups give access.

## projects.csv

| Column | Used for |
|---|---|
| `Key`, `Name`, `Project type` | identity; `service_desk` and `business` types are recognised |
| `Lead` | must be an active user |
| `Last issue update` | projects idle for `project_stale_days` → archive |
| `Issues` | shown |
| `Permission scheme`, `Workflow scheme` | schemes used by fewer than `shared_scheme_min` projects are one-offs |
| `Browse anyone` | Browse Projects granted to Anyone (public) → critical |
| `Archived` | archived projects are skipped |

## spaces.csv

`Key`, `Name`, `Type` (global / personal), `Status` (current / archived), `Last updated`, `Pages`, `Admins` (`;`-separated emails or ids), `Anonymous access`. Global spaces need an active admin and recent updates; personal spaces of deactivated users are listed; anonymous access is critical.

## sprints.csv

One row per sprint: `Board`, `Project`, `Sprint`, `State` (closed / active / future), `Start`, `End`, `Complete date`, `Committed`, `Completed`, `Added after start`, `Carried over` (story points or issue counts, as long as the board is consistent). The last `sprint_window` closed sprints give velocity, say/do (completed ÷ committed), carry-over and scope added (both ÷ committed). The Sprint Report in Jira shows these numbers per sprint; the exporter collects them.

## custom_fields.csv

`Name`, `Type`, `Contexts`, `Projects` (a number, or `Global`), `Issues with value`, `Last used`. Fields with no values, or not used for `field_unused_days`, can be removed; fields with more than three contexts, or global fields barely used, are flagged for review.

## settings.json

```json
{
  "site": "fabrikam-robotics.atlassian.net",
  "as_of": "2026-10-24",
  "managed_domains": ["fabrikam.com"],
  "seats": {"jira": 400, "confluence": 500, "jsm": 45},
  "price": {"jira": 8.6, "confluence": 6.1, "jsm": 21.0},
  "currency": "€",
  "inactive_days": 90,
  "never_used_days": 30,
  "admin_groups": ["site-admins", "org-admins", "jira-admins", "confluence-admins"],
  "max_admins": 6,
  "service_patterns": ["svc", "automation", "integration", "bot", "noreply"],
  "service_owners": {"svc-jenkins@fabrikam.com": "Platform Ops"},
  "project_stale_days": 180,
  "space_stale_days": 365,
  "field_unused_days": 365,
  "custom_field_budget": 400,
  "shared_scheme_min": 3,
  "sprint_window": 6,
  "carryover_max_pct": 20,
  "scope_added_max_pct": 15,
  "say_do_min_pct": 70,
  "board_idle_days": 45,
  "sprint_overdue_days": 3
}
```

- **price** is per user per month and is only used to put a number on the licences to reclaim; use your own contract price.
- **seats** is what you bought; more users with access than seats is critical, and fewer than 80% in use after reclaiming is a note for the renewal.
- **service_patterns** are matched as whole words in the name or the mailbox (`svc-jenkins`, `Automation Bot`, `jira.integration@`), so a surname that merely contains `svc` does not count.
- **service_owners** maps a service account to the team that owns it; accounts without an owner are flagged.
- Dates accept `YYYY-MM-DD`, ISO with `T` and `Z`, `24 Oct 2026` and `DD/MM/YYYY`.
