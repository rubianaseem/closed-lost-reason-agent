# 🔍 Closed-Lost Reason Agent

**Find out why you really lost each deal, not just what the rep picked in the dropdown.**

Every quarter someone asks "why are we losing?" and RevOps pulls the Closed Lost Reason report. Half of it says *Price*, a chunk says *Other*, and the notes underneath tell a different story: "went with Gong", "our champion left", "stopped replying after the pricing call". That report then goes into a board deck, a pricing debate or a roadmap discussion.

This agent reads your closed-lost export from HubSpot or Salesforce, compares the reason the rep picked with what the notes and activity data actually say, and gives you an audited reason for every deal. It also flags the data gaps behind bad loss data and builds a dated re-engage queue, so closed-lost becomes a list you can work.

> Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

---

## 🗺 Where each step runs

If you can create a repo but aren't sure where you actually *run* this, here's the whole flow in order:

1. **GitHub** is where the code lives. Copy it to your laptop with `git clone https://github.com/rubianaseem/closed-lost-reason-agent.git`, or click **Code → Download ZIP** and unzip it.
2. **Terminal** (Mac Terminal, or the terminal inside Cursor) is where you run the script on your closed-lost CSV export. Set it up once, then run `python agent.py --input your_export.csv` (see [Quick start](#-quick-start)).
3. **Claude is optional.** With no API key the agent uses its built-in rules. If you add an Anthropic API key to `.env`, it asks Claude to classify each deal and write the summary, which handles messy notes better. It still runs in the terminal. You don't open the Claude app or paste anything into a chat.
4. **You, then your CRM.** Open `out/closed_lost_report.md` and `out/closed_lost_audit.csv`, check the mismatches, and take the report to pipeline review. If you want the audited reason in your CRM, import `out/import_audited_reasons.csv` into HubSpot or Salesforce yourself (steps in [SETUP.md](SETUP.md#5-optional-put-the-audited-reason-back-in-your-crm)).

**The agent never writes to your CRM.** It only reads the CSV you give it and creates files on your computer.

---

## ✨ Features

- **Audited loss reason for every deal:** reads rep notes, the competitor field, stage, contact count and last activity date, then picks one of 8 actionable buckets (competitor, champion left, no decision, product gap, budget, timing, went dark, price/value)
- **Picklist vs notes check:** flags deals where the dropdown contradicts the rep's own notes, e.g. *Price* picked but the notes say *went with Gong*
- **Fixes "Other":** gives vague or blank reasons an audited reason when the notes support one, and says "unknown, ask the rep" when they don't
- **Evidence and confidence:** every call shows the phrase or signal it's based on, plus high / medium / low confidence
- **Data-quality flags:** missing notes, notes too short, competitor not named, single-threaded deals, and deals that went dark weeks before anyone closed them
- **Controllable vs not:** splits lost value into sales-controllable, partly controllable, product/roadmap and uncontrollable
- **Re-engage queue:** a dated play per deal (competitor renewal window ~10 months out, champion change now, budget cycle in ~4 months, and so on)
- **"Fix the field" recommendations:** concrete changes to your Closed Lost stage requirements, based on what this export shows
- **Reads real exports:** recognises HubSpot and Salesforce column names (`Record ID`, `Opportunity ID`, `Closed Lost Reason`, `Deal owner`, `Account Name`…) and HubSpot's free-text reason field
- **Three outputs:** `closed_lost_audit.csv`, `closed_lost_report.md`, `import_audited_reasons.csv`
- **Works with no API key.** Claude is an upgrade, not a requirement, and any API error falls back to the rules

---

## 🧠 The pain point

RevOps people keep saying the same thing: the loss reason in the CRM is the least trustworthy field you report on.

- *"Reps fill out the fields when they close a deal, but even with guardrails the data is often mislabeled or missing context or sometimes there's nothing there at all."* ([r/SalesOperations: (B2B SaaS) Struggling with Poor Win-Loss data](https://www.reddit.com/r/SalesOperations/comments/1ozwxan/b2b_saas_struggling_with_poor_winloss_data_how/))
- *"Rep-filled CRM fields for win-loss are basically useless, ask anyone who's tried to run a report off them."* (same thread)
- *"CRM fields are rarely accurate - sales reps default to 'price' or 'features,' but that's not the real reason 8 times out of 10."* ([r/ProductMarketing: Struggling with win-loss analysis](https://www.reddit.com/r/ProductMarketing/comments/1ni78ep/struggling_with_winloss_analysis_how_do_you/))
- *"If you're relying on sales to fill out fields in CRM you're going to have a bad time."* (same thread)

Those threads also say the gold standard is talking to the buyers who said no, and I agree. Interviews cost time or money, though (the original poster was quoted 500+ dollars per interview by third-party firms), so most teams can only do a handful. This agent doesn't replace that. It gets the most out of the data you already have, shows you where the dropdown is lying, and tells you which losses deserve an interview.

---

## 🚀 Quick start

```bash
git clone https://github.com/rubianaseem/closed-lost-reason-agent.git
cd closed-lost-reason-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py            # runs on the sample data, no API key needed
```

Use your own export:

```bash
python agent.py --input ~/Downloads/closed_lost_deals_q3.csv --output out/q3
```

Optional: `cp .env.example .env` and add your `ANTHROPIC_API_KEY` so Claude classifies the deals and writes the summary. Use `--no-llm` to force the rules even when a key is set. Full walkthrough in [SETUP.md](SETUP.md).

---

## 📟 Example output (sample data, no API key)

This is the real output of `python agent.py` on `sample_closed_lost_deals.csv` (8 fictional deals), run on 18 Oct 2026. Re-engage dates that would fall in the past show as "Due now" with the run date.

```text
============================================================================
 CLOSED-LOST REASON AGENT  |  sample_closed_lost_deals.csv  |  8 deals  |  built-in rules (no API key)
============================================================================

[MISMATCH] Northwind Analytics - Revenue Platform  (£48,000, lost at Negotiation, owner Jordan Patel)
    rep picked : Price
    audited    : Lost to competitor  [high]  evidence: Gong, went with
    flags      : picklist_mismatch; competitor_not_named
    re-engage  : 2027-07-09  Their renewal window opens ~10-12 months after signing. Re-engage with a displacement angle vs Gong.

[VAGUE] Lumen SaaS - Team Plan  (£22,000, lost at Demo, owner Priya Shah)
    rep picked : Other
    audited    : Went dark (no response)  [low]  evidence: no activity for 67 days before close
    flags      : missing_notes; vague_picklist; single_threaded; went_dark_67d_before_close
    re-engage  : 2026-11-04  Try a different contact and channel. Don't re-send the same sequence.

[MISMATCH] Brightpath - Enterprise  (£65,000, lost at Evaluation, owner Jordan Patel)
    rep picked : Timing
    audited    : Champion left / single-threaded  [high]  evidence: champion, left the company, new vp
    flags      : picklist_mismatch; single_threaded; went_dark_34d_before_close
    re-engage  : 2026-10-18  Due now. Map the new decision-maker and send a short 'picking up where we left off' note. Multi-thread this time.

[OK] Fernway - Starter  (£18,000, lost at Discovery, owner Marcus Lee)
    rep picked : Budget
    audited    : Budget  [high]  evidence: budget, frozen, hiring freeze, fy27
    re-engage  : 2027-01-03  Check in before their next budget cycle with a one-page business case.

[OK] Kestrel Logistics - Enterprise  (£90,000, lost at Legal/Procurement, owner Marcus Lee)
    rep picked : Product fit
    audited    : Product or security gap  [high]  evidence: no sso, soc 2, security review
    re-engage  : 2027-03-28  Re-open when the gap ships. Log this deal against the roadmap item so product sees the revenue.

[VAGUE] Orbital Health - Growth  (£30,000, lost at Proposal, owner Priya Shah)
    rep picked : Other
    audited    : No decision / status quo  [high]  evidence: no decision, spreadsheets, keep doing
    flags      : vague_picklist
    re-engage  : 2026-11-17  Lead with cost of inaction and find a sponsor who owns the pain.

[OK] Halcyon Retail - Growth  (£12,000, lost at Negotiation, owner Jordan Patel)
    rep picked : Lost to competitor
    audited    : Lost to competitor  [medium]  evidence: Clari
    re-engage  : 2027-07-05  Their renewal window opens ~10-12 months after signing. Re-engage with a displacement angle vs Clari.

[MISMATCH] Quill & Co - Team Plan  (£40,000, lost at Demo, owner Priya Shah)
    rep picked : Price
    audited    : Went dark (no response)  [high]  evidence: stopped replying, no answer, 3 follow ups, no activity for 59 days before close
    flags      : picklist_mismatch; single_threaded; went_dark_59d_before_close
    re-engage  : 2026-11-14  Try a different contact and channel. Don't re-send the same sequence.

============================================================================
 SUMMARY
============================================================================
8 closed-lost deals worth £325,000 were audited. The biggest audited loss reason by value is 'Product or security gap' (1 deal, £90,000, 28% of lost value). Rep-picked reasons were vague on 2 deals and contradicted the rep's own notes on 3. £127,000 (39%) was lost for reasons sales could have influenced (went dark, champion loss, value not proven).

Lost value by audited reason:
  Product or security gap              1 deal     £90,000
  Champion left / single-threaded      1 deal     £65,000
  Went dark (no response)             2 deals     £62,000
  Lost to competitor                  2 deals     £60,000
  No decision / status quo             1 deal     £30,000
  Budget                               1 deal     £18,000

Fix the field:
  - 'Other' or blank was picked on 2 of 8 deals. Make a short note required when 'Other' is chosen, and add the buckets your notes keep pointing to.
  - 3 of 8 picklist values contradict the rep's own notes. Review these in pipeline review before they reach a board deck.
  - Competitor was not named on 1 competitive loss. Make Competitor required when the loss reason is a competitor.
  - 1 deal had no loss notes at all. Require a one-line note on the Closed Lost stage.
  - 3 lost deals had one contact or fewer. Worth a multi-threading check at the Evaluation stage.
  - 3 deals went quiet long before they were closed. Those were dead earlier than the pipeline said, so check your stale-deal rule.

============================================================================
 FILES (nothing was written to your CRM)
  audit   ./out/closed_lost_audit.csv
  import  ./out/import_audited_reasons.csv
  report  ./out/closed_lost_report.md
============================================================================
```

The same results land in `out/closed_lost_report.md` as tables you can paste into a pipeline review doc or Notion.

---

## 💷 Cost (estimate)

- **Without an API key:** free. It's plain Python running on your laptop.
- **With `ANTHROPIC_API_KEY`:** one short Claude call per deal plus one for the summary. My rough estimate, based on [Anthropic's list pricing](https://platform.claude.com/docs/en/about-claude/pricing) for Claude Sonnet 5.5 ($2 per million input tokens, $10 per million output tokens) and about 700 input and 150 output tokens per deal, is a fraction of a cent per deal: a few US cents for the 8-deal sample, and somewhere around $1-2 for 500 deals. I haven't measured this on a large real export, so treat it as a ballpark. `--max-llm-deals` (default 200) caps how many deals go to Claude in one run; the rest use the rules.

---

## 🔁 Stack swap table

| Layer | In this repo | Swap for |
|---|---|---|
| Deal source | `sample_closed_lost_deals.csv` | HubSpot deals export or API, Salesforce Opportunity report or SOQL, Pipedrive / Attio / Close export |
| Loss context | Rep notes + reason field | Gong / Chorus / Fathom call summaries, email threads, support tickets, buyer survey answers |
| Classification | Keyword rules → Claude | OpenAI, Grok, Gemini or a local model; swap the one function `classify_llm` |
| Taxonomy | 8 buckets in `CATEGORIES` | Your own loss taxonomy, with sub-reasons or "controllable" scoring |
| Output | Local CSV + Markdown | HubSpot custom property via import, Salesforce Data Loader update, a Slack digest, a Notion page |
| Orchestration | You run it | n8n, Zapier or Make on a weekly or end-of-quarter schedule |

---

## 🛠 Customise it for your stack

Everything you'll want to tune is at the top of `agent.py`:

- **`ALIASES`:** add your exact export headers, e.g. a custom `Loss_Reason__c` or `Closed Lost Notes` property
- **`PICKLIST_MAP`:** map your dropdown values onto the audited buckets
- **`SIGNALS`:** the phrases your reps actually write ("procurement stalled", "went with incumbent", "POC failed")
- **`KNOWN_COMPETITORS`** (in `.env`): the competitors to spot in free-text notes
- **`REENGAGE`:** the timing and play per bucket, e.g. match the competitor window to typical contract length in your market
- **`WENT_DARK_DAYS`** (in `.env`): how many quiet days before close count as "went dark"
- **`LATE_STAGES`:** your stage names, so late-stage losses are marked correctly
- **Currency:** the report uses £. Change `money()` if you report in another currency.

---

## 🧭 How this runs today (and what production would add)

I want to be straight about what this is: a working **audit tool you run on an export**, not a hands-off system.

**Today:**
- **No auto-trigger.** You export the deals and run it by hand, e.g. before a QBR or monthly pipeline review.
- **Prints to the console** and writes three local files. **It never writes to your CRM.** Importing the audited reason back is optional and manual.
- **Only as good as the notes.** If a deal has no notes and no activity signal, it says "unknown" instead of guessing. The rules are keyword-based, so unusual wording can be missed. Claude handles that better but can still be wrong, which is why every call shows its evidence.
- **No memory.** It doesn't learn from the corrections you make in the audit file.
- It doesn't talk to buyers. It tells you which losses are worth an interview.

**What production would add:**
- A scheduled run (n8n, my default) pulling closed-lost deals straight from the HubSpot or Salesforce API
- Call-recording and email context per deal, not just the rep's notes
- A Slack check-in with the rep when the picklist and the notes disagree, before the reason gets locked in
- Writing the approved audited reason and re-engage date back to custom CRM properties, with an audit log
- Re-engage tasks or sequences created on the due date, owned by the right rep
- A feedback loop so reviewer corrections tune the signals and taxonomy over time

---

## 📁 What's in the repo

```
closed-lost-reason-agent/
├── agent.py                      # the agent
├── sample_closed_lost_deals.csv  # 8 fictional closed-lost deals
├── requirements.txt              # anthropic (optional, only used with a key)
├── .env.example                  # API key, model, went-dark days, competitors
├── SETUP.md                      # setup, real exports, CRM import, extending, troubleshooting
├── LICENSE                       # MIT
└── README.md
```

---

If you own the Closed Lost Reason field at your company, I'd love to hear which reasons your reps default to, and what the notes say instead.
