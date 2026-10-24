"""Fictional demo site: Fabrikam Robotics, a made-up warehouse-robotics company on Jira, Jira Service Management and Confluence Cloud.

Deterministic (seeded). Problems are planted on purpose so every check has something to find.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

AS_OF = date(2026, 10, 24)
SITE = "fabrikam-robotics.atlassian.net"
DOMAIN = "fabrikam.com"
FIRST = ["Ana", "Luis", "Marta", "Javier", "Lucia", "Pablo", "Elena", "Diego", "Sara", "Carlos", "Laura", "Hugo", "Irene", "Mario",
         "Nuria", "Oscar", "Paula", "Raul", "Sofia", "Tomas", "Clara", "Adrian", "Eva", "Ivan", "Julia", "Marco", "Giulia", "Lena",
         "Jonas", "Emma", "Noah", "Mia", "Lukas", "Hannah", "Felix", "Anna", "Piotr", "Kasia", "Tomasz", "Ola"]
LAST = ["Garcia", "Martin", "Lopez", "Sanchez", "Perez", "Gomez", "Ruiz", "Diaz", "Moreno", "Navarro", "Romero", "Torres", "Rossi",
        "Bianchi", "Ferrari", "Muller", "Schmidt", "Weber", "Fischer", "Kowalski", "Nowak", "Wojcik", "Silva", "Santos", "Costa"]
DEPTS = [("Engineering", 0.42), ("Product", 0.08), ("Operations", 0.14), ("Customer Support", 0.1), ("IT", 0.05), ("Finance", 0.05),
         ("HR", 0.04), ("Sales", 0.08), ("Quality", 0.04)]
BOARDS = [("Fleet Manager", "FLEET"), ("Robot Firmware", "FW"), ("Navigation", "NAV"), ("Mobile App", "MOB"), ("Data Platform", "DATA"),
          ("Web Portal", "WEB"), ("Integrations", "INT"), ("Simulation", "SIM"), ("QA Automation", "QA"), ("Platform Ops", "OPS"),
          ("Vision", "VIS"), ("Legacy Scanner", "LSC")]


def _pick(rng, weighted):
    r, acc = rng.random(), 0.0
    for v, w in weighted:
        acc += w
        if r <= acc:
            return v
    return weighted[-1][0]


def _d(x: date | None) -> str:
    return x.isoformat() if x else ""


def build(seed: int = 30) -> dict:
    rng = random.Random(seed)
    users, groups = [], []
    used = set()

    def person(domain=DOMAIN):
        while True:
            fn, ln = rng.choice(FIRST), rng.choice(LAST)
            email = f"{fn}.{ln}{'' if rng.random() < 0.7 else rng.randint(2, 9)}@{domain}".lower()
            if email not in used:
                used.add(email)
                return fn, ln, email

    def add(name, email, status="active", jira=True, conf=True, jsm=False, seen_j=None, seen_c=None, seen_s=None, added=None, groups_=(), kind="atlassian"):
        aid = f"5f{len(users):05d}{rng.randint(100000, 999999)}"
        users.append({"Account id": aid, "Name": name, "Email": email, "Account type": kind, "Status": status,
                      "Added to org": _d(added or AS_OF - timedelta(days=rng.randint(200, 1500))),
                      "Jira": "Yes" if jira else "No", "Confluence": "Yes" if conf else "No", "Jira Service Management": "Yes" if jsm else "No",
                      "Last seen in Jira": _d(seen_j) if jira else "", "Last seen in Confluence": _d(seen_c) if conf else "",
                      "Last seen in Jira Service Management": _d(seen_s) if jsm else ""})
        for g in groups_:
            groups.append({"Group": g, "Member": email})
        return email

    recent = lambda: AS_OF - timedelta(days=rng.randint(0, 20))  # noqa: E731
    stale = lambda: AS_OF - timedelta(days=rng.randint(95, 400))  # noqa: E731
    staff = []
    for i in range(392):
        fn, ln, email = person()
        dept = _pick(rng, DEPTS)
        jira = dept in ("Engineering", "Product", "Operations", "Customer Support", "IT", "Quality") or rng.random() < 0.55
        conf = rng.random() < 0.97
        jsm = dept in ("Customer Support", "IT") and rng.random() < 0.75
        r = rng.random()
        sj = recent() if r < 0.86 else stale()
        sc = recent() if rng.random() < 0.9 else stale()
        ss = recent() if rng.random() < 0.88 else stale()
        status = "active"
        if rng.random() < 0.008:
            status = "deactivated"
        grp = ["jira-software-users"] if jira else []
        grp += ["confluence-users"] if conf else []
        grp += ["jira-servicemanagement-users"] if jsm else []
        grp += [f"dept-{dept.lower().replace(' ', '-')}"]
        staff.append(add(f"{fn} {ln}", email, status, jira, conf, jsm, sj, sc, ss, groups_=grp))
    # never used: added through a default group two months ago, never opened Jira
    for i in range(12):
        fn, ln, email = person()
        add(f"{fn} {ln}", email, jira=True, conf=True, seen_j=None, seen_c=recent(), added=AS_OF - timedelta(days=rng.randint(40, 120)),
            groups_=["jira-software-users", "confluence-users", "dept-sales"])
    # brand-new joiners (not flagged)
    for i in range(6):
        fn, ln, email = person()
        add(f"{fn} {ln}", email, jira=True, conf=True, seen_j=None, seen_c=None, added=AS_OF - timedelta(days=rng.randint(1, 12)),
            groups_=["jira-software-users", "confluence-users"])
    # external partners
    for dom, n in (("contoso-consulting.com", 14), ("northwindqa.io", 6)):
        for i in range(n):
            fn, ln, email = person(dom)
            add(f"{fn} {ln}", email, jira=True, conf=rng.random() < 0.6, seen_j=recent() if rng.random() < 0.6 else stale(), seen_c=recent(),
                groups_=["jira-software-users", "partners"])
    # admins
    admins = staff[:6]
    for a in admins:
        groups.append({"Group": "site-admins" if a in staff[:3] else "jira-admins", "Member": a})
    for a in staff[6:9]:
        groups.append({"Group": "confluence-admins", "Member": a})
    old_admin = add("Ruben Ortega", "ruben.ortega@fabrikam.com", status="deactivated", seen_j=AS_OF - timedelta(days=210), seen_c=AS_OF - timedelta(days=210),
                    groups_=["site-admins", "jira-software-users", "confluence-users"])
    add("Alba Ferrer", "alba.ferrer@fabrikam.com", seen_j=AS_OF - timedelta(days=160), seen_c=AS_OF - timedelta(days=150),
        groups_=["jira-admins", "jira-software-users", "confluence-users"])
    add("Mark Hollis", "mark.hollis.dev@gmail.com", seen_j=recent(), seen_c=recent(), groups_=["jira-admins", "jira-software-users", "confluence-users"])
    # service accounts
    add("svc-jenkins", "svc-jenkins@fabrikam.com", seen_j=recent(), conf=False, groups_=["jira-software-users"])
    add("Automation Bot", "automation.bot@fabrikam.com", seen_j=recent(), seen_c=recent(), groups_=["jira-software-users", "confluence-users", "jira-admins"])
    add("Jira Integration", "jira.integration@fabrikam.com", seen_j=recent(), conf=False, groups_=["jira-software-users"])
    add("svc-backup", "svc-backup@fabrikam.com", seen_j=AS_OF - timedelta(days=30), seen_c=AS_OF - timedelta(days=30), groups_=["jira-software-users", "confluence-users"])
    add("Slack", "", kind="app", jira=False, conf=False)
    # JSM customers (portal only, no licence)
    for i in range(25):
        fn, ln, email = person("customers.example")
        add(f"{fn} {ln}", email, kind="customer", jira=False, conf=False)

    active = [u["Email"] for u in users if u["Status"] == "active" and u["Email"].endswith(DOMAIN) and u["Account type"] == "atlassian"
              and not any(x in u["Email"] for x in ("svc", "bot", "integration"))]
    gone = [u["Email"] for u in users if u["Status"] == "deactivated"] + ["former.lead@fabrikam.com", "ex.manager@fabrikam.com"]

    # projects
    projects = []
    perm_shared = ["Default Permission Scheme", "Engineering Permissions", "Service Desk Permissions"]
    wf_shared = ["Engineering Workflow", "Service Desk Workflow", "Business Workflow"]
    keys = [k for _, k in BOARDS] + ["SD", "ITSD", "HR", "FIN", "LEGAL", "MKT", "SALES", "QMS", "RMA", "SUP", "PROC", "FAC", "SEC", "ARCH",
                                     "BI", "ML", "HW", "PCB", "MECH", "PKG", "DOCS", "REL", "PERF", "ACC", "CERT", "TRAIN", "ONB", "EVT",
                                     "PART", "LOG", "WMS", "ERP", "CRM", "PORTAL", "API", "SDK", "TOOLS", "INFRA", "NET", "DB", "OBS",
                                     "DEMO", "PUBDOCS", "HACK", "OLD1", "OLD2", "PILOT", "R2020", "R2021", "TMP"]
    for i, k in enumerate(keys):
        service = k in ("SD", "ITSD", "SUP", "RMA", "FAC")
        business = k in ("HR", "FIN", "LEGAL", "MKT", "SALES", "PROC", "TRAIN", "ONB", "EVT")
        last = AS_OF - timedelta(days=rng.randint(0, 40))
        if k in ("OLD1", "OLD2", "R2020", "R2021", "TMP", "HACK", "PILOT", "LSC", "ARCH", "CERT"):
            last = AS_OF - timedelta(days=rng.randint(200, 900))
        lead = rng.choice(active)
        if k in ("PCB", "PKG", "R2021"):
            lead = rng.choice(gone)
        if k == "TOOLS":
            lead = ""
        perm = "Service Desk Permissions" if service else rng.choice(perm_shared[:2])
        wf = "Service Desk Workflow" if service else "Business Workflow" if business else "Engineering Workflow"
        if k in ("ML", "HW", "SEC", "BI", "DEMO"):
            perm = f"{k} Permissions"
        if k in ("ML", "MECH", "QMS", "PERF"):
            wf = f"{k} Workflow"
        projects.append({"Key": k, "Name": k.title() if len(k) > 3 else k, "Project type": "service_desk" if service else "business" if business else "software",
                         "Lead": lead, "Last issue update": _d(last), "Issues": rng.randint(40, 9000) if k not in ("TMP", "HACK") else rng.randint(1, 30),
                         "Permission scheme": perm, "Workflow scheme": wf, "Browse anyone": "Yes" if k in ("DEMO", "PUBDOCS") else "No",
                         "Archived": "Yes" if k in ("R2020",) else "No", "Category": "Service" if service else "Business" if business else "Engineering"})

    # spaces
    spaces = []
    gkeys = ["ENG", "PROD", "OPS", "SUPPORT", "IT", "HR", "FIN", "SALES", "QUALITY", "ARCH", "FW", "NAV", "FLEET", "MOB", "DATA", "WEB",
             "INT", "SIM", "QA", "VIS", "SEC", "LEGAL", "MKT", "ONBOARD", "HANDBOOK", "PUBLIC", "RELEASES", "RUNBOOKS", "MEETINGS",
             "RETRO", "DESIGN", "UX", "PARTNERS", "TRAINING", "EVENTS", "WIKI", "OLDWIKI", "HACK2023", "PROJX", "TEMP", "KB", "API",
             "SDK", "HW", "PCB", "MECH", "CERT", "LAB"]
    for k in gkeys:
        last = AS_OF - timedelta(days=rng.randint(0, 120))
        if k in ("OLDWIKI", "HACK2023", "PROJX", "TEMP", "CERT", "LAB", "MEETINGS", "EVENTS", "PCB", "ARCH"):
            last = AS_OF - timedelta(days=rng.randint(400, 1400))
        adm = [rng.choice(active), rng.choice(active)]
        if k in ("PROJX", "TEMP", "PCB", "PARTNERS"):
            adm = [rng.choice(gone)]
        spaces.append({"Key": k, "Name": k.title(), "Type": "global", "Status": "archived" if k == "OLDWIKI" else "current",
                       "Last updated": _d(last), "Pages": rng.randint(5, 2400), "Admins": "; ".join(adm),
                       "Anonymous access": "Yes" if k in ("PUBLIC", "PARTNERS") else "No"})
    personal_owners = rng.sample(active, 24) + gone[:6]
    for i, o in enumerate(personal_owners):
        spaces.append({"Key": f"~{o.split('@')[0].replace('.', '')}", "Name": o.split("@")[0], "Type": "personal", "Status": "current",
                       "Last updated": _d(AS_OF - timedelta(days=rng.randint(0, 700))), "Pages": rng.randint(1, 60), "Admins": o, "Anonymous access": "No"})

    # sprints
    sprints = []
    profile = {"Robot Firmware": dict(carry=0.35), "Navigation": dict(added=0.28), "Mobile App": dict(done=0.58), "Data Platform": dict(overdue=9),
               "Legacy Scanner": dict(idle=120), "Simulation": dict(idle=80)}
    for board, key in BOARDS:
        p = profile.get(board, {})
        vel = rng.randint(28, 60)
        end_last = AS_OF - timedelta(days=p.get("idle", rng.randint(1, 12)))
        n_closed = 8
        for i in range(n_closed):
            end = end_last - timedelta(days=14 * (n_closed - 1 - i))
            start = end - timedelta(days=14)
            committed = max(10, round(vel * rng.uniform(0.9, 1.15)))
            done_rate = p.get("done", rng.uniform(0.8, 0.97))
            completed = round(committed * min(1.0, rng.gauss(done_rate, 0.04)))
            added = round(committed * max(0.0, rng.gauss(p.get("added", 0.06), 0.03)))
            carried = round(committed * max(0.0, rng.gauss(p.get("carry", 0.08), 0.03))) if "done" not in p else committed - completed
            sprints.append({"Board": board, "Project": key, "Sprint": f"{key} Sprint {40 + i}", "State": "closed", "Start": _d(start),
                            "End": _d(end), "Complete date": _d(end), "Committed": committed, "Completed": completed,
                            "Added after start": added, "Carried over": carried})
        if "idle" in p:
            continue
        start = end_last
        end = start + timedelta(days=14)
        if "overdue" in p:
            end = AS_OF - timedelta(days=p["overdue"])
            start = end - timedelta(days=14)
        sprints.append({"Board": board, "Project": key, "Sprint": f"{key} Sprint {40 + n_closed}", "State": "active", "Start": _d(start),
                        "End": _d(end), "Complete date": "", "Committed": round(vel), "Completed": "", "Added after start": "", "Carried over": ""})
        sprints.append({"Board": board, "Project": key, "Sprint": f"{key} Sprint {41 + n_closed}", "State": "future", "Start": "", "End": "",
                        "Complete date": "", "Committed": "", "Completed": "", "Added after start": "", "Carried over": ""})

    # custom fields
    fields = []
    types = ["Select List (single choice)", "Text Field (single line)", "Number Field", "Date Picker", "User Picker (single user)",
             "Labels", "Checkboxes", "Paragraph"]
    stems = ["Customer", "Robot model", "Firmware version", "Site", "Severity", "Root cause", "Component", "Release", "Team", "Sprint goal",
             "Story points", "Due window", "Supplier", "Batch", "Serial number", "Warehouse", "Approval", "Risk", "Cost centre", "Region"]
    for i in range(460):
        stem = rng.choice(stems)
        name = f"{stem}{'' if i < len(stems) else ' ' + str(i)}"
        r = rng.random()
        if r < 0.2:
            issues, last = 0, None
        elif r < 0.27:
            issues, last = rng.randint(5, 400), AS_OF - timedelta(days=rng.randint(400, 1500))
        else:
            issues, last = rng.randint(50, 30000), AS_OF - timedelta(days=rng.randint(0, 200))
        fields.append({"Name": name, "Type": rng.choice(types), "Contexts": rng.choice([1, 1, 1, 2, 3, 5]) if r > 0.05 else 7,
                       "Projects": "Global" if rng.random() < 0.3 else rng.randint(1, 12), "Issues with value": issues, "Last used": _d(last)})

    settings = {
        "site": SITE, "as_of": AS_OF.isoformat(), "managed_domains": [DOMAIN],
        "seats": {"jira": 400, "confluence": 500, "jsm": 45}, "price": {"jira": 8.6, "confluence": 6.1, "jsm": 21.0}, "currency": "€",
        "inactive_days": 90, "never_used_days": 30, "admin_groups": ["site-admins", "org-admins", "jira-admins", "confluence-admins"],
        "max_admins": 6, "service_patterns": ["svc", "automation", "integration", "bot", "noreply"],
        "service_owners": {"svc-jenkins@fabrikam.com": "Platform Ops"},
        "project_stale_days": 180, "space_stale_days": 365, "field_unused_days": 365, "custom_field_budget": 400, "shared_scheme_min": 3,
        "sprint_window": 6, "carryover_max_pct": 20, "scope_added_max_pct": 15, "say_do_min_pct": 70, "board_idle_days": 45,
        "sprint_overdue_days": 3,
    }
    return dict(users=users, groups=groups, projects=projects, spaces=spaces, sprints=sprints, fields=fields, settings=settings)


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write(folder: Path, seed: int = 30) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    b = build(seed)
    _write(folder / "users.csv", b["users"])
    _write(folder / "group_members.csv", b["groups"])
    _write(folder / "projects.csv", b["projects"])
    _write(folder / "spaces.csv", b["spaces"])
    _write(folder / "sprints.csv", b["sprints"])
    _write(folder / "custom_fields.csv", b["fields"])
    (folder / "settings.json").write_text(json.dumps(b["settings"], indent=2) + "\n", encoding="utf-8")
