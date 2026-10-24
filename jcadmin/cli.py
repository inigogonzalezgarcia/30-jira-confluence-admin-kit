"""Command line: `demo` builds everything from the fictional site, `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import report, simulate
from .checks import run_all
from .model import load, parse_date

OUTPUTS = ("report.html", "admin-review.md", "licences.csv", "seats.csv", "access-review.csv", "projects.csv", "spaces.csv", "fields.csv",
           "boards.csv", "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: date | None = None) -> dict:
    d = load(data, as_of)
    findings = run_all(d)
    b = report.build(d, findings)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, findings, title, b), encoding="utf-8")
    (out / "admin-review.md").write_text(report.review_md(d, findings, b), encoding="utf-8")
    report.write_licences(b, out / "licences.csv")
    report.write_seats(b, out / "seats.csv")
    report.write_access(b, out / "access-review.csv")
    report.write_projects(b, out / "projects.csv")
    report.write_spaces(b, out / "spaces.csv")
    report.write_fields(b, out / "fields.csv")
    report.write_boards(b, out / "boards.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    return report.summary(d, findings, b)


def _date(value: str) -> date:
    d = parse_date(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jcadmin", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional site to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, help="folder with users.csv (required) and group_members.csv, projects.csv, spaces.csv, sprints.csv, "
                                            "custom_fields.csv, settings.json (optional)")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Atlassian admin review")
    rv.add_argument("--as-of", type=_date, help="export date, YYYY-MM-DD (default: settings.json, or the latest last-seen date)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, "Fabrikam Robotics · Atlassian admin review")
    else:
        try:
            sm = run(a.data, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['licensed']} licensed users · {sm['reclaim']} licences to reclaim ({sm['reclaim_users']} users, {sm['saving']:,.0f} a year) · "
          f"{sm['admins']} admins · {sm['access_issues']} access issues · projects {sm['projects_flagged']}/{sm['projects']} · "
          f"spaces {sm['spaces_flagged']}/{sm['spaces']} · fields {sm['fields_remove']}/{sm['fields']} to remove · boards {sm['boards_flagged']}/{sm['boards']} · "
          f"{sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
