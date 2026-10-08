# job-alert-bot

Small Python script to quickly find remote jobs so you spend less time manually scouting job sites.

## Run

```bash
python job_alert_bot.py --keyword python --keyword backend --location "Worldwide" --limit 5
```

## Options

- `--keyword`: repeatable keyword filter
- `--location`: match candidate location text (example: `US`, `Worldwide`)
- `--limit`: number of results to print (default `10`)
- `--api-url`: override source API endpoint
- `--timeout`: HTTP timeout in seconds
