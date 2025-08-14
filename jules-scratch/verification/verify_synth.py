import os
from playwright.sync_api import sync_playwright, Page, expect

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Get the absolute path to the index.html file
        file_path = os.path.abspath('index.html')

        # Go to the local HTML file
        page.goto(f'file://{file_path}')

        # Wait for the page to load and the title to be correct
        expect(page).to_have_title("Macintosh JS-88 Synthesizer")

        # Check for the MIDI controls section
        midi_controls = page.locator("#midi-controls")
        expect(midi_controls).to_be_visible()
        expect(midi_controls.get_by_role("heading", name="MIDI Input")).to_be_visible()
        expect(page.locator("#midi-inputs")).to_be_visible()

        # Click the "Add Detune Oscillator" button
        page.get_by_role("button", name="Add Detune Oscillator").click()

        # Take a final screenshot
        page.screenshot(path="jules-scratch/verification/verification_midi.png")

        browser.close()

if __name__ == "__main__":
    run_verification()
