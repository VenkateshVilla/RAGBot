# Knowledge Bot

A local, browser-based knowledge search app. Search for a keyword or a natural-language alias and view the matching answer from the documents in `documents/`. A phone can mirror the current search and answer while connected to the same network as the computer running the app.

## Requirements

- Python 3.9 or later
- A network connection for the initial Python package installation

## Run the app

### Windows

Run `run.bat`. It creates a virtual environment if needed, installs the dependencies, and starts the app.

To run it manually:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

### macOS or Linux

Run `bash run.sh`, or use:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

Open the **Local URL** printed by Streamlit to search on the computer. To mirror the current search on a phone, connect it to the same network and open the **Network URL** with `/?mode=display` appended, for example:

```text
http://192.168.1.25:8501/?mode=display
```

Keep the app running while using either view. Network access may require allowing Python or Streamlit through the computer's firewall.

## Add or edit knowledge

Put `.docx`, `.md`, or `.txt` files in the relevant folder under `documents/`:

| Keyword prefix | Folder |
| --- | --- |
| `play` | `documents/Playwright/` |
| `sel` | `documents/Selenium/` |
| `api` | `documents/API/` |

Wrap each answer in matching keyword tags. For example:

```text
<playfixture>
The answer for the playfixture keyword.
</playfixture>
```

Keywords are case-insensitive. If a keyword appears in more than one document in a folder, the first match in the sorted file order is used. The search index refreshes when knowledge files change.

To add natural-language search phrases, edit `intents.json`. Map each keyword to a list of aliases:

```json
{
  "playfixture": ["playwright fixtures", "test fixtures in playwright"]
}
```

Aliases are case-insensitive and can match within a longer query. Each alias should point to a keyword defined in the corresponding knowledge folder.

To add another knowledge area, add its prefix-to-folder mapping to `ROUTES` in `search_bot.py` and create the matching folder in `documents/`.
