# Setup guide

This walks through everything in order: install, a first run on the sample data, adding Claude, exporting your real closed-lost deals from HubSpot or Salesforce, and (optionally) putting the audited reason back in your CRM.

You need **Python 3.9 or newer**. Check with `python3 --version` in Terminal.

---

## 1. Get the code and create a virtual environment

Run these in **Terminal** (Mac Terminal, or the terminal panel in Cursor):

```bash
git clone https://github.com/rubianaseem/closed-lost-reason-agent.git
cd closed-lost-reason-agent

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The virtual environment (`.venv`) keeps this project's packages separate from everything else on your laptop. Run `source .venv/bin/activate` again whenever you open a new terminal.

## 2. Run it on the sample data

```bash
python agent.py
```

No API key needed. You'll see one block per deal in the terminal, then a summary, and three files in `out/`:

| File | What it's for |
|---|---|
| `out/closed_lost_audit.csv` | One row per deal: rep-picked reason, audited reason, confidence, evidence, flags, re-engage date and play |
| `out/closed_lost_report.md` | The readout for pipeline review: summary, picked vs audited, lost value by reason, data-quality issues, field fixes, re-engage queue |
| `out/import_audited_reasons.csv` | Optional CRM import file (high and medium confidence rows only) |

## 3. Optional: add Claude

```bash
cp .env.example .env
```

Open `.env` and paste your key after `ANTHROPIC_API_KEY=` (get one at https://console.anthropic.com). The default model is `claude-sonnet-5-5`; change `ANTHROPIC_MODEL` if you want another one.

Run `python agent.py` again. The header now says `Claude (claude-sonnet-5-5)` and the `classified_by` column says `claude`. If a call fails (bad key, no credit, network), that deal falls back to the rules. After two failures in a row the rest of the run uses the rules too. Use `--no-llm` to skip Claude even when a key is set.

`.env` is in `.gitignore`, so your key is never committed.

Other settings in `.env`:

- `WENT_DARK_DAYS` (default 30): quiet days before the close date that count as "went dark"
- `KNOWN_COMPETITORS`: competitor names to spot in free-text notes

## 4. Export your real closed-lost deals

The agent needs at least an ID column and a loss reason column. Everything else makes it smarter. Column names are matched automatically (see `ALIASES` in `agent.py`).

| Agent field | HubSpot column | Salesforce column |
|---|---|---|
| `deal_id` (required) | Record ID | Opportunity ID |
| `lost_reason` (required) | Closed Lost Reason | Your loss reason field (Salesforce has no standard one; often `Loss_Reason__c`) |
| `lost_reason_notes` | Your notes property, if you have one | Your loss detail field, if you have one |
| `deal_name`, `company`, `owner` | Deal Name, Associated Company, Deal owner | Opportunity Name, Account Name, Opportunity Owner |
| `amount` | Amount | Amount |
| `created_date`, `close_date` | Create Date, Close Date | Created Date, Close Date |
| `last_activity_date` | Last Activity Date | Last Activity |
| `contacts_engaged` | Number of Associated Contacts | Count of contact roles (needs the "Opportunities with Contact Roles" report type) |
| `competitor` | Your competitor property, if you have one | Your competitor field, if you have one |
| `stage_at_loss` | Not stored by default; add a column by hand or from your own property | From an Opportunity History report (the stage before Closed Lost) |

### HubSpot

1. Go to **CRM → Deals** and switch to the table view.
2. Filter: **Deal stage** is **Closed Lost** (one filter per pipeline if you have several), and **Close date** is in the period you care about, e.g. last quarter.
3. Click **Edit columns** and add the columns in the table above.
4. Click **Export**, choose **CSV**, and include only the columns in the view. HubSpot emails you a download link when the file is ready.
5. Run: `python agent.py --input ~/Downloads/<your-export>.csv --output out/hubspot`

HubSpot's default **Closed Lost Reason** property is free text, so it often holds the rep's actual words. The agent reads free text in that field as notes, so you get a useful audit even without a separate notes property.

### Salesforce

1. Go to **Reports → New Report → Opportunities**.
2. Filters: **Stage** equals **Closed Lost**, **Close Date** in your period, and **Show Me** set to *All opportunities*.
3. Add the columns in the table above as report columns.
4. Click the arrow next to **Edit → Export → Details Only**, format **Comma Delimited .csv**.
5. Run: `python agent.py --input ~/Downloads/<your-report>.csv --output out/salesforce`

If your column names differ (custom fields, other languages), add them to `ALIASES` at the top of `agent.py`.

## 5. Optional: put the audited reason back in your CRM

The agent never does this for you. Review `out/closed_lost_audit.csv` first and delete any rows you disagree with in `out/import_audited_reasons.csv`.

### HubSpot

1. **Settings → Properties → Deal properties → Create property:**
   - `Lost Reason (Audited)`: dropdown select, options matching the audited reasons in `CATEGORIES`
   - `Lost Reason Confidence`: dropdown select (high, medium)
   - `Re-engage Date`: date picker
2. **CRM → Deals → Import → Start an import → File from computer → One file → One object → Deals.**
3. Choose to update existing records, matched on **Record ID**, so no new deals get created.
4. Map the columns to the new properties and finish the import.
5. Build a deals view or task workflow on `Re-engage Date` so reps see the queue.

### Salesforce

1. Create custom Opportunity fields with the same three names (picklist, picklist, date).
2. Salesforce's Data Import Wizard doesn't support Opportunities, so use **Data Loader** (or dataloader.io): choose **Update**, object **Opportunity**, map `Record ID` to **Opportunity ID**, and map the other columns to the new fields.
3. Add the new fields to your closed-lost report and to a list view for the re-engage queue.

## 6. Extend it with an AI coding tool

The code is one file with clear sections, so it's easy to extend with an AI coding assistant. Open the folder in your tool and try prompts like these:

- **Cursor:** open the folder, press Cmd+L and ask: *"Add a `--since` argument that only audits deals closed after a given date."*
- **Claude Code:** run `claude` in the project folder and ask: *"Read call summaries from a `calls.csv` keyed on deal_id and pass them to `classify_llm` as extra context."*
- **Codex CLI:** run `codex` in the folder and ask: *"Post the summary section of closed_lost_report.md to a Slack webhook URL from `.env`."*
- **Grok:** paste `agent.py` and ask it to add sub-reasons under the competitor bucket (feature gap, price, existing relationship, integration).

Ask the tool to run `python agent.py` afterwards and check that the sample still produces the same 8 audited rows.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `Input is missing required column(s): deal_id` | Your ID column has a name the agent doesn't know. Add it to `ALIASES["deal_id"]`, or rename the column to `Record ID` / `Opportunity ID`. |
| Everything comes out as "Unknown" | Your export probably has no notes or free-text reason. Add a notes column, a Last Activity Date column, or your competitor field. |
| Amounts show as £0 | The amount column wasn't found or uses an odd format. Check the header against `ALIASES["amount"]`. |
| Dates are ignored | Supported formats are `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY` (with or without a time). Ambiguous dates are read day-first. |
| `Claude call failed (AuthenticationError)` | The key in `.env` is wrong or has no credit. The run still finishes using the rules. |
| `Claude call failed (NotFoundError)` | The model name in `ANTHROPIC_MODEL` isn't available on your account. Pick one from Anthropic's models page. |
| `ModuleNotFoundError: anthropic` | Activate the venv (`source .venv/bin/activate`) and run `pip install -r requirements.txt`. Without a key the agent doesn't need it at all. |
| Weird characters in names | Export as UTF-8 CSV. The agent already handles the Excel byte-order mark. |
