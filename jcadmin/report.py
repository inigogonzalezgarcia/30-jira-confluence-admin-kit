"""Outputs: report.html, admin-review.md and the CSVs (licences, seats, access, projects, spaces, fields, boards, actions, findings)."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import (AREAS, CRITICAL, INFO, WARNING, Finding, access_rows, area_status, board_rows, field_rows, licence_rows,
                     project_rows, seat_rows, space_rows)
from .model import PRODUCT_NAMES, Data

e = html.escape


def build(d: Data, findings: list[Finding]) -> dict:
    lic = licence_rows(d)
    return dict(lic=lic, seats=seat_rows(d, lic), acc=access_rows(d), projects=project_rows(d), spaces=space_rows(d), fields=field_rows(d),
                boards=board_rows(d), findings=findings)


def summary(d: Data, findings: list[Finding], b: dict | None = None) -> dict:
    b = b or build(d, findings)
    rec = [r for r in b["lic"] if r["verdict"] == "reclaim"]
    return dict(users=sum(u.account_type == "atlassian" for u in d.users), licensed=len({r["account"] for r in b["lic"]}),
                reclaim=len(rec), reclaim_users=len({r["account"] for r in rec}), saving=round(sum(r["cost_year"] for r in rec), 2),
                admins=sum(r["kind"] == "admin" for r in b["acc"]), access_issues=sum(bool(r["issues"]) for r in b["acc"]),
                projects=len(b["projects"]), projects_flagged=sum(r["verdict"] != "ok" for r in b["projects"]),
                spaces=len(b["spaces"]), spaces_flagged=sum(r["verdict"] != "ok" for r in b["spaces"]),
                fields=len(b["fields"]), fields_remove=sum(r["verdict"] == "remove" for r in b["fields"]),
                boards=len(b["boards"]), boards_flagged=sum(r["verdict"] != "ok" for r in b["boards"]),
                critical=sum(f.severity == CRITICAL for f in findings), warning=sum(f.severity == WARNING for f in findings),
                info=sum(f.severity == INFO for f in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> int:
    rows = [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO]
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"], rows)
    return len(rows)


def write_licences(b: dict, path: Path) -> None:
    rows = sorted([r for r in b["lic"] if r["verdict"] == "reclaim"], key=lambda r: (r["product"], -(r["days"] or 99999)))
    _w(path, ["account", "name", "product", "last_seen", "days", "why", "cost_year", "manager_ok", "removed"],
       [[r["account"], r["name"], PRODUCT_NAMES[r["product"]], r["last_seen"] or "never", r["days"] if r["days"] is not None else "", r["why"],
         r["cost_year"], "", ""] for r in rows])


def write_seats(b: dict, path: Path) -> None:
    _w(path, ["product", "seats_licensed", "users_with_access", "used_pct", "to_reclaim", "after_reclaim", "price_month", "saving_year"],
       [[r["name"], r["bought"], r["assigned"], r["used_pct"], r["reclaim"], r["after"], r["price"], r["saving_year"]] for r in b["seats"]])


def write_access(b: dict, path: Path) -> None:
    _w(path, ["account", "name", "kind", "admin_groups", "domain", "days_since_seen", "owner", "issues", "decision"],
       [[r["account"], r["name"], r["kind"], "; ".join(r["groups"]), r["domain"], r["days"] if r["days"] is not None else "", r["owner"],
         " | ".join(r["issues"]), ""] for r in b["acc"]])


def write_projects(b: dict, path: Path) -> None:
    _w(path, ["key", "name", "type", "days_since_update", "issues", "verdict", "problems", "notes"],
       [[r["key"], r["name"], r["type"], r["days"] if r["days"] is not None else "", r["issues_count"], r["verdict"], " | ".join(r["issues"]),
         " | ".join(r["notes"])] for r in b["projects"]])


def write_spaces(b: dict, path: Path) -> None:
    _w(path, ["key", "name", "type", "days_since_update", "pages", "active_admins", "verdict", "problems"],
       [[r["key"], r["name"], r["type"], r["days"] if r["days"] is not None else "", r["pages"], "; ".join(r["admins"]), r["verdict"],
         " | ".join(r["issues"])] for r in b["spaces"]])


def write_fields(b: dict, path: Path) -> None:
    _w(path, ["field", "type", "contexts", "projects", "issues_with_value", "days_since_used", "verdict", "problems"],
       [[r["name"], r["type"], r["contexts"], r["projects"] or "global", r["issues"], r["days"] if r["days"] is not None else "never",
         r["verdict"], " | ".join(r["problems"])] for r in b["fields"]])


def write_boards(b: dict, path: Path) -> None:
    _w(path, ["board", "project", "closed_sprints", "active", "velocity", "say_do_pct", "carry_over_pct", "scope_added_pct", "idle_days",
              "verdict", "issues"],
       [[r["board"], r["project"], r["sprints"], r["active"], r["velocity"], r["say_do"] if r["say_do"] is not None else "",
         r["carry"] if r["carry"] is not None else "", r["added"] if r["added"] is not None else "",
         r["idle_days"] if r["idle_days"] is not None else "", r["verdict"], " | ".join(r["issues"])] for r in b["boards"]])


# ---------------------------------------------------------------- markdown

def review_md(d: Data, findings: list[Finding], b: dict | None = None) -> str:
    b = b or build(d, findings)
    s, sm = d.settings, summary(d, findings, b)
    cur = s.currency
    out = [f"# Atlassian admin review · {s.site}", "",
           f"As of {d.as_of:%d %b %Y} · {sm['licensed']} licensed users · {sm['projects']} Jira projects · {sm['spaces']} Confluence spaces · "
           f"{sm['boards']} Scrum boards.", "", "## Summary", "",
           f"- Licences: {sm['reclaim']} product licences to reclaim ({sm['reclaim_users']} users), about {cur}{sm['saving']:,.0f} a year.",
           f"- Access: {sm['admins']} admins; {sm['access_issues']} accounts with something to fix (admins, external users, service accounts).",
           f"- Jira: {sm['projects_flagged']} of {sm['projects']} projects need a fix, a tidy-up or archiving; {sm['fields_remove']} of {sm['fields']} custom fields can go.",
           f"- Confluence: {sm['spaces_flagged']} of {sm['spaces']} spaces need a fix or archiving.",
           f"- Agile: {sm['boards_flagged']} of {sm['boards']} boards over a limit or idle.",
           f"- Findings: {sm['critical']} critical, {sm['warning']} warnings, {sm['info']} for information.", "", "## Seats", "",
           "| Product | Licensed | With access | To reclaim | After | Saving / year |", "|---|---:|---:|---:|---:|---:|"]
    out += [f"| {r['name']} | {r['bought'] or '–'} | {r['assigned']} | {r['reclaim']} | {r['after']} | {cur}{r['saving_year']:,.0f} |" for r in b["seats"]]
    out += ["", "## Decisions for this review", ""]
    for f in [x for x in findings if x.severity != INFO]:
        out.append(f"- [ ] **{f.code} {f.subject}** ({f.owner or 'owner?'}): {f.detail} → {f.fix}")
    out += ["", "## For information", ""]
    out += [f"- {f.code} {f.subject}: {f.detail}" for f in findings if f.severity == INFO] or ["- Nothing."]
    out += ["", "## Agile health (last sprints)", "", "| Board | Velocity | Say/do | Carry-over | Scope added | Status |", "|---|---:|---:|---:|---:|---|"]
    fmt = lambda v: f"{v:g}%" if v is not None else "–"  # noqa: E731
    out += [f"| {r['board']} | {r['velocity']:g} | {fmt(r['say_do'])} | {fmt(r['carry'])} | {fmt(r['added'])} | {r['verdict']} |" for r in b["boards"]]
    out += ["", "Generated by jcadmin. Changes to schemes, fields and permissions go through the change process before they are made.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--na:#8a94a0}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--na:#6d7782}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}.na{color:var(--na)}
.area.critical,.area.warning,.area.ok{color:inherit}
.bar{height:10px;border-radius:5px;background:var(--line);overflow:hidden;min-width:120px}.bar i{display:block;height:100%;background:var(--ok)}
.bar i.over{background:var(--bad)}.spark{display:inline-flex;gap:2px;align-items:flex-end;height:22px}.spark i{display:block;width:6px;background:var(--info);border-radius:2px 2px 0 0}
.spark i.low{background:var(--warn)}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}code{font-size:12px}
footer{margin-top:40px;font-size:13px}
"""
PILL = {"keep": "ok", "ok": "ok", "reclaim": "critical", "fix": "critical", "archive": "warning", "tidy": "info", "remove": "warning",
        "review": "info", "attention": "warning", "idle": "na"}


def _pill(s: str) -> str:
    return f"<span class='pill {PILL.get(s, s)}'>{e('OK' if s == 'ok' else s.upper())}</span>"


def _spark(trend: list[int], target: float) -> str:
    return "<span class='spark' title='say/do per sprint'>" + "".join(
        f"<i class='{'low' if v < target else ''}' style='height:{max(3, min(100, v)) * 0.22:.0f}px' title='{v}%'></i>" for v in trend) + "</span>"


def render_html(d: Data, findings: list[Finding], title: str, b: dict | None = None) -> str:
    b = b or build(d, findings)
    s = d.settings
    sm, st = summary(d, findings, b), area_status(findings)
    cur = s.currency
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(s.site)} · as of {d.as_of:%d %b %Y}</p><div class='tiles'>"]
    tiles = [("Licensed users", str(sm["licensed"]), f"{sm['users']} accounts in total"),
             ("To reclaim", str(sm["reclaim"]), f"licences · {sm['reclaim_users']} users"),
             ("Saving", f"{cur}{sm['saving']:,.0f}", "a year"),
             ("Admins", str(sm["admins"]), f"target {s.max_admins}"),
             ("Access to fix", str(sm["access_issues"]), "admins, externals, services"),
             ("Projects", f"{sm['projects_flagged']}/{sm['projects']}", "to fix or archive"),
             ("Spaces", f"{sm['spaces_flagged']}/{sm['spaces']}", "to fix or archive"),
             ("Custom fields", str(sm["fields"]), f"{sm['fields_remove']} can go"),
             ("Boards", f"{sm['boards_flagged']}/{sm['boards']}", "over a limit or idle"),
             ("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} info")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        pill = _pill("ok") if st[a] == "ok" else f"<span class='pill {st[a]}'>{st[a].upper()}</span>"
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{pill}<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    # seats
    h.append("<h2>Seats</h2><div class='wrap'><table><tr><th>Product</th><th class='num'>Licensed</th><th class='num'>With access</th><th>Use</th>"
             "<th class='num'>To reclaim</th><th class='num'>After</th><th class='num'>Saving / year</th></tr>")
    for r in b["seats"]:
        pct = 100 * r["assigned"] / r["bought"] if r["bought"] else 0
        h.append(f"<tr><td>{e(r['name'])}</td><td class='num'>{r['bought'] or '–'}</td><td class='num'>{r['assigned']}</td>"
                 f"<td><div class='bar'><i class='{'over' if pct > 100 else ''}' style='width:{min(pct, 100):.0f}%'></i></div>"
                 f"<span class='muted'>{pct:.0f}%</span></td><td class='num'>{r['reclaim']}</td><td class='num'>{r['after']}</td>"
                 f"<td class='num'>{cur}{r['saving_year']:,.0f}</td></tr>")
    h.append(f"</table></div><p class='muted'>Reclaim = not seen for {s.inactive_days}+ days, never used {s.never_used_days}+ days after being "
             "added, or account suspended/deactivated with access still assigned. The list with a manager-OK column is in <code>licences.csv</code>.</p>")
    # access
    acc = [r for r in b["acc"] if r["issues"]]
    if acc:
        h.append(f"<h2>Access to fix ({len(acc)})</h2><div class='wrap'><table><tr><th>Account</th><th>Kind</th><th>Groups</th><th>Issues</th></tr>")
        for r in sorted(acc, key=lambda r: ({"admin": 0, "service": 1, "external": 2}[r["kind"]], r["account"]))[:30]:
            h.append(f"<tr><td class='nw'>{e(r['account'] or r['name'])}<br><span class='muted'>{e(r['name'])}</span></td><td>{e(r['kind'])}</td>"
                     f"<td>{e(', '.join(r['groups']) or '–')}</td><td>{'<br>'.join(e(i) for i in r['issues'])}</td></tr>")
        h.append("</table></div>" + (f"<p class='muted'>30 of {len(acc)}; all in <code>access-review.csv</code>.</p>" if len(acc) > 30 else ""))
    # projects
    pr = [r for r in b["projects"] if r["verdict"] in ("fix", "archive")]
    if pr:
        h.append(f"<h2>Jira projects to fix or archive ({len(pr)})</h2><div class='wrap'><table><tr><th>Project</th><th>Type</th>"
                 "<th class='num'>Days idle</th><th class='num'>Issues</th><th>Verdict</th><th>Why</th></tr>")
        for r in sorted(pr, key=lambda r: (r["verdict"] != "fix", -(r["days"] or 0))):
            h.append(f"<tr><td class='nw'><b>{e(r['key'])}</b></td><td>{e(r['type'])}</td><td class='num'>{r['days'] if r['days'] is not None else '?'}</td>"
                     f"<td class='num'>{r['issues_count']:,}</td><td>{_pill(r['verdict'])}</td><td>{'<br>'.join(e(i) for i in r['issues'])}</td></tr>")
        h.append("</table></div>")
    # spaces
    sp = [r for r in b["spaces"] if r["verdict"] != "ok"]
    if sp:
        h.append(f"<h2>Confluence spaces to fix or archive ({len(sp)})</h2><div class='wrap'><table><tr><th>Space</th><th>Type</th>"
                 "<th class='num'>Days idle</th><th class='num'>Pages</th><th>Verdict</th><th>Why</th></tr>")
        for r in sorted(sp, key=lambda r: (r["verdict"] != "fix", r["type"], -(r["days"] or 0)))[:30]:
            h.append(f"<tr><td class='nw'><b>{e(r['key'])}</b></td><td>{e(r['type'])}</td><td class='num'>{r['days'] if r['days'] is not None else '?'}</td>"
                     f"<td class='num'>{r['pages']:,}</td><td>{_pill(r['verdict'])}</td><td>{'<br>'.join(e(i) for i in r['issues'])}</td></tr>")
        h.append("</table></div>")
    # boards
    if b["boards"]:
        fmt = lambda v: f"{v:g}%" if v is not None else "–"  # noqa: E731
        h.append(f"<h2>Agile health (last {s.sprint_window} sprints)</h2><div class='wrap'><table><tr><th>Board</th><th class='num'>Velocity</th>"
                 "<th>Say/do per sprint</th><th class='num'>Say/do</th><th class='num'>Carry-over</th><th class='num'>Scope added</th><th>Status</th></tr>")
        for r in b["boards"]:
            cls = lambda v, lim, hi=True: "critical" if v is not None and ((v > lim) if hi else (v < lim)) else ""  # noqa: E731
            h.append(f"<tr><td><b>{e(r['board'])}</b><br><span class='muted'>{e(r['project'])}</span></td><td class='num'>{r['velocity']:g}</td>"
                     f"<td>{_spark(r['trend'], s.say_do_min_pct)}</td><td class='num {cls(r['say_do'], s.say_do_min_pct, False)}'>{fmt(r['say_do'])}</td>"
                     f"<td class='num {cls(r['carry'], s.carryover_max_pct)}'>{fmt(r['carry'])}</td>"
                     f"<td class='num {cls(r['added'], s.scope_added_max_pct)}'>{fmt(r['added'])}</td>"
                     f"<td>{_pill(r['verdict'])}{('<br><span class=muted>' + e('; '.join(r['issues'])) + '</span>') if r['issues'] else ''}</td></tr>")
        h.append(f"</table></div><p class='muted'>Limits: say/do ≥ {s.say_do_min_pct:g}%, carry-over ≤ {s.carryover_max_pct:g}%, scope added ≤ "
                 f"{s.scope_added_max_pct:g}% of the commitment. They are conversation starters for the retro, not targets to game.</p>")
    # findings
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td><span class='pill {f.severity}'>{f.severity.upper()}</span></td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by jcadmin from the site's exports. Fictional demo data unless you ran it on your own site.</footer>"
             "</main></body></html>")
    return "".join(h)
