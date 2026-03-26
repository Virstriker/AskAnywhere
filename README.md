# AskAnywhere (Windows MVP)

AskAnywhere is a desktop helper that watches text selection across apps, opens a popup near the cursor, and lets you chat with AI in-place.

## What this MVP does

- Captures selected text automatically on text selection (left mouse release).
- Triggers `Ctrl+C` internally to read selected text.
- Press `Ctrl+Shift+Z` to toggle listening on/off globally.
- Shows a floating chat popup near your cursor.
- Lets you drag the popup around freely.
- Hides the popup when focus moves away (click outside the popup).
- Sends selected text + your follow-up input to Gemini and shows responses in the same popup.

## Model note

This app supports any Gemini model name via `GEMINI_MODEL`.

- If `gemini-3-flash` works in your account, set that value.
- Default in this project is `gemini-2.5-flash` for broader availability.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set your key:

   ```env
   GEMINI_API_KEY=your_real_key
   GEMINI_MODEL=gemini-2.5-flash
   ```

4. Run:

   ```powershell
   python main.py
   ```

## Build executable (.exe)

1. Install PyInstaller:

   ```powershell
   pip install pyinstaller
   ```

2. Build:

   ```powershell
   pyinstaller --noconfirm --clean --onefile --name AskAnywhere main.py
   ```

3. Copy config template and fill it:

   - Copy `askanywhere.config.json.example` to `dist/askanywhere.config.json`.
   - Set your real `gemini_api_key` and preferred `gemini_model`.

4. Launch by double-clicking:

   - `dist/AskAnywhere.exe`

Note: In `.exe` mode, the app reads config from `askanywhere.config.json` in the same directory as the executable.

## Notes and limitations

- Automatic selection capture is best-effort and depends on how each app handles `Ctrl+C`.
- Some protected apps or admin-elevated windows may block global hooks unless this app is run with matching privileges.
- Because capture uses `Ctrl+C`, your clipboard content may change.
