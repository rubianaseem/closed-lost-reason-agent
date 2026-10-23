# Closed-Lost Reason Agent

**Find out why you really lost each deal, not just what the rep picked in the dropdown.**

> Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

---

## The pain point

Every quarter someone asks "why are we losing?" and RevOps pulls the Closed Lost Reason report. Half of it says *Price*, a chunk says *Other*, and the notes underneath tell a different story. Buyer interviews are the gold standard, but most teams can only afford a handful, so this gets the most out of the data you already have.

- *"Reps fill out the fields when they close a deal, but even with guardrails the data is often mislabeled or missing context or sometimes there's nothing there at all."* ([r/SalesOperations: (B2B SaaS) Struggling with Poor Win-Loss data](https://www.reddit.com/r/SalesOperations/comments/1ozwxan/b2b_saas_struggling_with_poor_winloss_data_how/))
- *"CRM fields are rarely accurate - sales reps default to 'price' or 'features,' but that's not the real reason 8 times out of 10."* ([r/ProductMarketing: Struggling with win-loss analysis](https://www.reddit.com/r/ProductMarketing/comments/1ni78ep/struggling_with_winloss_analysis_how_do_you/))

---

## What it does

- **Audited loss reason for every deal:** reads rep notes, competitor, stage, contact count and last activity, then picks one of 8 actionable buckets
- **Picklist vs notes check:** flags deals where the dropdown contradicts the rep's own notes, e.g. *Price* picked but the notes say *went with Gong*
- **Evidence and confidence:** every call shows the phrase or signal it's based on, and says "unknown, ask the rep" when the notes don't support one
- **Data-quality flags:** missing notes, competitor not named, single-threaded deals, and deals that went dark weeks before close
- **Re-engage queue:** a dated play per deal, plus "fix the field" recommendations for your Closed Lost stage
- **Works with no API key:** Claude only classifies and summarises if you set a key

---

## Where each step runs

1. **GitHub** holds the code. Clone it or click **Code → Download ZIP**.
2. **Terminal** is where you run it on your closed-lost export: `python agent.py --input your_export.csv`.
3. **Claude is optional.** With an Anthropic key it classifies each deal and writes the summary, which handles messy notes better. It all stays in the terminal.
4. **You, then your CRM.** Check the mismatches, take the report to pipeline review, and import the audited reasons yourself if you want them in the CRM.

**The agent never writes to your CRM.**

---

## Quick start

```bash
git clone https://github.com/rubianaseem/closed-lost-reason-agent.git
cd closed-lost-reason-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py            # runs on the sample data, no API key needed
```

Use your own export with `python agent.py --input ~/Downloads/closed_lost_deals_q3.csv --output out/q3`.

---

## Example output

On `sample_closed_lost_deals.csv` (8 fictional deals), with no API key:

```text
[MISMATCH] Northwind Analytics - Revenue Platform  (£48,000, lost at Negotiation, owner Jordan Patel)
    rep picked : Price
    audited    : Lost to competitor  [high]  evidence: Gong, went with
    flags      : picklist_mismatch; competitor_not_named
    re-engage  : 2027-07-09  Their renewal window opens ~10-12 months after signing. Re-engage with a displacement angle vs Gong.

SUMMARY
8 closed-lost deals worth £325,000 were audited. The biggest audited loss reason by value is 'Product or security gap' (1 deal, £90,000, 28% of lost value). Rep-picked reasons were vague on 2 deals and contradicted the rep's own notes on 3. £127,000 (39%) was lost for reasons sales could have influenced (went dark, champion loss, value not proven).
```

---

## More

- [SETUP.md](SETUP.md): Claude, exporting your real closed-lost deals, putting the audited reason back in your CRM, extending it, troubleshooting
- [docs/DETAILS.md](docs/DETAILS.md): all the pain-point quotes, full feature list and example output, cost, stack swap table, customising, how this runs today vs production, and what's in the repo
