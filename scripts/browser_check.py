"""Exercise the real local app in an isolated database without paid API calls."""

import re
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import expect, sync_playwright

from customer_intelligence.main import create_app


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def status(self):
        return {
            name: {"configured": bool(self.get(name)), "environment": False}
            for name in ["openrouter", "tavily"]
        }


def main():
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="customer-intelligence-ui-") as directory:
        app = create_app(Path(directory), auth_token="browser-fixture", secret_store=MemorySecrets())
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=8878, log_level="error", access_log=False)
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(60):
            try:
                if httpx.get("http://127.0.0.1:8878/health").is_success:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto("http://127.0.0.1:8878/auth?token=browser-fixture")
                expect(page.get_by_role("heading", name="Accounts worth your attention.")).to_be_visible()
                expect(page.get_by_role("button", name="Find accounts", exact=True)).to_be_disabled()
                page.screenshot(path=str(artifacts / "onboarding.png"), full_page=True)
                page.get_by_role("button", name="See an example", exact=True).click()
                expect(page.get_by_role("heading", name="Northstar Labs", exact=True).last).to_be_visible()
                expect(page.get_by_text("Synthetic demo.", exact=True)).to_be_visible()
                page.screenshot(path=str(artifacts / "desktop.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    "Desktop horizontal overflow"
                )
                page.get_by_role("button", name=re.compile("View evidence for")).first.click()
                expect(page.get_by_role("complementary", name="Source evidence")).to_be_visible()
                expect(page.locator("blockquote")).to_contain_text("Terraform")
                page.screenshot(path=str(artifacts / "evidence.png"), full_page=True)
                page.keyboard.press("Escape")
                expect(page.get_by_role("complementary", name="Source evidence")).to_have_count(0)
                # A closed or superseded drawer must ignore late network results.
                page.evaluate("""() => {
                  window.__savedFetch = window.fetch;
                  window.fetch = async (input, init) => {
                    if (typeof input === 'string' && input.endsWith('/demo-source-0-workflow'))
                      await new Promise(resolve => setTimeout(resolve, 400));
                    return window.__savedFetch(input, init);
                  };
                }""")
                page.get_by_role("button", name=re.compile("View evidence for")).first.click()
                page.keyboard.press("Escape")
                page.wait_for_timeout(600)
                expect(page.get_by_role("complementary", name="Source evidence")).to_have_count(0)
                page.get_by_role("button", name="Source 1", exact=True).click()
                page.get_by_role("button", name="Source 2", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Northstar Labs · team update", exact=True)
                ).to_be_visible()
                page.wait_for_timeout(600)
                expect(
                    page.get_by_role("heading", name="Northstar Labs · team update", exact=True)
                ).to_be_visible()
                page.keyboard.press("Escape")
                page.evaluate("window.fetch = window.__savedFetch")
                page.get_by_role("button", name=re.compile("Aster Software")).click()
                expect(page.get_by_text("No timing signal found.", exact=True)).to_be_visible()
                page.get_by_role("combobox", name="Account status", exact=True).select_option(
                    "relevant_conversation"
                )
                page.get_by_label("Conversation or review notes", exact=True).fill(
                    "Synthetic check: confirmed a relevant workflow."
                )
                page.get_by_role("button", name="Save outcome", exact=True).click()
                expect(page.get_by_text("Outcome saved.", exact=True)).to_be_visible()
                page.get_by_role("tab", name="Ask about this account").click()
                composer_contrast = page.locator(".chat-composer span").evaluate(r"""element => {
                  const values = getComputedStyle(element).color.match(/[\d.]+/g).slice(0, 3).map(Number);
                  const linear = values.map(value => {
                    const channel = value / 255;
                    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
                  });
                  const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
                  return 1.05 / (luminance + 0.05);
                }""")
                assert composer_contrast >= 4.5, f"Composer contrast is {composer_contrast:.2f}:1"
                page.get_by_label("Question about this account").fill("What should I confirm?")
                page.get_by_role("button", name="Ask", exact=True).click()
                expect(page.locator(".chat-answer")).to_contain_text("synthetic demonstration")
                page.get_by_role("button", name="Inputs & assets", exact=True).click()
                page.get_by_role("button", name="Paste notes", exact=True).click()
                page.get_by_label("Title", exact=True).fill("Browser check notes")
                page.get_by_label(re.compile("Company domain")).fill("customer.example")
                page.get_by_label("Extracted content", exact=True).fill(
                    "Synthetic customer reports manual ownership checks."
                )
                page.get_by_role("button", name="Save input", exact=True).click()
                expect(page.get_by_role("button", name=re.compile("Browser check notes"))).to_have_count(2)
                assert len(app.state.store.all("source")) == 7
                page.get_by_role("button", name="Customer profile", exact=True).click()
                profile = app.state.store.get("run", "demo-research")["profile"]
                for index, key in enumerate(
                    ["offering", "company_type", "technology", "buyer_role", "problem", "buying_trigger"]
                ):
                    page.locator(".editor-form textarea").nth(index).fill(profile[key])
                page.locator(".editor-form textarea").nth(6).fill("Consultancies")
                page.get_by_role("button", name="Save customer profile", exact=True).click()
                expect(
                    page.get_by_text("Customer profile saved. Future runs will use these criteria.")
                ).to_be_visible()
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.get_by_role("heading", name="Research connections", exact=True)).to_be_visible()
                page.get_by_label("openrouter API key", exact=True).fill("synthetic-not-a-real-key")
                page.get_by_role("button", name="Save key", exact=True).first.click()
                expect(page.get_by_text("Key saved in Keychain", exact=True)).to_be_visible()
                assert "synthetic-not-a-real-key" not in page.content()
                page.get_by_text("Delete research data", exact=True).first.click()
                page.get_by_label("Type DELETE to confirm", exact=True).fill("DELETE")
                page.get_by_role("button", name="Delete research data", exact=True).click()
                expect(page.get_by_text("Research data deleted.", exact=True)).to_be_visible()
                assert app.state.store.all("source") == []
                assert app.state.store.get("config", "profile") is not None
                page.get_by_role("button", name="Explore a demo", exact=True).click()
                expect(page.get_by_role("heading", name="Northstar Labs", exact=True).last).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    "Mobile horizontal overflow"
                )
                page.get_by_role("button", name=re.compile("View evidence for")).first.click()
                expect(page.get_by_role("button", name="Close evidence", exact=True)).to_be_visible()
                for key in ["Tab"] * 6 + ["Shift+Tab"] * 6:
                    page.keyboard.press(key)
                    assert page.locator(":focus").evaluate(
                        "element => !!element.closest('.evidence-drawer')"
                    ), "Focus escaped the mobile drawer"
                assert page.locator(".main-shell").get_attribute("inert") is not None
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)
                assert page.locator(":focus").evaluate("element => element.classList.contains('citation')"), (
                    "Focus did not return to the citation"
                )
                expect(page.get_by_role("dialog", name="Source evidence")).to_have_count(0)
                assert not errors, errors
                browser.close()
            print(
                "Browser checks passed: onboarding, demo, citations, missing timing, outcomes, chat, input import, profile, credentials, deletion, desktop/mobile overflow, mobile focus containment and evidence-request races."
            )
            print(f"Screenshots: {artifacts}")
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == "__main__":
    main()
