"""Tests for progress_chart.py (classification) and wiki2html.py (conversion)."""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "fhir-jira" / "skills" / "fhir-jira-workflow" / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_export(path):
    path.write_text(
        "Issue key|Summary|Resolution|Status\n"
        "FHIR-1|applied one|Persuasive|Applied\n"
        "FHIR-2|merged not marked|Persuasive|Resolved - change required\n"
        "FHIR-3|in a PR|Persuasive|Resolved - change required\n"
        "FHIR-4|voted|Persuasive|Resolved - change required\n"
        "FHIR-5|proposed|Persuasive|Triaged\n"
        "FHIR-6|nothing yet||Submitted\n"
        "FHIR-7|voted in a meeting||Triaged\n"
        "FHIR-8|drafted locally||Triaged\n",
        encoding="utf-8",
    )


def test_classification_covers_every_category(tmp_path):
    pc = load("progress_chart")
    exp = tmp_path / "Jira export.csv"
    write_export(exp)
    cfg = {
        "export": str(exp),
        "pr_merged": {"FHIR-2": 10},
        "pr_open": {"FHIR-3": 11},
        "voted_not_entered": ["FHIR-7"],
        "dispositions_local": ["FHIR-8"],
        "extra": ["FHIR-9"],
        "exclude": [],
    }
    _, export = pc.read_export(cfg["export"])
    cat, _, _ = pc.classify(cfg, export)
    assert cat == {
        "FHIR-1": "applied", "FHIR-2": "done", "FHIR-3": "pr", "FHIR-4": "voted",
        "FHIR-5": "disposition", "FHIR-6": "none", "FHIR-7": "voted", "FHIR-8": "disposition",
        "FHIR-9": "none",
    }


def test_applied_status_wins_over_merged_pr(tmp_path):
    pc = load("progress_chart")
    exp = tmp_path / "Jira export.csv"
    write_export(exp)
    _, export = pc.read_export(str(exp))
    cat, _, _ = pc.classify({"pr_merged": {"FHIR-1": 12}}, export)
    assert cat["FHIR-1"] == "applied"


def test_new_and_same_iterations(tmp_path, monkeypatch):
    pc = load("progress_chart")
    exp = tmp_path / "Jira export.csv"
    write_export(exp)
    cfgp = tmp_path / "progress-config.json"
    cfgp.write_text(json.dumps({"export": str(exp), "out_dir": str(tmp_path)}), encoding="utf-8")
    for mode in ("new", "same", "new"):
        monkeypatch.setattr("sys.argv", ["progress_chart.py", mode, "--config", str(cfgp), "--date", "2026-10-05"])
        assert pc.main() == 0
    data = json.loads((tmp_path / "progress-data.json").read_text(encoding="utf-8"))
    assert [d["iteration"] for d in data] == [1, 2]
    assert (tmp_path / "progress.html").exists()
    assert (tmp_path / "progress-history" / "iteration-2.md").exists()


def test_wiki2html_tables_links_and_items():
    w = load("wiki2html")
    out = w.convert("h1. Agenda\n*1.* Roll call\n||Ticket||Summary||\n|[FHIR-1|https://jira.hl7.org/browse/FHIR-1]|Fix {{code}}|\n* a bullet\n")
    assert "<h1>Agenda</h1>" in out
    assert "<h3>1. Roll call</h3>" in out
    assert '<td><a href="https://jira.hl7.org/browse/FHIR-1">FHIR-1</a></td><td>Fix <code>code</code></td>' in out
    assert "<li>a bullet</li>" in out
