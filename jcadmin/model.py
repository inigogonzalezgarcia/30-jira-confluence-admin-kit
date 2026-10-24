"""Loading: the six CSV exports and settings.json, with forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

PRODUCTS = ("jira", "confluence", "jsm")
PRODUCT_NAMES = {"jira": "Jira", "confluence": "Confluence", "jsm": "Jira Service Management"}

USER_ALIASES = {
    "account_id": ["account id", "user id", "accountid", "id", "aaid"],
    "name": ["name", "user name", "display name", "displayname", "full name", "nombre"],
    "email": ["email", "email address", "mail", "correo"],
    "status": ["status", "user status", "account status", "estado"],
    "account_type": ["account type", "type", "accounttype", "user type"],
    "added": ["added", "added to org", "created", "date added", "added to site"],
    "jira_access": ["jira", "jira access", "jira software", "jira software access", "has jira access", "product access jira"],
    "confluence_access": ["confluence", "confluence access", "has confluence access", "product access confluence"],
    "jsm_access": ["jsm", "jsm access", "jira service management", "jira service management access", "jsm agent", "agent"],
    "last_seen_jira": ["last seen in jira", "last active jira", "jira last seen", "last seen jira", "last seen in jira software"],
    "last_seen_confluence": ["last seen in confluence", "last active confluence", "confluence last seen", "last seen confluence"],
    "last_seen_jsm": ["last seen in jira service management", "last seen jsm", "jsm last seen", "last active jsm"],
    "last_active": ["last active", "last seen", "last login", "last activity", "ultimo acceso"],
}
GROUP_ALIASES = {
    "group": ["group", "group name", "grupo"],
    "member": ["member", "account id", "user id", "email", "user", "miembro"],
}
PROJECT_ALIASES = {
    "key": ["key", "project key", "clave"],
    "name": ["name", "project name", "project"],
    "type": ["type", "project type", "projecttypekey"],
    "lead": ["lead", "project lead", "lead account id", "lead email", "responsable"],
    "last_update": ["last issue update", "last updated", "last update", "updated", "last activity"],
    "issues": ["issues", "issue count", "total issues"],
    "permission_scheme": ["permission scheme", "permissions"],
    "workflow_scheme": ["workflow scheme", "workflows"],
    "browse_anyone": ["browse anyone", "public", "anonymous browse", "browse: anyone", "browse public"],
    "archived": ["archived", "is archived"],
    "category": ["category", "project category", "categoria"],
}
SPACE_ALIASES = {
    "key": ["key", "space key"],
    "name": ["name", "space name", "space"],
    "type": ["type", "space type"],
    "status": ["status", "space status"],
    "last_update": ["last updated", "last update", "last modified", "last activity"],
    "pages": ["pages", "page count", "content count"],
    "admins": ["admins", "space admins", "administrators"],
    "anonymous": ["anonymous access", "anonymous", "public", "anonymous view"],
}
SPRINT_ALIASES = {
    "board": ["board", "board name"],
    "project": ["project", "project key"],
    "sprint": ["sprint", "sprint name", "name"],
    "state": ["state", "status", "sprint state"],
    "start": ["start", "start date", "startdate"],
    "end": ["end", "end date", "enddate"],
    "complete": ["complete", "complete date", "completed date", "completedate"],
    "committed": ["committed", "committed points", "commitment", "planned"],
    "completed": ["completed", "completed points", "done"],
    "added": ["added", "added after start", "scope added", "added points"],
    "carried": ["carried over", "carried", "not completed", "carry over", "incomplete"],
}
FIELD_ALIASES = {
    "name": ["name", "field name", "custom field"],
    "type": ["type", "field type"],
    "contexts": ["contexts", "context count"],
    "projects": ["projects", "project count", "used in projects"],
    "issues": ["issues", "issues with value", "issue count"],
    "last_used": ["last used", "last value", "last updated"],
}
YES = {"yes", "y", "true", "1", "si", "sí", "x", "has access", "enabled", "on", "public", "anyone"}
STATUS_MAP = {"active": "active", "activo": "active", "enabled": "active", "suspended": "suspended",
              "deactivated": "deactivated", "inactive": "deactivated", "disabled": "deactivated", "closed": "deactivated"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%b %d, %Y",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def _norm(s: str) -> str:
    s = s.strip().lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"[()\[\]]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def yes(v: str) -> bool:
    return _norm(v) in YES


def parse_date(v: str) -> date | None:
    v = (v or "").strip()
    if not v or _norm(v) in {"never", "never accessed", "-", "n/a", "none"}:
        return None
    v = re.sub(r"\.\d+", "", v).replace("Z", "")
    v = re.sub(r"[+-]\d{2}:?\d{2}$", "", v).strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    return None


def num(v: str, default: float = 0.0) -> float:
    m = re.search(r"-?\d+(\.\d+)?", (v or "").replace(",", ""))
    return float(m.group()) if m else default


def _split(v: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;|]", v or "") if x.strip()]


def _headers(fieldnames: list[str], aliases: dict) -> dict[str, str]:
    normed = {_norm(h): h for h in fieldnames if h}
    out = {}
    for canon, names in aliases.items():
        for a in names:
            if a in normed:
                out[canon] = normed[a]
                break
    return out


def _rows(path: Path, aliases: dict, required: str):
    if not path.exists():
        return [], {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        rows = list(rd)
        h = _headers(rd.fieldnames or [], aliases)
    if rows and required not in h:
        raise ValueError(f"{path.name}: no '{required}' column (tried {', '.join(aliases[required])})")
    return rows, h


def _getter(h: dict):
    return lambda r, k: (r.get(h[k]) or "").strip() if k in h else ""


@dataclass
class User:
    account_id: str
    name: str = ""
    email: str = ""
    status: str = "active"
    account_type: str = "atlassian"
    added: date | None = None
    access: dict[str, bool] = field(default_factory=dict)
    last_seen: dict[str, date | None] = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return self.email.split("@")[-1].lower() if "@" in self.email else ""

    @property
    def last_any(self) -> date | None:
        seen = [d for d in self.last_seen.values() if d]
        return max(seen) if seen else None


@dataclass
class Project:
    key: str
    name: str = ""
    type: str = "software"
    lead: str = ""
    last_update: date | None = None
    issues: int = 0
    permission_scheme: str = ""
    workflow_scheme: str = ""
    browse_anyone: bool = False
    archived: bool = False
    category: str = ""


@dataclass
class Space:
    key: str
    name: str = ""
    type: str = "global"
    status: str = "current"
    last_update: date | None = None
    pages: int = 0
    admins: list[str] = field(default_factory=list)
    anonymous: bool = False


@dataclass
class Sprint:
    board: str
    project: str = ""
    name: str = ""
    state: str = "closed"
    start: date | None = None
    end: date | None = None
    complete: date | None = None
    committed: float = 0.0
    completed: float = 0.0
    added: float = 0.0
    carried: float = 0.0


@dataclass
class CustomField:
    name: str
    type: str = ""
    contexts: int = 1
    projects: int = 0          # 0 = global
    issues: int = 0            # -1 = not known (the REST API does not return it)
    last_used: date | None = None


@dataclass
class Settings:
    site: str = "your-site.atlassian.net"
    as_of: date | None = None
    managed_domains: list[str] = field(default_factory=list)
    seats: dict[str, int] = field(default_factory=dict)            # product -> licensed seats bought
    price: dict[str, float] = field(default_factory=dict)          # product -> price per user per month
    currency: str = "€"
    inactive_days: int = 90
    never_used_days: int = 30
    admin_groups: list[str] = field(default_factory=lambda: ["site-admins", "org-admins", "jira-admins", "confluence-admins", "administrators"])
    max_admins: int = 5
    service_patterns: list[str] = field(default_factory=lambda: ["svc", "service", "automation", "integration", "bot", "api", "noreply"])
    service_owners: dict[str, str] = field(default_factory=dict)  # account email or id -> owner
    project_stale_days: int = 180
    space_stale_days: int = 365
    field_unused_days: int = 365
    custom_field_budget: int = 400
    shared_scheme_min: int = 3       # a scheme used by fewer projects than this counts as a one-off
    sprint_window: int = 6
    carryover_max_pct: float = 20.0
    scope_added_max_pct: float = 15.0
    say_do_min_pct: float = 70.0
    board_idle_days: int = 45
    sprint_overdue_days: int = 3


def settings_from_dict(d: dict) -> Settings:
    s = Settings()
    for k in ("site", "currency"):
        if k in d:
            setattr(s, k, str(d[k]))
    for k in ("inactive_days", "never_used_days", "max_admins", "project_stale_days", "space_stale_days", "field_unused_days",
              "custom_field_budget", "shared_scheme_min", "sprint_window", "board_idle_days", "sprint_overdue_days"):
        if k in d:
            setattr(s, k, int(d[k]))
    for k in ("carryover_max_pct", "scope_added_max_pct", "say_do_min_pct"):
        if k in d:
            setattr(s, k, float(d[k]))
    for k in ("managed_domains", "admin_groups", "service_patterns"):
        if k in d:
            setattr(s, k, [str(x).lower() for x in d[k]])
    s.seats = {str(k).lower(): int(v) for k, v in d.get("seats", {}).items()}
    s.price = {str(k).lower(): float(v) for k, v in d.get("price", {}).items()}
    s.service_owners = {str(k).lower(): str(v) for k, v in d.get("service_owners", {}).items()}
    if d.get("as_of"):
        s.as_of = parse_date(str(d["as_of"]))
    return s


def load_users(path: Path) -> list[User]:
    rows, h = _rows(path, USER_ALIASES, "account_id")
    if rows and "account_id" not in h and "email" in h:
        h["account_id"] = h["email"]
    g = _getter(h)
    out = []
    for r in rows:
        aid = g(r, "account_id") or g(r, "email")
        if not aid:
            continue
        fallback = parse_date(g(r, "last_active"))
        access = {p: yes(g(r, f"{p}_access")) for p in PRODUCTS}
        last = {p: (parse_date(g(r, f"last_seen_{p}")) if f"last_seen_{p}" in h else (fallback if access[p] else None)) for p in PRODUCTS}
        at = _norm(g(r, "account_type")) or "atlassian"
        out.append(User(account_id=aid, name=g(r, "name"), email=g(r, "email").lower(), added=parse_date(g(r, "added")),
                        status=STATUS_MAP.get((_norm(g(r, "status")).split() or ["active"])[0], "active"),
                        account_type="app" if at in {"app", "bot", "app account"} else "customer" if at == "customer" else "atlassian",
                        access=access, last_seen=last))
    return out


def load_groups(path: Path) -> list[tuple[str, str]]:
    rows, h = _rows(path, GROUP_ALIASES, "group")
    g = _getter(h)
    return [(g(r, "group").lower(), g(r, "member").lower()) for r in rows if g(r, "group") and g(r, "member")]


def load_projects(path: Path) -> list[Project]:
    rows, h = _rows(path, PROJECT_ALIASES, "key")
    g = _getter(h)
    out = []
    for r in rows:
        if not g(r, "key"):
            continue
        t = _norm(g(r, "type"))
        out.append(Project(key=g(r, "key").upper(), name=g(r, "name"), lead=g(r, "lead").lower(), last_update=parse_date(g(r, "last_update")),
                           type="service" if "service" in t else "business" if "business" in t or "work" in t else "software",
                           issues=int(num(g(r, "issues"))), permission_scheme=g(r, "permission_scheme"), workflow_scheme=g(r, "workflow_scheme"),
                           browse_anyone=yes(g(r, "browse_anyone")), archived=yes(g(r, "archived")), category=g(r, "category")))
    return out


def load_spaces(path: Path) -> list[Space]:
    rows, h = _rows(path, SPACE_ALIASES, "key")
    g = _getter(h)
    out = []
    for r in rows:
        if not g(r, "key"):
            continue
        out.append(Space(key=g(r, "key"), name=g(r, "name"), type="personal" if "personal" in _norm(g(r, "type")) else "global",
                         status="archived" if "archiv" in _norm(g(r, "status")) else "current", last_update=parse_date(g(r, "last_update")),
                         pages=int(num(g(r, "pages"))), admins=[a.lower() for a in _split(g(r, "admins"))], anonymous=yes(g(r, "anonymous"))))
    return out


def load_sprints(path: Path) -> list[Sprint]:
    rows, h = _rows(path, SPRINT_ALIASES, "board")
    g = _getter(h)
    out = []
    for r in rows:
        if not g(r, "board"):
            continue
        st = _norm(g(r, "state"))
        out.append(Sprint(board=g(r, "board"), project=g(r, "project").upper(), name=g(r, "sprint"),
                          state="active" if st in {"active", "open", "in progress"} else "future" if st in {"future", "planned"} else "closed",
                          start=parse_date(g(r, "start")), end=parse_date(g(r, "end")), complete=parse_date(g(r, "complete")),
                          committed=num(g(r, "committed")), completed=num(g(r, "completed")), added=num(g(r, "added")), carried=num(g(r, "carried"))))
    return out


def load_fields(path: Path) -> list[CustomField]:
    rows, h = _rows(path, FIELD_ALIASES, "name")
    g = _getter(h)
    out = []
    for r in rows:
        if not g(r, "name"):
            continue
        p = g(r, "projects")
        out.append(CustomField(name=g(r, "name"), type=g(r, "type"), contexts=int(num(g(r, "contexts"), 1)),
                               projects=0 if _norm(p) in {"global", "all", ""} else int(num(p)), issues=int(num(g(r, "issues"), -1)),
                               last_used=parse_date(g(r, "last_used"))))
    return out


@dataclass
class Data:
    users: list[User]
    groups: list[tuple[str, str]]
    projects: list[Project]
    spaces: list[Space]
    sprints: list[Sprint]
    fields: list[CustomField]
    settings: Settings
    as_of: date

    def __post_init__(self):
        self.by_key: dict[str, User] = {}
        for u in self.users:
            self.by_key[u.account_id.lower()] = u
            if u.email:
                self.by_key[u.email] = u
        for grp, member in self.groups:
            u = self.by_key.get(member)
            if u and grp not in u.groups:
                u.groups.append(grp)

    def user(self, ref: str) -> User | None:
        return self.by_key.get((ref or "").lower())


def load(folder: Path, as_of: date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "users.csv").exists():
        raise FileNotFoundError(f"{folder / 'users.csv'} not found")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    users = load_users(folder / "users.csv")
    when = as_of or s.as_of or max([u.last_any for u in users if u.last_any] or [date.today()])
    return Data(users, load_groups(folder / "group_members.csv"), load_projects(folder / "projects.csv"), load_spaces(folder / "spaces.csv"),
                load_sprints(folder / "sprints.csv"), load_fields(folder / "custom_fields.csv"), s, when)
