# AIBYPYTHON Content Studio

A small content-creation app for turning a topic into ideas and an editable
social-media draft. Its creator profile can be changed for other domains.

The app runs without an API key using a local demo generator. Configure an
OpenAI-compatible chat endpoint for model-generated ideas and drafts.

## Files

| File | Purpose |
|------|---------|
| `content_agent.py` | Idea generation, ranking, and draft generation |
| `streamlit_app.py` | Web app for ideas, editing, and saved drafts |
| `profile.json` | Creator identity, voice, audience, and goals |
| `library.json` | Previously published posts used for recommendations |
| `trends.json` | Starter topics used by the command-line prototype |
| `drafts.json` | Created locally when you save a draft; excluded from Git |
| `requirements.txt` | Python app dependency |

## Run the web app

Install dependencies and start Streamlit from this folder:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

The app opens in your browser. Enter a topic, choose a format, select an idea,
create and edit its draft, then save it locally or download it. Edit your
creator details in the sidebar. Saved drafts are stored in `drafts.json` on
this computer; this prototype has no login or cloud storage.

## Enable model-generated content

Set environment variables in PowerShell, then start the app in the same
terminal:

```powershell
$env:CONTENT_AGENT_API_KEY = "your-key"
$env:CONTENT_AGENT_API_URL = "https://api.openai.com/v1/chat/completions"
$env:CONTENT_AGENT_MODEL = "gpt-4o-mini"
python -m streamlit run streamlit_app.py
```

Use the documented endpoint and model for your OpenAI-compatible provider.
Keep API keys out of source files and never commit them. If model generation
fails, the app shows an error rather than silently presenting the local demo
as model output.

## Command-line prototype

The original command-line interface remains available:

```powershell
python content_agent.py
python content_agent.py --n 5
```

## Prototype limitations

- The no-key generator is a basic template demo, not a language model.
- Saved drafts are local JSON, intended for one user and one running app.
- Review technical claims and edit every draft before publishing.
- Instagram publishing, analytics, and live trend research are not included.
