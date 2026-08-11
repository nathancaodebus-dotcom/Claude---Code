"""Network diagnostics: speed test."""
from __future__ import annotations

import speedtest

from tools.base import Tool


class NetworkSpeedTestTool(Tool):
    name = "run_speed_test"
    description = "Run a network speed test (download/upload/ping) from the machine Orion runs on. Takes ~20-30 seconds."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        st = speedtest.Speedtest()
        st.get_best_server()
        download_mbps = st.download() / 1_000_000
        upload_mbps = st.upload() / 1_000_000
        ping_ms = st.results.ping
        return f"Download: {download_mbps:.1f} Mbps, Upload: {upload_mbps:.1f} Mbps, Ping: {ping_ms:.0f} ms"
