# Monthly admin review runbook

A 45-minute monthly review of the Atlassian site with the site admins, the IT owner of the licence budget, and (for the agile part) the Scrum masters. The tool only reads exports; every change is made by a person, and the changes to schemes, fields and permissions go through the change process.

## Before the meeting (30 minutes)

1. Export the users from admin.atlassian.com (Directory → Users → Export users, all products, include last-seen dates) to `data/users.csv`.
2. Run the exporter for the rest (read-only, an API token in a prompt):
   ```powershell
   .\scripts\Export-AtlassianSite.ps1 -Site https://fabrikam-robotics.atlassian.net -OutputFolder .\data
   ```
3. Check `data/settings.json`: seats and prices from the current contract, managed domains, admin groups, service-account owners.
4. Build the outputs and send `admin-review.md` with the agenda:
   ```bash
   python -m jcadmin review data/ --title "Atlassian admin review · November" --as-of 2026-11-02
   ```

## Agenda

| Minutes | Topic | Output |
|---|---|---|
| 5 | Fix first: anything critical (public projects or spaces, external or unused admins, over the seats) | `report.html` → Fix first |
| 10 | Licences: who loses access this month; managers get a week to object | `licences.csv` (manager_ok, removed columns) |
| 10 | Access: admin list against the target, external users and their sponsors, service accounts and owners | `access-review.csv` (decision column) |
| 10 | Jira and Confluence hygiene: projects and spaces to archive, leads and space admins to replace, fields and schemes for the next change window | `projects.csv`, `spaces.csv`, `fields.csv` |
| 10 | Agile health with the Scrum masters: open sprints, carry-over, scope added, say/do, idle boards | `boards.csv` |

## How to read the agile numbers

- **Say/do** is completed ÷ committed over the last sprints. A low number usually means the team plans the sprint it would like, not the one it can finish; the fix is planning to the recent average.
- **Carry-over** is the work moved to the next sprint unfinished. High carry-over with normal say/do usually means large stories that only finish in the next sprint.
- **Scope added** is the work that entered after the sprint started. Some is expected (incidents); a lot means the product owner and the team need an agreement on what can enter a running sprint.
- **Idle boards** have no sprint and nothing planned. Either the team has moved to another board or the work is flow-based and belongs on a Kanban board.

These are conversation starters for the retrospective, not targets. Comparing velocity between teams is meaningless; the trend of one team against itself is what matters.

## After the meeting

- Remove licences only after the week's notice, and record the date in `licences.csv`.
- Raise one change request for the configuration clean-up (fields, schemes, archived projects) and attach `fields.csv` and `projects.csv`.
- Keep each month's output folder; the next review starts by checking that last month's actions are done.
