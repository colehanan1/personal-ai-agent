# Milton

Local morning-briefing helper that pulls weather + recent arXiv papers,
stores a JSON brief, and renders a short text summary.

## Requirements
- Python 3.10+
- Dependencies: `requests`, `python-dotenv`, `feedparser`

## Setup
1) Create a `.env` in the repo root:
```
WEATHER_API_KEY=your_openweather_key
WEATHER_LOCATION=St. Louis,US
```

2) Install dependencies:
```
python3 -m pip install requests python-dotenv feedparser
```

## Usage
- Generate the JSON brief:
```
python3 morning_briefing.py
```

- Render a text summary:
```
python3 render_briefing.py
```

Output is written to `inbox/morning/brief_latest.json` and is ignored by git.

## Smoke checks
```
python3 test_weather.py
python3 test_arxiv.py
```
