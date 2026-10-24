"""The checks: licences, access, Jira projects and configuration, Confluence spaces, agile delivery.

Every function takes the Data object from model.py and returns plain rows (dicts); run_all() turns them into Findings.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import mean

from .model import PRODUCT_NAMES, PRODUCTS, Data, Sprint, User

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Licences", "Access", "Jira projects", "Confluence spaces", "Agile delivery")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


def _days(d: Data, when) -> int | None:
    return (d.as_of - when).days if when else None


def _top(items: list[str], n: int = 6) -> str:
    return ", ".join(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else "")


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def _money(d: Data, v: float) -> str:
    return f"{d.settings.currency}{v:,.0f}"


# ---------------------------------------------------------------- licences

def licence_rows(d: Data) -> list[dict]:
    """One row per user and product the user can access: keep, reclaim (inactive) or never used."""
    s = d.settings
    rows = []
    for u in d.users:
        if u.account_type != "atlassian":
            continue
        for p in PRODUCTS:
            if not u.access.get(p):
                continue
            seen = u.last_seen.get(p)
            days = _days(d, seen)
            added_days = _days(d, u.added)
            if u.status != "active":
                verdict, why = "reclaim", f"account {u.status} but still has {PRODUCT_NAMES[p]} access"
            elif seen is None and (added_days is None or added_days > s.never_used_days):
                verdict, why = "reclaim", "never used" + (f" since added {added_days} days ago" if added_days is not None else "")
            elif days is not None and days > s.inactive_days:
                verdict, why = "reclaim", f"last seen {days} days ago"
            else:
                verdict, why = "keep", ""
            rows.append(dict(user=u, account=u.email or u.account_id, name=u.name, product=p, last_seen=seen, days=days, verdict=verdict,
                             why=why, cost_year=round(12 * s.price.get(p, 0.0), 2) if verdict == "reclaim" else 0.0))
    return rows


def seat_rows(d: Data, lic: list[dict] | None = None) -> list[dict]:
    s = d.settings
    lic = lic if lic is not None else licence_rows(d)
    out = []
    for p in PRODUCTS:
        assigned = sum(r["product"] == p for r in lic)
        if not assigned and p not in s.seats:
            continue
        reclaim = sum(r["product"] == p and r["verdict"] == "reclaim" for r in lic)
        bought = s.seats.get(p, 0)
        out.append(dict(product=p, name=PRODUCT_NAMES[p], bought=bought, assigned=assigned, reclaim=reclaim, after=assigned - reclaim,
                        used_pct=round(100 * assigned / bought, 1) if bought else 0.0, price=s.price.get(p, 0.0),
                        saving_year=round(12 * s.price.get(p, 0.0) * reclaim, 2)))
    return out


# ---------------------------------------------------------------- access

def _is_service(u: User, d: Data) -> bool:
    """A normal (atlassian) account whose name or mailbox looks like an integration: 'svc-jira', 'Automation Bot', 'jira.integration@'."""
    if u.account_type != "atlassian":
        return False
    tokens = set(re.split(r"[^a-z0-9]+", f"{u.name} {u.email.split('@')[0]}".lower()))
    return bool(tokens & set(d.settings.service_patterns))


def access_rows(d: Data) -> list[dict]:
    """Admins, external users with product access and service accounts, each with what is wrong (if anything)."""
    s = d.settings
    rows = []
    admin_groups = set(s.admin_groups)
    for u in d.users:
        adm = sorted(set(u.groups) & admin_groups)
        external = bool(s.managed_domains) and u.domain and u.domain not in s.managed_domains and u.account_type == "atlassian"
        service = _is_service(u, d)
        has_access = any(u.access.values())
        if not (adm or (external and has_access) or service):
            continue
        issues = []
        days = _days(d, u.last_any)
        if adm and u.status != "active":
            issues.append(f"{u.status} account still in {', '.join(adm)}")
        elif adm and (days is None or days > s.inactive_days):
            issues.append(f"admin not seen for {days if days is not None else '?'} days")
        if adm and external:
            issues.append(f"admin from an unmanaged domain ({u.domain})")
        if external and has_access and not adm:
            issues.append(f"external user ({u.domain}) with product access")
        if service and not s.service_owners.get(u.email) and not s.service_owners.get(u.account_id.lower()):
            issues.append("service account without a named owner")
        kind = "admin" if adm else "service" if service else "external"
        rows.append(dict(user=u, account=u.email or u.account_id, name=u.name, kind=kind, groups=adm, domain=u.domain, days=days,
                         owner=s.service_owners.get(u.email) or s.service_owners.get(u.account_id.lower(), ""), issues=issues))
    return rows


# ---------------------------------------------------------------- jira projects and fields

def project_rows(d: Data) -> list[dict]:
    s = d.settings
    perm_use = Counter(p.permission_scheme for p in d.projects if p.permission_scheme and not p.archived)
    wf_use = Counter(p.workflow_scheme for p in d.projects if p.workflow_scheme and not p.archived)
    rows = []
    for p in d.projects:
        if p.archived:
            continue
        issues, notes = [], []
        days = _days(d, p.last_update)
        lead = d.user(p.lead)
        if days is None or days > s.project_stale_days:
            issues.append(f"no issue updated for {days if days is not None else '?'} days: archive")
        if not p.lead:
            issues.append("no project lead")
        elif lead is None or lead.status != "active":
            issues.append(f"lead {p.lead} is {'not in the user list' if lead is None else lead.status}")
        if p.browse_anyone:
            issues.append("Browse Projects granted to Anyone (public)")
        if p.permission_scheme and perm_use[p.permission_scheme] < s.shared_scheme_min:
            notes.append(f"one-off permission scheme '{p.permission_scheme}'")
        if p.workflow_scheme and wf_use[p.workflow_scheme] < s.shared_scheme_min:
            notes.append(f"one-off workflow scheme '{p.workflow_scheme}'")
        verdict = "fix" if (p.browse_anyone or not p.lead or lead is None or (lead and lead.status != "active")) else \
            "archive" if issues else "tidy" if notes else "ok"
        if verdict == "fix" and days is not None and days > s.project_stale_days and not p.browse_anyone:
            verdict = "archive"
        rows.append(dict(project=p, key=p.key, name=p.name, type=p.type, days=days, issues_count=p.issues, verdict=verdict, issues=issues, notes=notes))
    return rows


def field_rows(d: Data) -> list[dict]:
    s = d.settings
    rows = []
    for f in d.fields:
        days = _days(d, f.last_used)
        problems = []
        if f.issues == 0:
            problems.append("no issue has a value")
        elif days is None and f.issues < 0:
            problems.append("no last-used date (never used, or usage not tracked)")
        elif days is None or days > s.field_unused_days:
            problems.append(f"last used {days if days is not None else '?'} days ago")
        if f.contexts > 3:
            problems.append(f"{f.contexts} contexts")
        if f.projects == 0 and 0 < f.issues < 50:
            problems.append(f"global field used in only {f.issues} issues")
        unused = f.issues == 0 or (days is not None and days > s.field_unused_days) or (days is None and f.issues > 0)
        verdict = "remove" if unused else "review" if problems else "ok"
        rows.append(dict(field=f, name=f.name, type=f.type, contexts=f.contexts, projects=f.projects, issues=f.issues, days=days,
                         verdict=verdict, problems=problems))
    return rows


# ---------------------------------------------------------------- confluence

def space_rows(d: Data) -> list[dict]:
    s = d.settings
    rows = []
    for sp in d.spaces:
        if sp.status == "archived":
            continue
        issues = []
        days = _days(d, sp.last_update)
        active_admins = [a for a in sp.admins if (u := d.user(a)) and u.status == "active"]
        owner = d.user(sp.admins[0]) if sp.type == "personal" and sp.admins else None
        if sp.anonymous:
            issues.append("anonymous (public) access enabled")
        if sp.type == "personal":
            if owner is not None and owner.status != "active":
                issues.append(f"personal space of a {owner.status} user")
        else:
            if not active_admins:
                issues.append("no active space admin")
            if days is None or days > s.space_stale_days:
                issues.append(f"no page updated for {days if days is not None else '?'} days: archive")
        verdict = "fix" if sp.anonymous or (sp.type == "global" and not active_admins) else "archive" if issues else "ok"
        rows.append(dict(space=sp, key=sp.key, name=sp.name, type=sp.type, days=days, pages=sp.pages, admins=active_admins,
                         verdict=verdict, issues=issues))
    return rows


# ---------------------------------------------------------------- agile

def board_rows(d: Data) -> list[dict]:
    s = d.settings
    by_board: dict[str, list[Sprint]] = defaultdict(list)
    for sp in d.sprints:
        by_board[sp.board].append(sp)
    rows = []
    for board, sprints in sorted(by_board.items()):
        closed = sorted([x for x in sprints if x.state == "closed"], key=lambda x: x.end or x.complete or d.as_of)[-s.sprint_window:]
        active = [x for x in sprints if x.state == "active"]
        future = [x for x in sprints if x.state == "future"]
        last_end = max([x.complete or x.end for x in sprints if x.state == "closed" and (x.complete or x.end)] or [None], key=lambda v: v or d.as_of.replace(year=1))
        committed = sum(x.committed for x in closed)
        say_do = round(100 * sum(x.completed for x in closed) / committed, 1) if committed else None
        carry = round(100 * sum(x.carried for x in closed) / committed, 1) if committed else None
        added = round(100 * sum(x.added for x in closed) / committed, 1) if committed else None
        overdue = [x for x in active if x.end and (d.as_of - x.end).days > s.sprint_overdue_days]
        idle_days = _days(d, last_end) if not active and not future else None
        issues = []
        if overdue:
            issues.append(f"active sprint '{overdue[0].name}' ended {(d.as_of - overdue[0].end).days} days ago")
        if idle_days is not None and idle_days > s.board_idle_days:
            issues.append(f"no sprint for {idle_days} days and nothing planned: archive or move to Kanban")
        if carry is not None and carry > s.carryover_max_pct:
            issues.append(f"carry-over {carry:g}% of commitment (limit {s.carryover_max_pct:g}%)")
        if added is not None and added > s.scope_added_max_pct:
            issues.append(f"scope added after start {added:g}% (limit {s.scope_added_max_pct:g}%)")
        if say_do is not None and say_do < s.say_do_min_pct:
            issues.append(f"say/do {say_do:g}% (target {s.say_do_min_pct:g}%)")
        trend = [round(100 * x.completed / x.committed) if x.committed else 0 for x in closed]
        rows.append(dict(board=board, project=sprints[0].project, sprints=len(closed), active=len(active), say_do=say_do, carry=carry,
                         added=added, velocity=round(mean([x.completed for x in closed]), 1) if closed else 0.0, trend=trend,
                         idle_days=idle_days, overdue=overdue, issues=issues, verdict="idle" if idle_days is not None and idle_days > s.board_idle_days
                         else "attention" if issues else "ok"))
    return rows


# ---------------------------------------------------------------- findings

def run_all(d: Data) -> list[Finding]:
    s = d.settings
    f: list[Finding] = []
    lic = licence_rows(d)
    # licences
    for p in PRODUCTS:
        rec = [r for r in lic if r["product"] == p and r["verdict"] == "reclaim"]
        never = [r for r in rec if r["why"].startswith("never used")]
        inactive = [r for r in rec if r not in never]
        if inactive:
            cost = sum(r["cost_year"] for r in inactive)
            f.append(Finding(WARNING if len(inactive) < 20 else CRITICAL, "Licences", "LIC-01", f"Inactive {PRODUCT_NAMES[p]} licences",
                             f"{len(inactive)} users with access not seen for {s.inactive_days}+ days (or suspended), {_money(d, cost)} a year: "
                             f"{_top([r['account'] for r in inactive])}.",
                             "Tell the managers, wait a week, then remove the product access (the account stays; access can be given back in a minute).",
                             "Atlassian admin", items=[r["account"] for r in inactive]))
        if never:
            f.append(Finding(WARNING, "Licences", "LIC-02", f"{PRODUCT_NAMES[p]} access never used",
                             f"{len(never)} users were given access more than {s.never_used_days} days ago and never opened {PRODUCT_NAMES[p]}: "
                             f"{_top([r['account'] for r in never])}.",
                             "Remove the access and stop granting it by default: check which group gives it (often a default access group).",
                             "Atlassian admin", items=[r["account"] for r in never]))
    for sr in seat_rows(d, lic):
        if sr["bought"] and sr["assigned"] > sr["bought"]:
            f.append(Finding(CRITICAL, "Licences", "LIC-03", f"{sr['name']} over the licensed seats",
                             f"{sr['assigned']} users have access and {sr['bought']} seats are licensed; {sr['reclaim']} of them can be reclaimed.",
                             "Reclaim first (LIC-01/02); only then decide whether to move up a tier at renewal.", "Atlassian admin"))
        elif sr["bought"] and sr["after"] < 0.8 * sr["bought"]:
            f.append(Finding(INFO, "Licences", "LIC-03", f"{sr['name']} seats to drop at renewal",
                             f"After reclaiming, {sr['after']} of {sr['bought']} seats would be in use ({100 * sr['after'] / sr['bought']:.0f}%).",
                             "Take the number to the renewal; Cloud user tiers are bought in steps, so check which tier fits.", "IT finance"))
    # access
    acc = access_rows(d)
    admins = [r for r in acc if r["kind"] == "admin"]
    if len(admins) > s.max_admins:
        f.append(Finding(WARNING, "Access", "ACC-01", "Too many administrators",
                         f"{len(admins)} accounts are in admin groups ({', '.join(sorted({g for r in admins for g in r['groups']}))}); the target is {s.max_admins}: "
                         f"{_top([r['account'] for r in admins])}.",
                         "Keep two or three named site admins plus one break-glass account; give project admins project roles instead.", "IT management",
                         items=[r["account"] for r in admins]))
    stale_adm = [r for r in admins if any("not seen" in i or "account still in" in i for i in r["issues"])]
    if stale_adm:
        f.append(Finding(CRITICAL, "Access", "ACC-02", "Inactive or deactivated administrators",
                         f"{len(stale_adm)} admin account{'s are' if len(stale_adm) > 1 else ' is'} not in use: {_top([r['account'] + ' (' + r['issues'][0] + ')' for r in stale_adm], 4)}.",
                         "Remove them from the admin groups today; an unused admin account is the easiest way in.", "Atlassian admin",
                         items=[r["account"] for r in stale_adm]))
    ext_adm = [r for r in admins if any("unmanaged domain" in i for i in r["issues"])]
    if ext_adm:
        f.append(Finding(CRITICAL, "Access", "ACC-03", "Administrators from outside the company",
                         f"{len(ext_adm)} admin account{'s use' if len(ext_adm) > 1 else ' uses'} an unmanaged domain: {_top([r['account'] for r in ext_adm])}.",
                         "Give partners a company account under SSO and MFA, or a scoped project role; never an admin group on a personal domain.",
                         "Atlassian admin", items=[r["account"] for r in ext_adm]))
    ext = [r for r in acc if r["kind"] == "external"]
    if ext:
        doms = Counter(r["domain"] for r in ext)
        f.append(Finding(WARNING, "Access", "ACC-04", "External users with product access",
                         f"{len(ext)} users from {len(doms)} unmanaged domains have product access ({', '.join(f'{k} {v}' for k, v in doms.most_common(4))}).",
                         "Confirm each with a sponsor and an end date; contractors without a current contract lose access.", "Project owners",
                         items=[r["account"] for r in ext]))
    svc = [r for r in acc if any("without a named owner" in i for i in r["issues"])]
    if svc:
        f.append(Finding(WARNING, "Access", "ACC-05", "Service accounts without an owner",
                         f"{len(svc)} integration or automation accounts have no named owner: {_top([r['account'] for r in svc])}.",
                         "Name an owner in settings.json (service_owners) for each, or remove it; prefer app accounts or API tokens owned by a person.",
                         "Atlassian admin", items=[r["account"] for r in svc]))
    # jira projects
    pr = project_rows(d)
    public = [r for r in pr if r["project"].browse_anyone]
    if public:
        f.append(Finding(CRITICAL, "Jira projects", "JIR-01", "Projects visible to anyone",
                         f"{len(public)} projects grant Browse Projects to Anyone: {_top([r['key'] for r in public])}.",
                         "Change the permission scheme to logged-in users or a group; check the project's issues for anything that was public.",
                         "Atlassian admin", items=[r["key"] for r in public]))
    nolead = [r for r in pr if any(i.startswith("no project lead") or i.startswith("lead ") for i in r["issues"])]
    if nolead:
        f.append(Finding(WARNING, "Jira projects", "JIR-02", "Projects without an active lead",
                         f"{len(nolead)} projects have no lead or a lead who has left: {_top([r['key'] for r in nolead])}.",
                         "Ask the team for a new lead; the lead is who approves access and scheme changes for the project.", "Project owners",
                         items=[r["key"] for r in nolead]))
    stale = [r for r in pr if r["verdict"] == "archive"]
    if stale:
        f.append(Finding(WARNING if len(stale) > 5 else INFO, "Jira projects", "JIR-03", "Projects to archive",
                         f"{len(stale)} projects have had no issue updated for {s.project_stale_days}+ days: {_top([r['key'] for r in stale])}.",
                         "Archive them (Jira Premium) or move them to an 'Archive' category with read-only permissions.", "Atlassian admin",
                         items=[r["key"] for r in stale]))
    oneoff = sorted({n for r in pr for n in r["notes"]})
    if oneoff:
        f.append(Finding(INFO, "Jira projects", "JIR-04", "One-off schemes",
                         f"{len(oneoff)} schemes are used by fewer than {s.shared_scheme_min} projects: {_top([n.split(' scheme ')[-1] for n in oneoff])}.",
                         "Move those projects to the shared schemes at the next change window; every one-off scheme is a change nobody reviews.",
                         "Atlassian admin", items=oneoff))
    fr = field_rows(d)
    if fr:
        unused = [r for r in fr if r["verdict"] == "remove"]
        over = len(fr) > s.custom_field_budget
        if unused or over:
            f.append(Finding(WARNING if over else INFO, "Jira projects", "JIR-05", "Custom fields to clean up",
                             f"{len(fr)} custom fields (budget {s.custom_field_budget}); {len(unused)} unused for {s.field_unused_days}+ days or never: "
                             f"{_top([r['name'] for r in unused])}.",
                             "Remove unused fields after a CAB change (export their values first); give global fields a project context.",
                             "Atlassian admin", items=[r["name"] for r in unused]))
    # confluence
    spr = space_rows(d)
    anon = [r for r in spr if r["space"].anonymous]
    if anon:
        f.append(Finding(CRITICAL, "Confluence spaces", "CON-01", "Spaces open to anonymous users",
                         f"{len(anon)} spaces allow anonymous access: {_top([r['key'] for r in anon])}.",
                         "Remove anonymous access unless the space is meant to be public, and then check it holds nothing internal.",
                         "Atlassian admin", items=[r["key"] for r in anon]))
    noadm = [r for r in spr if "no active space admin" in r["issues"]]
    if noadm:
        f.append(Finding(WARNING, "Confluence spaces", "CON-02", "Spaces without an active admin",
                         f"{len(noadm)} spaces have no active admin: {_top([r['key'] for r in noadm])}.",
                         "Recover the space as site admin and hand it to a named owner.", "Space owners", items=[r["key"] for r in noadm]))
    old = [r for r in spr if r["type"] == "global" and any("archive" in i for i in r["issues"])]
    if old:
        f.append(Finding(INFO, "Confluence spaces", "CON-03", "Spaces to archive",
                         f"{len(old)} spaces have had no update for {s.space_stale_days}+ days: {_top([r['key'] for r in old])}.",
                         "Archive them: they stay readable but leave search and the space directory.", "Space owners", items=[r["key"] for r in old]))
    pers = [r for r in spr if any("personal space of" in i for i in r["issues"])]
    if pers:
        f.append(Finding(INFO, "Confluence spaces", "CON-04", "Personal spaces of leavers",
                         f"{len(pers)} personal spaces belong to deactivated users: {_top([r['key'] for r in pers])}.",
                         "Ask the manager whether anything should move to a team space, then archive.", "Managers", items=[r["key"] for r in pers]))
    # agile
    br = board_rows(d)
    od = [r for r in br if r["overdue"]]
    if od:
        f.append(Finding(WARNING, "Agile delivery", "AGL-01", "Sprints still open after their end date",
                         f"{_n(len(od), 'board')} {'has' if len(od) == 1 else 'have'} an active sprint past its end date: {_top([r['board'] for r in od])}.",
                         "Close the sprint in the review and move what is left on purpose; open sprints distort every report.", "Scrum masters",
                         items=[r["board"] for r in od]))
    for code, key, label, fix in (
            ("AGL-02", "carry-over", "High carry-over", "Plan to the last three sprints' average, split stories that do not fit, and look at what blocked them in the retro."),
            ("AGL-03", "scope added", "Scope added during the sprint", "Agree with the product owner what may enter a running sprint (incidents, yes; new features, next sprint)."),
            ("AGL-04", "say/do", "Low say/do ratio", "Commit less; a team that finishes what it plans is easier to trust than a team with a big number.")):
        hit = [r for r in br if any(i.startswith(key) for i in r["issues"])]
        if hit:
            f.append(Finding(WARNING, "Agile delivery", code, label,
                             f"{_n(len(hit), 'board')} over the limit over the last {s.sprint_window} sprints: "
                             f"{_top([r['board'] + ' (' + re.search(r'[0-9.]+%', next(i for i in r['issues'] if i.startswith(key))).group() + ')' for r in hit], 4)}.",
                             fix, "Scrum masters", items=[r["board"] for r in hit]))
    idle = [r for r in br if r["verdict"] == "idle"]
    if idle:
        f.append(Finding(INFO, "Agile delivery", "AGL-05", "Idle Scrum boards",
                         f"{_n(len(idle), 'board')} {'has' if len(idle) == 1 else 'have'} had no sprint for {s.board_idle_days}+ days and nothing planned: {_top([r['board'] for r in idle])}.",
                         "Ask the team: archive the board, or switch it to Kanban if the work is flow-based.", "Scrum masters",
                         items=[r["board"] for r in idle]))
    f.sort(key=lambda x: (ORDER[x.severity], AREAS.index(x.area), x.code))
    return f


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {a: "ok" for a in AREAS}
    for x in findings:
        if x.severity == CRITICAL:
            st[x.area] = CRITICAL
        elif x.severity == WARNING and st[x.area] != CRITICAL:
            st[x.area] = WARNING
    return st
