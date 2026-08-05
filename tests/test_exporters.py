import json
import xml.etree.ElementTree as ET
import pytest
from openharness import export_to_json, export_to_html, export_to_junit_xml


def test_exporters():
    sample_run = {
        "id": "run_123",
        "name": "Suite 1",
        "timestamp": 1700000000.0,
        "passed_count": 1,
        "total_count": 1,
        "duration_ms": 100.0,
        "results": [
            {
                "test_case_name": "Case A",
                "passed": True,
                "total_score": 1.0,
                "duration_ms": 100.0,
                "metrics": [
                    {"name": "m1", "category": "assertion", "passed": True, "reason": "Good"}
                ]
            }
        ]
    }

    json_out = export_to_json(sample_run)
    parsed = json.loads(json_out)
    assert parsed["id"] == "run_123"

    html_out = export_to_html(sample_run)
    assert "OpenHarness Evaluation Report" in html_out
    assert "Suite 1" in html_out

    junit_out = export_to_junit_xml(sample_run)
    root = ET.fromstring(junit_out)
    assert root.tag == "testsuite"
    assert root.attrib["name"] == "Suite 1"
