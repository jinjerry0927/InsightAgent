import json

from test_metrics import metric_db
from test_query_executor import safe_database
from scripts import ask


def test_demo_cli_runs_without_api_or_environment_keys(safe_database, monkeypatch, capsys):
    monkeypatch.setattr(ask, "load_settings", lambda: (_ for _ in ()).throw(AssertionError("No API configuration in demo")))
    monkeypatch.setattr("sys.argv", ["ask", "--demo", "월별 매출", "--database", str(safe_database),
                                     "--start", "2018-01-01", "--end", "2018-03-01"])
    assert ask.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "offline_fixture" and report["state"] == "success"
    assert report["api_attempts"] == 0 and report["rows"][0]["merchandise_value"] == {"$decimal": "41.00"}
    assert report["start_inclusive"] == "2018-01-01"
