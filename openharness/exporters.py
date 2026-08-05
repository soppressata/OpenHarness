"""
Exporters module for OpenHarness.
Provides core functionality for the exporters subsystem.
"""
def export_static_html(data, path="output.html"):
    with open(path, "w") as f:
        f.write(f"<html><body><h1>OpenHarness Dashboard</h1><p>Data: {data}</p></body></html>")
