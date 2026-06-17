# Hunch Portfolio — GitHub Pages Edition

A self-hosted, self-refreshing paper-portfolio dashboard. Lives on GitHub Pages,
fetches fresh prices on a GitHub Actions schedule, commits weekly snapshots into
the repo so the chart accrues history.

## What you get

- A bookmarkable URL: `https://<your-username>.github.io/<repo-name>/`
- Prices refreshed automatically every weekday at 5 PM ET (US market close)
- Manual "Run workflow" trigger from the Actions tab whenever you want
- Hunches edited via GitHub's built-in web editor (one click from the dashboard)
- Snapshot history accruing in `data/portfolio_state.json` — chart fills in over time

## One-time setup (~5 minutes)

### 1. Create a new GitHub repository

- Go to github.com → New repository
- Name it `hunch-portfolio` (or anything you like)
- Public or private — both work for personal use
  - **Private + GitHub Free:** Pages won't work. Either make it public, or upgrade to Pro
  - **Private + GitHub Pro/Team:** Pages works fine
- Don't initialize with a README — we have one

### 2. Upload these files

Either drag-drop in the GitHub web UI (Add file → Upload files), or from terminal:

```bash
cd path/to/github_deploy
git init
git add .
git commit -m "Initial dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/hunch-portfolio.git
git push -u origin main
```

### 3. Enable GitHub Pages

- Repo → Settings → Pages
- Source: **Deploy from a branch**
- Branch: **main**, folder: **/ (root)**
- Save. After ~1 minute the URL appears at the top of the Pages settings page.

### 4. Enable Actions write permissions

The refresh workflow needs to push commits back to the repo:

- Repo → Settings → Actions → General
- Workflow permissions: **Read and write permissions**
- Save

### 5. Trigger the first refresh

- Repo → Actions tab
- "Refresh portfolio prices" workflow → **Run workflow**
- Wait ~30 seconds. It will fetch prices and commit the first snapshot.
- Pages auto-rebuilds in another minute. Refresh the dashboard URL.

That's it. From here on, the Action runs every weekday at 21:00 UTC (5 PM ET).

## Editing hunches

The dashboard has an **Edit hunches** button in the header. It deep-links to
`data/portfolio_state.json` in GitHub's web editor. Find the `"hunch"` field
for the position you want to update, edit, click Commit changes. Pages
rebuilds in ~1 minute and the new hunch shows up.

If you'd rather edit locally and push, just edit the JSON in any editor and
push the commit.

## Changing positions

To add, remove, or resize positions, edit `data/portfolio_state.json` directly
(same flow as hunches). The shape of each position is:

```json
{
  "ticker": "FRVO",
  "name": "Fervo Energy (Nasdaq)",
  "bucket": "Energy",
  "shares": 58.98,
  "entryPrice": 33.91,
  "entryDate": "2026-06-17",
  "spyEntryPrice": 750.33,
  "hunch": "Your one-line thesis here.",
  "active": true
}
```

Tickers map to Yahoo Finance symbols (Toronto = `.TO`, London = `.L`, etc.).
Non-Yahoo tickers (KCB Nairobi) are handled specially — see
`scripts/refresh.py`.

## Manually triggering a refresh

- Repo → Actions → "Refresh portfolio prices" → **Run workflow** → Run
- Or click the **Refresh on GitHub** button in the dashboard header

## How prices are fetched

- `scripts/refresh.py` runs in the GitHub Action environment (Python 3.11)
- Pulls quote metadata from `query1.finance.yahoo.com/v8/finance/chart/{symbol}`
- Converts non-USD quotes (IVN.TO → CAD → USD) using Yahoo's FX symbols
- KCB is scraped from `afx.kwayisi.org/nse/kcb.html`
- Falls back to last-known price on any per-ticker failure (won't break the run)

## Files

```
.
├── index.html                       # Dashboard (read by GitHub Pages)
├── data/
│   └── portfolio_state.json        # Source of truth — positions + snapshots
├── scripts/
│   └── refresh.py                  # Fetches prices, appends snapshot
└── .github/workflows/
    └── refresh.yml                 # Schedule + manual trigger
```

## Troubleshooting

- **Action fails with "permission denied to push":** Fix step 4 above.
- **Dashboard says "Never refreshed" forever:** The Action hasn't run yet, or
  failed. Check the Actions tab for error details.
- **KCB price stuck at last-known:** afx.kwayisi.org's HTML may have changed.
  Edit `fetch_kcb_kes()` in `scripts/refresh.py` to point at a different source.
- **Custom domain:** Set `CONFIG.owner` and `CONFIG.repo` at the top of the
  `<script>` block in `index.html` — the auto-detection only works for
  `*.github.io` URLs.
