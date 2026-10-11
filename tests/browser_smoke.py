"""Real-browser smoke test against a disposable running dashboard container.

The target MUST be isolated: this script saves demo observations. Start it with
`docker run --rm -d --name phc-supplysignal-ui-test -p 127.0.0.1:8502:8501
phc-supplysignal-dashboard`, then run this file with --url http://127.0.0.1:8502.
Requires the optional Playwright Python package and a Chromium executable.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


RECIPIENT = "Idi Emi Akilapa Leemp Community Project"
DONOR = "Akinbola Health Center"
PRODUCT = "Oxytocin injection, example unit"
ROOT = Path(__file__).resolve().parents[1]


def wait_for_render(page) -> None:
    expect(page.get_by_test_id("stApp")).to_have_attribute(
        "data-test-script-state", "notRunning", timeout=20000,
    )


def choose(page, field: str, label: str) -> None:
    wait_for_render(page)
    box = page.get_by_role("combobox", name=field)
    box.click()
    page.keyboard.type(label.split()[0])
    page.get_by_role("option", name=label, exact=True).click()
    expect(box).to_have_value(label)
    wait_for_render(page)


def save_count(page, units: int) -> None:
    choose(page, "Observation", "Physical stock count")
    expect(page.get_by_role("textbox", name="Recorded by (name or role)", exact=True)).to_have_count(1)
    page.get_by_role("spinbutton", name="Units").fill(str(units))
    page.get_by_role("textbox", name="Recorded by (name or role)", exact=True).fill("Browser smoke test")
    page.get_by_role("button", name="Save observation and update queue").click()
    wait_for_render(page)


def run(url: str, browser_executable: str | None, evidence_dir: Path | None = None) -> None:
    with sync_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox"]}
        if browser_executable:
            options["executable_path"] = browser_executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(accept_downloads=True, viewport={"width": 1440, "height": 1000})
        # A local deployment must not depend on a public-internet response.
        allowed_host = urlsplit(url).netloc
        page.route("**/*", lambda route: route.continue_()
                   if urlsplit(route.request.url).netloc == allowed_host else route.abort())
        if evidence_dir:
            evidence_dir.mkdir(parents=True, exist_ok=True)

        def capture(name):
            if evidence_dir:
                wait_for_render(page)
                page.screenshot(path=str(evidence_dir / f"{name}.png"), full_page=True)
        page_errors = []
        media_responses = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "response",
            lambda response: media_responses.append((response.url, response.status, response.body()))
            if "/media/" in response.url and response.url.endswith(".csv") else None,
        )
        page.goto(url, wait_until="domcontentloaded")
        expect(page.get_by_text("PHC SupplySignal", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Where the work is", exact=True)).to_be_visible()
        expect(page.get_by_text("First ten facility calls", exact=False)).to_be_visible()
        expect(page.get_by_text("10 calls cover 24 product checks", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Open call")).to_have_count(10)
        # The basemap is stored locally, so all 28 PHC markers render with external requests blocked.
        expect(page.locator(".js-plotly-plot .scatterlayer .point")).to_have_count(28, timeout=20000)
        capture("01_worklist")
        print("PASS map renders offline with 28 PHCs and ten call cards")
        with page.expect_download() as sheet_download_event:
            page.get_by_role("button", name="Download call worksheet (text)").click()
        worksheet = sheet_download_event.value
        assert worksheet.failure() is None
        text = Path(worksheet.path()).read_text()
        assert text.count("\nCALL ") == 10
        assert text.count("  Product:") == 24
        assert "UNKNOWN, never zero" in text and "no automatic upload" in text
        print("PASS offline worksheet has ten facility calls, 24 product checks and explicit unknowns")
        page.get_by_text("Full backlog: all 52 product cases", exact=False).click()
        expect(page.get_by_text("Showing 52 of 52 product cases", exact=False)).to_be_visible()
        with page.expect_download() as full_download_event:
            page.get_by_role("button", name="Download full backlog (52)").click()
        full_download = full_download_event.value
        assert full_download.suggested_filename.endswith(".csv")
        assert full_download.failure() is None
        full_responses = [body for url, status, body in media_responses if status == 200]
        assert full_responses, "Browser did not receive CSV media response"
        full_rows = list(csv.DictReader(io.StringIO(full_responses[-1].decode("utf-8-sig"))))
        assert len(full_rows) == 52, len(full_rows)
        assert "follow_up_status" in full_rows[0]
        print("PASS CSV download produces 52 readable backlog rows")
        page.get_by_role("button", name="Filter cases").click()
        page.get_by_role("radiogroup", name="Worklist size").get_by_text("10", exact=True).click()
        page.keyboard.press("Escape")
        with page.expect_download() as displayed_download_event:
            page.get_by_role("button", name="Download displayed cases (10)").click()
        assert displayed_download_event.value.failure() is None
        displayed_rows = list(csv.DictReader(io.StringIO(media_responses[-1][2].decode("utf-8-sig"))))
        assert len(displayed_rows) == 10, len(displayed_rows)
        print("PASS displayed-case export follows the ten-case filter")
        page.get_by_role("tab", name="Worklist").click()
        page.get_by_role("button", name="Open call").first.click()
        wait_for_render(page)
        expect(page.get_by_role("combobox", name="Facility")).to_have_value("Abujakan Health Center", timeout=20000)
        expect(page.get_by_text("Products at this clinic:", exact=False)).to_be_visible()
        print("PASS call card opens the clinic on the Verify and update tab")
        page.get_by_role("tab", name="Data and evidence").click()
        expect(page.get_by_text("On six alternate seeds", exact=False)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Ten PHC calls: does the order help?", exact=True)).to_be_visible()
        expect(page.get_by_text("in 5 of 40 calls versus 8 of 40", exact=False)).to_be_visible()
        page.get_by_role("tab", name="Import preview").click()
        page.get_by_role("button", name="Create verification preview").click()
        expect(page.get_by_text("2 expected facility-product pairs; 2 need a verification check", exact=False)).to_be_visible(timeout=20000)
        print("PASS fictional LMIS import exposes low cover and never-reporting roster pair")
        page.get_by_text("Use fictional sample files", exact=True).click()
        upload_inputs = page.locator('input[type="file"]')
        upload_inputs.nth(0).set_input_files(str(ROOT / "data/example_lmis_input.csv"))
        upload_inputs.nth(1).set_input_files(str(ROOT / "data/example_roster.csv"))
        upload_inputs.nth(2).set_input_files(str(ROOT / "data/example_mapping.json"))
        page.get_by_role("button", name="Create verification preview").click()
        expect(page.get_by_text("Uploaded extract: 2 expected facility-product pairs", exact=False)).to_be_visible(timeout=20000)
        print("PASS uploaded LMIS CSV, roster, and field mapping produce a worklist")
        page.get_by_role("tab", name="Verify and update").click()
        page.get_by_role("combobox", name="Facility").wait_for(timeout=20000)
        expect(page.get_by_role("combobox", name="Open a worklist case")).to_be_visible()
        page.get_by_role("button", name="Open selected case").click()
        expect(page.get_by_role("combobox", name="Facility")).to_have_value("Abujakan Health Center")
        choose(page, "Facility", RECIPIENT)
        choose(page, "Product", PRODUCT)
        expect(page.get_by_text("Current decision: Verify stock", exact=False)).to_be_visible()
        expect(page.get_by_text("Why it appeared:", exact=False)).to_be_visible()
        choose(page, "Follow-up outcome", "Facility unreachable")
        page.get_by_role("textbox", name="Follow-up recorded by (name or role)").fill("Browser smoke test")
        page.get_by_role("textbox", name="Follow-up note").fill("No answer after two calls")
        page.get_by_role("button", name="Save follow-up").click()
        expect(page.get_by_text("Follow-up status: Facility unreachable", exact=False)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Current decision: Verify stock", exact=False)).to_be_visible()
        print("PASS follow-up persists without changing the supply alert")

        # An empty recorder must not create an observation.
        page.get_by_role("spinbutton", name="Units").fill("0")
        page.get_by_role("button", name="Save observation and update queue").click()
        expect(page.get_by_text("Recorder name or role is required", exact=False)).to_be_visible()
        save_count(page, 0)
        expect(page.get_by_text("Current decision: Verify donor", exact=False)).to_be_visible(timeout=20000)
        print("PASS recipient count promotes case to donor verification")

        choose(page, "Facility", DONOR)
        choose(page, "Product", PRODUCT)
        expect(page.get_by_text("Current decision: No immediate action", exact=False)).to_be_visible(timeout=20000)
        save_count(page, 32)
        expect(page.get_by_text("Last physical count: 2026-10-04", exact=False)).to_be_visible(timeout=20000)
        choose(page, "Facility", RECIPIENT)
        expect(page.get_by_text("Current decision: Check transfer", exact=False)).to_be_visible(timeout=20000)
        expect(page.get_by_text("Proposed transfer: 2 units from Akinbola Health Center", exact=False)).to_be_visible()
        expect(page.get_by_text("This proposal leaves", exact=False)).to_be_visible()
        capture("02_conditional_transfer")
        print("PASS donor count unlocks conditional transfer proposal")

        choose(page, "Observation", "Delivery expected")
        page.get_by_role("spinbutton", name="Units").fill("20")
        page.get_by_role("textbox", name="Recorded by (name or role)", exact=True).fill("Browser smoke test")
        page.get_by_role("button", name="Save observation and update queue").click()
        expect(page.get_by_text("Current decision: Check transfer", exact=False)).to_be_visible(timeout=20000)
        expect(page.get_by_text("An unconfirmed delivery is expected on 2026-10-07", exact=False)).to_be_visible()
        print("PASS expected delivery does not add stock")

        choose(page, "Observation", "Delivery received")
        page.get_by_role("spinbutton", name="Units").fill("9")
        page.get_by_role("textbox", name="Delivery reference").fill("BROWSER-WAYBILL-001")
        page.get_by_role("textbox", name="Recorded by (name or role)", exact=True).fill("Browser smoke test")
        page.get_by_role("button", name="Save observation and update queue").click()
        expect(page.get_by_text("Current decision: No immediate action", exact=False)).to_be_visible(timeout=20000)
        print("PASS confirmed delivery changes stock and clears the shortage")

        page.get_by_role("spinbutton", name="Units").fill("9")
        page.get_by_role("textbox", name="Delivery reference").fill("BROWSER-WAYBILL-001")
        page.get_by_role("textbox", name="Recorded by (name or role)", exact=True).fill("Browser smoke test")
        page.get_by_role("button", name="Save observation and update queue").click()
        expect(page.get_by_text("already recorded", exact=False)).to_be_visible(timeout=20000)
        print("PASS duplicate receipt rejected")

        page.reload(wait_until="domcontentloaded")
        page.get_by_role("tab", name="Verify and update").click()
        page.get_by_role("combobox", name="Facility").wait_for(timeout=20000)
        choose(page, "Facility", RECIPIENT)
        choose(page, "Product", PRODUCT)
        expect(page.get_by_text("Current decision: No immediate action", exact=False)).to_be_visible(timeout=20000)
        print("PASS decision persists after page refresh")
        choose(page, "Facility", "Jarija Sango Ibon Health Center")
        choose(page, "Product", "Misoprostol tablet, example unit")
        save_count(page, 0)
        expect(page.get_by_text("Current decision: Escalate resupply", exact=False)).to_be_visible(timeout=20000)
        capture("03_no_donor_escalation")
        print("PASS verified shortage without a donor escalates for resupply")
        assert not page_errors, f"Browser page errors: {page_errors}"
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    run(args.url, args.browser_executable, args.evidence_dir)
