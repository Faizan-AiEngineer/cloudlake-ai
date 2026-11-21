import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
from openpyxl import load_workbook
from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ("/", "Platform overview", "01-executive-overview"),
    ("/sources", "Data sources", "02-data-sources"),
    ("/lakehouse", "Lakehouse explorer", "03-lakehouse-explorer"),
    ("/pipelines", "Pipeline manager", "04-pipeline-timeline"),
    ("/quality", "Data quality", "05-data-quality"),
    ("/lineage", "Data lineage", "06-data-lineage"),
    ("/analytics", "Business analytics", "07-business-analytics"),
    ("/assistant", "AI operations assistant", "08-operations-assistant"),
    ("/infrastructure", "Cloud infrastructure", "09-cloud-infrastructure"),
    ("/alerts", "Alerts & monitoring", None),
    ("/reports", "Reports", None),
    ("/settings", "Settings", None),
]


def wait_http(url, process, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with status {process.returncode}")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Service did not respond at {url}")


def terminate(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--chrome")
    parser.add_argument("--startup-timeout", type=int, default=120, help="Maximum seconds to wait for each service")
    parser.add_argument("--screens", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--trigger", action="store_true", help="Verify a real incremental no-op from the browser")
    options = parser.parse_args()
    if not options.node:
        parser.error("Node was not found on PATH. Pass --node.")
    if options.screens:
        options.screens.mkdir(parents=True, exist_ok=True)
    if options.exports:
        options.exports.mkdir(parents=True, exist_ok=True)
    logs = ROOT / ".runtime/verification"
    logs.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        flag = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        api_log = stack.enter_context((logs / "api.log").open("wb"))
        web_log = stack.enter_context((logs / "web.log").open("wb"))
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT, stdout=api_log, stderr=subprocess.STDOUT, creationflags=flag,
        )
        stack.callback(terminate, api)
        web = subprocess.Popen(
            [options.node, "node_modules/vite/bin/vite.js", "preview", "--host", "127.0.0.1",
             "--port", "5173", "--strictPort"],
            cwd=ROOT / "frontend", stdout=web_log, stderr=subprocess.STDOUT, creationflags=flag,
        )
        stack.callback(terminate, web)
        wait_http("http://127.0.0.1:8000/ready", api, options.startup_timeout)
        wait_http("http://127.0.0.1:5173/", web, options.startup_timeout)

        api_url = "http://127.0.0.1:8000/api/v1"
        with httpx.Client(base_url=api_url, timeout=25) as client:
            published = client.get("/overview").raise_for_status().json()
            assert published["published_run"] and published["processed"] > 0
            blocked = client.get("/runs", params={"status": "blocked", "limit": 1}).raise_for_status().json()["items"]
            for zone, name in (("bronze", "orders"), ("silver", "orders"), ("gold", "fact_sales")):
                assert client.get(f"/lakehouse/{zone}/{name}").raise_for_status().json()["total"] > 0
            all_sales = client.get("/analytics").raise_for_status().json()
            germany = client.get("/analytics", params={"country": "DE"}).raise_for_status().json()
            assert 0 < germany["kpis"]["revenue_usd"] < all_sales["kpis"]["revenue_usd"]
            files = {suffix: client.get(f"/reports/executive/{suffix}").raise_for_status().content
                     for suffix in ("pdf", "csv", "xlsx")}
            pdf = PdfReader(io.BytesIO(files["pdf"]))
            assert "Executive platform report" in pdf.pages[0].extract_text()
            assert b"Source datasets" in files["csv"]
            assert "Sales metrics" in load_workbook(io.BytesIO(files["xlsx"]), read_only=True).sheetnames
            if options.exports:
                for suffix, contents in files.items():
                    (options.exports / f"sample-cloudlake-report.{suffix}").write_bytes(contents)
        errors = []
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=options.chrome)
            context = browser.new_context(viewport={"width": 1440, "height": 1060}, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda entry: errors.append(entry.text) if entry.type == "error" else None)
            page.on("response", lambda response: errors.append(f"{response.status} {response.url}")
                    if response.status >= 400 else None)
            for path, title, name in PAGES:
                if path == "/":
                    page.goto("http://127.0.0.1:5173/")
                else:
                    page.locator(f'nav a[href="{path}"]').click()
                expect(page.get_by_role("heading", level=1, name=title, exact=True)).to_be_visible(timeout=25000)
                page.wait_for_load_state("networkidle")
                assert not page.get_by_role("alert").count(), path
                if path == "/assistant":
                    page.get_by_role("button", name="How has revenue changed this month?").click()
                    expect(page.get_by_text("Sales analytics", exact=True)).to_be_visible(timeout=12000)
                    page.get_by_role("textbox", name="Operational question").fill("What is the weather in Tokyo?")
                    page.get_by_role("button", name="Ask", exact=True).click()
                    expect(page.get_by_text("Unsupported", exact=True)).to_be_visible(timeout=12000)
                if path == "/pipelines":
                    page.get_by_role("button", name=re.compile(published["published_run"][:8])).click()
                    expect(page.get_by_text("Build gold", exact=True)).to_be_visible(timeout=12000)
                if path == "/analytics":
                    expect(page.get_by_text("Recognized revenue", exact=True)).to_be_visible(timeout=12000)
                if path == "/lineage":
                    page.get_by_role("button", name="Zoom in").click()
                    page.get_by_role("button", name="Fact sales", exact=True).click()
                    expect(page.get_by_role("heading", name="Fact sales")).to_be_visible()
                if path == "/quality" and blocked:
                    page.get_by_label("Pipeline run").select_option(blocked[0]["id"])
                    expect(page.get_by_text("completeness", exact=False).first).to_be_visible(timeout=15000)
                if path == "/reports":
                    with page.expect_download(timeout=15000) as download:
                        page.get_by_role("button", name="Download Executive platform report CSV").click()
                    assert download.value.suggested_filename == "cloudlake-executive.csv"
                if name and options.screens:
                    page.screenshot(path=options.screens / f"{name}.png", full_page=True, animations="disabled")
                print(f"Verified {path}", flush=True)
            if options.trigger:
                page.locator('nav a[href="/pipelines"]').click()
                page.get_by_label("Execution mode").select_option("incremental")
                with page.expect_response(lambda response: response.url.endswith("/api/v1/runs")
                                          and response.request.method == "POST") as started:
                    page.get_by_role("button", name="Start run").click()
                assert started.value.status == 202
                run_id = started.value.json()["run_id"]
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    run = httpx.get(f"{api_url}/runs/{run_id}",timeout=8).raise_for_status().json()["run"]
                    if run["status"] in {"successful", "blocked", "failed"}:
                        assert run["status"] == "successful" and run["details"]["noop"] and run["trigger"] == "api", run
                        assert httpx.get(f"{api_url}/runs/{run_id}/logs",timeout=8).json()["available"]
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("Timed out waiting for API-triggered run")
            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("button", name="Toggle navigation").click()
            page.locator('nav a[href="/"]').click()
            expect(page.get_by_role("heading", name="Platform overview")).to_be_visible()
            width, content_width = page.evaluate("() => [innerWidth,document.documentElement.scrollWidth]")
            assert content_width <= width + 1, (width, content_width)
            browser.close()
        assert not errors, errors
        print("Demo verified against live API and browser", flush=True)


if __name__ == "__main__":
    main()
