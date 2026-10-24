"""Unit tests for jcadmin. Run with `python -m pytest -q` (or `python -m unittest`)."""
from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from jcadmin import checks, cli, simulate
from jcadmin.model import (CustomField, Data, Project, Settings, Space, Sprint, User, load, parse_date, settings_from_dict, yes)

AS_OF = date(2026, 10, 24)
D = lambda n: AS_OF - timedelta(days=n)  # noqa: E731


def user(email="ana@fabrikam.com", jira=True, conf=True, jsm=False, seen=5, status="active", added=400, kind="atlassian", name="Ana Garcia"):
    return User(account_id=email or name, name=name, email=email, status=status, account_type=kind, added=D(added) if added is not None else None,
                access={"jira": jira, "confluence": conf, "jsm": jsm},
                last_seen={"jira": D(seen) if (jira and seen is not None) else None, "confluence": D(seen) if (conf and seen is not None) else None,
                           "jsm": D(seen) if (jsm and seen is not None) else None})


def settings(**kw) -> Settings:
    s = Settings(managed_domains=["fabrikam.com"], seats={"jira": 10, "confluence": 10}, price={"jira": 10.0, "confluence": 5.0})
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def data(users=None, groups=None, projects=None, spaces=None, sprints=None, fields=None, s=None) -> Data:
    return Data(users if users is not None else [user()], groups or [], projects or [], spaces or [], sprints or [], fields or [], s or settings(), AS_OF)


class Parsing(unittest.TestCase):
    def test_values(self):
        self.assertTrue(yes("Yes")); self.assertTrue(yes("Has access")); self.assertFalse(yes("No")); self.assertFalse(yes(""))
        self.assertEqual(parse_date("2026-10-24T08:00:00.000Z"), AS_OF)
        self.assertEqual(parse_date("24 Oct 2026"), AS_OF)
        self.assertIsNone(parse_date("Never accessed"))

    def test_atlassian_user_export_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "users.csv").write_text(
                "User id,User name,email,User status,Added to org,Jira Software,Confluence,Last seen in Jira Software,Last seen in Confluence\n"
                "abc,Ana Garcia,Ana@Fabrikam.com,Active,2025-01-10,Has access,No,2026-10-20,\n"
                "def,Old User,old@fabrikam.com,Suspended - access removed,2024-01-10,Has access,Has access,Never accessed,2026-01-01\n", encoding="utf-8")
            (p / "group_members.csv").write_text("Group name,Email\nsite-admins,ana@fabrikam.com\n", encoding="utf-8")
            d = load(p)
            a, o = d.users
            self.assertEqual(a.email, "ana@fabrikam.com")
            self.assertTrue(a.access["jira"]); self.assertFalse(a.access["confluence"])
            self.assertEqual(a.last_seen["jira"], date(2026, 10, 20))
            self.assertEqual(o.status, "suspended")
            self.assertIsNone(o.last_seen["jira"])
            self.assertEqual(a.groups, ["site-admins"])
            self.assertEqual(d.as_of, date(2026, 10, 20))

    def test_settings(self):
        s = settings_from_dict({"seats": {"Jira": 400}, "price": {"jira": "8.6"}, "managed_domains": ["Fabrikam.com"], "max_admins": 4,
                                "say_do_min_pct": 75, "service_owners": {"SVC@fabrikam.com": "Ops"}})
        self.assertEqual(s.seats, {"jira": 400}); self.assertEqual(s.price["jira"], 8.6)
        self.assertEqual(s.managed_domains, ["fabrikam.com"]); self.assertEqual(s.max_admins, 4)
        self.assertEqual(s.say_do_min_pct, 75.0); self.assertEqual(s.service_owners, {"svc@fabrikam.com": "Ops"})


class Licences(unittest.TestCase):
    def verdicts(self, u):
        return {r["product"]: (r["verdict"], r["why"]) for r in checks.licence_rows(data([u]))}

    def test_active_user_is_kept(self):
        self.assertEqual(self.verdicts(user())["jira"][0], "keep")

    def test_inactive_never_used_and_suspended(self):
        self.assertIn("last seen 120 days ago", self.verdicts(user(seen=120))["jira"][1])
        never = self.verdicts(user(seen=None, added=60))
        self.assertTrue(never["jira"][1].startswith("never used"))
        self.assertEqual(self.verdicts(user(seen=None, added=5))["jira"][0], "keep", "new joiners get a grace period")
        self.assertIn("suspended", self.verdicts(user(status="suspended"))["confluence"][1])

    def test_app_and_customer_accounts_are_not_licences(self):
        self.assertEqual(checks.licence_rows(data([user(kind="app"), user(email="c@x.com", kind="customer")])), [])

    def test_seats_and_saving(self):
        users = [user(email=f"u{i}@fabrikam.com", conf=False, seen=120 if i < 3 else 1) for i in range(12)]
        d = data(users)
        seats = {r["product"]: r for r in checks.seat_rows(d)}
        self.assertEqual((seats["jira"]["assigned"], seats["jira"]["reclaim"], seats["jira"]["after"]), (12, 3, 9))
        self.assertEqual(seats["jira"]["saving_year"], 360.0)
        f = checks.run_all(d)
        self.assertTrue(any(x.code == "LIC-03" and x.severity == checks.CRITICAL for x in f), "12 users on 10 seats")


class Access(unittest.TestCase):
    def test_admin_problems(self):
        users = [user("ok@fabrikam.com"), user("gone@fabrikam.com", status="deactivated"), user("idle@fabrikam.com", seen=200),
                 user("dev@gmail.com")]
        groups = [("site-admins", u.email) for u in users]
        d = data(users, groups)
        rows = {r["account"]: r for r in checks.access_rows(d)}
        self.assertEqual(rows["ok@fabrikam.com"]["issues"], [])
        self.assertIn("deactivated account still in site-admins", rows["gone@fabrikam.com"]["issues"])
        self.assertIn("admin not seen for 200 days", rows["idle@fabrikam.com"]["issues"])
        self.assertIn("admin from an unmanaged domain (gmail.com)", rows["dev@gmail.com"]["issues"])
        codes = {x.code for x in checks.run_all(d)}
        self.assertTrue({"ACC-02", "ACC-03"} <= codes)

    def test_externals_and_service_accounts(self):
        s = settings(service_owners={"svc-jenkins@fabrikam.com": "Platform"})
        users = [user("p@partner.io"), user("svc-jenkins@fabrikam.com", name="svc-jenkins"), user("jira.integration@fabrikam.com", name="Jira Integration"),
                 user("ana.svcetti@fabrikam.com", name="Ana Svcetti")]
        rows = {r["account"]: r for r in checks.access_rows(data(users, s=s))}
        self.assertEqual(rows["p@partner.io"]["kind"], "external")
        self.assertEqual(rows["svc-jenkins@fabrikam.com"]["issues"], [], "owner named in settings")
        self.assertIn("service account without a named owner", rows["jira.integration@fabrikam.com"]["issues"])
        self.assertNotIn("ana.svcetti@fabrikam.com", rows, "a surname is not a service account")


class JiraAndConfluence(unittest.TestCase):
    def test_projects(self):
        users = [user("lead@fabrikam.com"), user("left@fabrikam.com", status="deactivated")]
        ps = [Project("OK", lead="lead@fabrikam.com", last_update=D(3), permission_scheme="Shared", workflow_scheme="W"),
              Project("OLD", lead="lead@fabrikam.com", last_update=D(400), permission_scheme="Shared", workflow_scheme="W"),
              Project("PUB", lead="lead@fabrikam.com", last_update=D(3), browse_anyone=True, permission_scheme="Shared", workflow_scheme="W"),
              Project("ORPH", lead="left@fabrikam.com", last_update=D(3), permission_scheme="Own", workflow_scheme="W"),
              Project("ARC", archived=True)]
        rows = {r["key"]: r for r in checks.project_rows(data(users, projects=ps))}
        self.assertNotIn("ARC", rows)
        self.assertEqual(rows["OK"]["verdict"], "ok")
        self.assertEqual(rows["OLD"]["verdict"], "archive")
        self.assertEqual(rows["PUB"]["verdict"], "fix")
        self.assertEqual(rows["ORPH"]["verdict"], "fix")
        self.assertIn("one-off permission scheme 'Own'", rows["ORPH"]["notes"])
        codes = [x.code for x in checks.run_all(data(users, projects=ps))]
        self.assertIn("JIR-01", codes); self.assertIn("JIR-02", codes)

    def test_custom_fields(self):
        fs = [CustomField("Used", issues=500, last_used=D(10), projects=3), CustomField("Never", issues=0),
              CustomField("Old", issues=40, last_used=D(800), projects=2), CustomField("Busy", issues=900, last_used=D(5), contexts=6, projects=4)]
        fs.append(CustomField("Unknown", issues=-1, last_used=None, projects=1))
        fs.append(CustomField("Tracked", issues=-1, last_used=D(20), projects=1))
        rows = {r["name"]: r["verdict"] for r in checks.field_rows(data(fields=fs))}
        self.assertEqual(rows, {"Used": "ok", "Never": "remove", "Old": "remove", "Busy": "review", "Unknown": "review", "Tracked": "ok"})
        f = next(x for x in checks.run_all(data(fields=fs, s=settings(custom_field_budget=3))) if x.code == "JIR-05")
        self.assertEqual(f.severity, checks.WARNING)

    def test_spaces(self):
        users = [user("a@fabrikam.com"), user("left@fabrikam.com", status="deactivated")]
        sp = [Space("OK", admins=["a@fabrikam.com"], last_update=D(3)), Space("PUB", admins=["a@fabrikam.com"], last_update=D(3), anonymous=True),
              Space("ORPH", admins=["left@fabrikam.com"], last_update=D(3)), Space("OLD", admins=["a@fabrikam.com"], last_update=D(900)),
              Space("~left", type="personal", admins=["left@fabrikam.com"], last_update=D(900)), Space("ARC", status="archived")]
        rows = {r["key"]: r["verdict"] for r in checks.space_rows(data(users, spaces=sp))}
        self.assertEqual(rows, {"OK": "ok", "PUB": "fix", "ORPH": "fix", "OLD": "archive", "~left": "archive"})


class Agile(unittest.TestCase):
    def sprints(self, board, n=6, committed=40, completed=36, added=2, carried=3, last_end=5, active_end=None, future=True):
        out = []
        for i in range(n):
            end = D(last_end + 14 * (n - 1 - i))
            out.append(Sprint(board, "P", f"S{i}", "closed", end - timedelta(days=14), end, end, committed, completed, added, carried))
        if active_end is not None:
            out.append(Sprint(board, "P", "S-active", "active", D(active_end + 14), D(active_end)))
        if future:
            out.append(Sprint(board, "P", "S-next", "future"))
        return out

    def test_metrics_and_limits(self):
        sp = (self.sprints("Healthy", active_end=-7) + self.sprints("Carry", carried=12, active_end=-7)
              + self.sprints("Scope", added=10, active_end=-7) + self.sprints("Late", active_end=9)
              + self.sprints("Idle", last_end=90, future=False))
        rows = {r["board"]: r for r in checks.board_rows(data(sprints=sp))}
        self.assertEqual(rows["Healthy"]["say_do"], 90.0); self.assertEqual(rows["Healthy"]["verdict"], "ok")
        self.assertEqual(rows["Carry"]["carry"], 30.0); self.assertEqual(rows["Carry"]["verdict"], "attention")
        self.assertEqual(rows["Scope"]["added"], 25.0)
        self.assertTrue(rows["Late"]["overdue"])
        self.assertEqual(rows["Idle"]["verdict"], "idle"); self.assertEqual(rows["Idle"]["idle_days"], 90)
        codes = {x.code for x in checks.run_all(data(sprints=sp))}
        self.assertTrue({"AGL-01", "AGL-02", "AGL-03", "AGL-05"} <= codes)

    def test_only_the_last_window_counts(self):
        sp = self.sprints("B", n=10, active_end=-7)
        for x in sp[:4]:
            x.completed = 0
        r = checks.board_rows(data(sprints=sp, s=settings(sprint_window=6)))[0]
        self.assertEqual(r["sprints"], 6); self.assertEqual(r["say_do"], 90.0)


class Findings(unittest.TestCase):
    def test_ordering_and_area_status(self):
        users = [user("gone@fabrikam.com", status="deactivated")]
        f = checks.run_all(data(users, [("site-admins", "gone@fabrikam.com")], spaces=[Space("PUB", admins=["x"], anonymous=True)]))
        sev = [x.severity for x in f]
        self.assertEqual(sev, sorted(sev, key=checks.ORDER.get))
        st = checks.area_status(f)
        self.assertEqual(st["Access"], checks.CRITICAL); self.assertEqual(st["Agile delivery"], "ok")


class EndToEnd(unittest.TestCase):
    def test_demo_is_deterministic_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, out = Path(tmp) / "a", Path(tmp) / "b", Path(tmp) / "out"
            simulate.write(a); simulate.write(b)
            for name in ("users.csv", "projects.csv", "sprints.csv", "custom_fields.csv"):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
            self.assertEqual(cli.main(["review", str(a), "--out", str(out)]), 0)
            self.assertEqual({p.name for p in out.iterdir()}, set(cli.OUTPUTS))
            codes = {r["code"] for r in csv.DictReader((out / "findings.csv").open(encoding="utf-8"))}
            self.assertTrue({"LIC-01", "LIC-02", "LIC-03", "ACC-02", "ACC-03", "JIR-01", "CON-01", "AGL-01", "AGL-02", "AGL-05"} <= codes)
            md = (out / "admin-review.md").read_text(encoding="utf-8")
            self.assertIn("## Decisions for this review", md)
            self.assertIn("Robot Firmware", (out / "report.html").read_text(encoding="utf-8"))

    def test_missing_users_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli.main(["review", tmp, "--out", str(Path(tmp) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
