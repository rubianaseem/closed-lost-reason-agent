#!/usr/bin/env python3
"""
Closed-Lost Reason Agent
------------------------
Audits a closed-lost deal export from HubSpot or Salesforce and tells you
why you actually lost each deal, not just what the rep picked in the dropdown.

For every deal it:
  * reads the rep's notes and activity data and infers the real loss reason
  * flags picklist mismatches ("Price" picked, notes say "went with Gong")
  * flags data-quality gaps (blank notes, "Other", competitor not named,
    single-threaded, went dark weeks before the deal was closed)
  * marks the loss as controllable / product / uncontrollable
  * suggests a re-engage play and date

Runs with no API key using built-in rules. If ANTHROPIC_API_KEY is set it asks
Claude to classify each deal and write the summary, and falls back to the
rules on any API error. It only writes local files. It never writes to your CRM.

Usage:
  python agent.py                                   # sample data
  python agent.py --input ~/Downloads/closed_lost.csv --output out/
  python agent.py --no-llm                          # force rules only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "sample_closed_lost_deals.csv"
DEFAULT_OUTPUT = HERE / "out"
DEFAULT_MODEL = "claude-sonnet-5-5"

# ---------------------------------------------------------------------------
# 1. Configuration you will want to tune
# ---------------------------------------------------------------------------

# Map the column headers your CRM exports to the fields the agent uses.
ALIASES = {
    "deal_id": ["deal_id", "record id", "deal id", "opportunity id", "id", "opportunity_id"],
    "deal_name": ["deal_name", "deal name", "opportunity name", "name"],
    "company": ["company", "associated company", "account name", "account", "company name"],
    "owner": ["owner", "deal owner", "opportunity owner", "owner name"],
    "amount": ["amount", "deal amount", "amount (gbp)", "amount (usd)", "total contract value", "acv"],
    "stage_at_loss": ["stage_at_loss", "stage at loss", "last stage before lost", "previous stage", "stage before closed lost"],
    "created_date": ["created_date", "create date", "created date", "createdate"],
    "close_date": ["close_date", "close date", "closedate", "closed date"],
    "last_activity_date": ["last_activity_date", "last activity date", "last activity", "notes_last_updated", "lastactivitydate"],
    "contacts_engaged": ["contacts_engaged", "number of associated contacts", "num_associated_contacts", "contact roles", "contacts"],
    "lost_reason": ["lost_reason", "closed lost reason", "lost reason", "loss reason", "loss_reason__c", "closed_lost_reason"],
    "lost_reason_notes": ["lost_reason_notes", "closed lost notes", "lost reason notes", "loss reason notes", "loss notes",
                          "loss_reason_detail__c", "closed lost reason notes", "notes"],
    "competitor": ["competitor", "competitor name", "lost to", "primary competitor", "competitor__c"],
}

# The audited taxonomy. Keep it short: 5-9 buckets you can act on.
CATEGORIES = {
    "competitor": "Lost to competitor",
    "champion_lost": "Champion left / single-threaded",
    "no_decision": "No decision / status quo",
    "product_gap": "Product or security gap",
    "budget": "Budget",
    "timing": "Timing / deprioritised",
    "went_dark": "Went dark (no response)",
    "price": "Price / value not proven",
    "unknown": "Unknown (needs rep input)",
}

# What reps picked -> audited category. "Other" and blank map to None (vague).
PICKLIST_MAP = {
    "price": "price", "pricing": "price", "too expensive": "price",
    "budget": "budget", "no budget": "budget",
    "timing": "timing", "bad timing": "timing", "not a priority": "timing",
    "product fit": "product_gap", "product gap": "product_gap", "missing feature": "product_gap", "features": "product_gap",
    "lost to competitor": "competitor", "competitor": "competitor", "went with competitor": "competitor",
    "no decision": "no_decision", "status quo": "no_decision",
    "champion left": "champion_lost", "lost champion": "champion_lost",
    "no response": "went_dark", "unresponsive": "went_dark", "went dark": "went_dark",
    "other": None, "": None, "n/a": None, "unknown": None,
}

# Phrases that point to each category in rep notes (lowercase, regex allowed).
SIGNALS = {
    "competitor": [r"went with", r"chose \w+", r"signed with", r"competitor", r"switched to", r"picked \w+ over"],
    "champion_lost": [r"champion", r"left the company", r"new (vp|cro|head|director)", r"reorg", r"sponsor (left|moved)",
                      r"single[- ]threaded", r"our contact (left|moved)"],
    "no_decision": [r"no decision", r"status quo", r"spreadsheets?", r"do nothing", r"keep doing", r"stay with (their )?current"],
    "product_gap": [r"missing", r"no sso", r"soc ?2", r"security review", r"integration", r"doesn'?t support",
                    r"feature", r"roadmap", r"api limit"],
    "budget": [r"budget", r"frozen", r"hiring freeze", r"no funds", r"fy\d{2}", r"cost cutting", r"spend freeze"],
    "timing": [r"next year", r"next quarter", r"revisit", r"not a priority", r"deprioriti[sz]ed", r"timing", r"on hold", r"q[1-4]"],
    "went_dark": [r"stopped replying", r"ghosted", r"no answer", r"no response", r"went dark", r"unresponsive", r"\d+ follow[- ]?ups?"],
    "price": [r"too expensive", r"price", r"pricing", r"cheaper", r"cost", r"discount"],
}

# Tie-break order when two categories score the same.
PRIORITY = ["competitor", "champion_lost", "no_decision", "product_gap", "went_dark", "budget", "timing", "price"]

CONTROLLABILITY = {
    "went_dark": "Controllable (sales)",
    "champion_lost": "Controllable (sales)",
    "price": "Controllable (sales)",
    "competitor": "Partly controllable",
    "no_decision": "Partly controllable",
    "product_gap": "Product / roadmap",
    "budget": "Uncontrollable",
    "timing": "Uncontrollable",
    "unknown": "Unknown",
}

# Re-engage play: (days after close date, play). None = don't recycle yet.
REENGAGE = {
    "competitor": (300, "Their renewal window opens ~10-12 months after signing. Re-engage with a displacement angle vs {competitor}."),
    "champion_lost": (21, "Map the new decision-maker and send a short 'picking up where we left off' note. Multi-thread this time."),
    "no_decision": (60, "Lead with cost of inaction and find a sponsor who owns the pain."),
    "product_gap": (180, "Re-open when the gap ships. Log this deal against the roadmap item so product sees the revenue."),
    "budget": (120, "Check in before their next budget cycle with a one-page business case."),
    "timing": (90, "Re-engage when they said to and confirm the trigger they named."),
    "went_dark": (45, "Try a different contact and channel. Don't re-send the same sequence."),
    "price": (120, "Re-engage when packaging changes. Re-anchor on value with the economic buyer."),
    "unknown": (None, "Ask the rep for the real reason before recycling this deal."),
}

LATE_STAGES = {"proposal", "negotiation", "legal/procurement", "contract", "evaluation", "commit"}

# ---------------------------------------------------------------------------
# 2. Helpers
# ---------------------------------------------------------------------------


def load_dotenv(path: Path) -> None:
    """Tiny .env loader so we don't need an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ and val:
            os.environ[key] = val


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for candidate in (value, value[:10]):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%m/%d/%Y", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_amount(value: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", value or "")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def parse_int(value: str) -> int | None:
    cleaned = re.sub(r"[^\d]", "", value or "")
    return int(cleaned) if cleaned else None


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def money(x: float) -> str:
    return f"£{x:,.0f}"


def read_deals(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        lookup = {h.strip().lower(): h for h in headers}
        mapping = {}
        for field, names in ALIASES.items():
            for name in names:
                if name in lookup:
                    mapping[field] = lookup[name]
                    break
        missing = [f for f in ("deal_id", "lost_reason") if f not in mapping]
        if missing:
            sys.exit(f"Input is missing required column(s): {', '.join(missing)}. "
                     f"Found headers: {headers}. Add an alias in ALIASES at the top of agent.py.")
        deals = []
        for row in reader:
            deal = {field: (row.get(src) or "").strip() for field, src in mapping.items()}
            for field in ALIASES:
                deal.setdefault(field, "")
            deals.append(deal)
    return deals


# ---------------------------------------------------------------------------
# 3. Rule-based classification (always available)
# ---------------------------------------------------------------------------


def find_competitor(notes: str, competitor_field: str, known: list[str]) -> str:
    if competitor_field:
        return competitor_field
    for name in known:
        if name and re.search(rf"\b{re.escape(name.lower())}\b", notes.lower()):
            return name
    return ""


def reason_text(deal: dict) -> str:
    """Notes, plus the reason field itself when it is free text rather than a picklist value.
    (HubSpot's default 'Closed Lost Reason' property is free text, so it often holds the notes.)"""
    picked = deal["lost_reason"].strip()
    extra = picked if picked.lower() not in PICKLIST_MAP else ""
    return " ".join(x for x in (deal["lost_reason_notes"], extra) if x)


def classify_rules(deal: dict, known_competitors: list[str], went_dark_days: int) -> dict:
    notes = reason_text(deal)
    low = notes.lower()
    scores: Counter = Counter()
    evidence: dict[str, list[str]] = defaultdict(list)
    for cat, patterns in SIGNALS.items():
        for pat in patterns:
            m = re.search(pat, low)
            if m:
                scores[cat] += 1
                evidence[cat].append(m.group(0))

    competitor = find_competitor(notes, deal["competitor"], known_competitors)
    if competitor:
        scores["competitor"] += 2
        evidence["competitor"].insert(0, competitor)

    close, last = parse_date(deal["close_date"]), parse_date(deal["last_activity_date"])
    gap = (close - last).days if close and last else None
    if gap is not None and gap >= went_dark_days:
        scores["went_dark"] += 1
        evidence["went_dark"].append(f"no activity for {gap} days before close")

    if scores:
        top = max(scores.values())
        winners = [c for c in PRIORITY if scores.get(c) == top]
        inferred = winners[0]
        confidence = "high" if top >= 3 else "medium" if top == 2 else "low"
        if len([c for c in scores if scores[c] == top]) > 1 and confidence == "high":
            confidence = "medium"
        ev = ", ".join(dict.fromkeys(evidence[inferred]))
    else:
        inferred, confidence, ev = "unknown", "low", "no notes and no activity signal"

    return {
        "inferred": inferred,
        "confidence": confidence,
        "evidence": ev,
        "competitor": competitor,
        "gap_days": gap,
        "summary": "",
        "source": "rules",
    }


# ---------------------------------------------------------------------------
# 4. Optional Claude classification (only if ANTHROPIC_API_KEY is set)
# ---------------------------------------------------------------------------


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # noqa: WPS433
        return anthropic.Anthropic()
    except Exception as exc:  # package missing or bad config
        print(f"  ! Claude unavailable ({exc.__class__.__name__}); using built-in rules.")
        return None


def _ask(client, model: str, prompt: str, max_tokens: int) -> str:
    resp = client.messages.create(model=model, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": prompt}])
    return "".join(getattr(b, "text", "") for b in resp.content).strip()


def classify_llm(client, model: str, deal: dict, rules: dict) -> dict | None:
    cats = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    prompt = f"""You are a RevOps analyst auditing why a B2B deal was lost.
Pick exactly one category key from this list:
{cats}

Deal:
- Rep-picked reason: {deal['lost_reason'] or '(blank)'}
- Rep notes: {reason_text(deal) or '(blank)'}
- Competitor field: {deal['competitor'] or '(blank)'}
- Stage at loss: {deal['stage_at_loss'] or '(unknown)'}
- Contacts engaged: {deal['contacts_engaged'] or '(unknown)'}
- Days with no activity before close: {rules['gap_days'] if rules['gap_days'] is not None else '(unknown)'}

Base your answer only on this data. If the evidence is thin, say "low" confidence.
Reply with JSON only, no prose:
{{"category": "<key>", "confidence": "high|medium|low", "evidence": "<short phrase from the data>", "competitor": "<name or empty>", "summary": "<one sentence on why this deal was really lost>"}}"""
    try:
        text = _ask(client, model, prompt, 400)
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0)) if match else {}
        cat = data.get("category", "")
        if cat not in CATEGORIES:
            return None
        return {
            "inferred": cat,
            "confidence": data.get("confidence", "medium") if data.get("confidence") in ("high", "medium", "low") else "medium",
            "evidence": str(data.get("evidence", ""))[:200],
            "competitor": str(data.get("competitor") or rules["competitor"]),
            "gap_days": rules["gap_days"],
            "summary": str(data.get("summary", ""))[:300],
            "source": "claude",
        }
    except Exception as exc:
        print(f"  ! Claude call failed for {deal['deal_id']} ({exc.__class__.__name__}); using rules for this deal.")
        return None


# ---------------------------------------------------------------------------
# 5. Audit: flags, controllability, re-engage
# ---------------------------------------------------------------------------


def audit(deal: dict, result: dict, went_dark_days: int) -> dict:
    picked_raw = deal["lost_reason"].strip()
    picked = PICKLIST_MAP.get(picked_raw.lower(), "unmapped")
    inferred = result["inferred"]
    flags = []
    notes = reason_text(deal)

    if not notes:
        flags.append("missing_notes")
    elif len(notes) < 20:
        flags.append("notes_too_short")
    if picked is None:
        flags.append("vague_picklist")
    elif picked != "unmapped" and inferred != "unknown" and picked != inferred and result["confidence"] != "low":
        flags.append("picklist_mismatch")
    if inferred == "competitor" and not deal["competitor"]:
        flags.append("competitor_not_named")
    contacts = parse_int(deal["contacts_engaged"])
    if contacts is not None and contacts <= 1:
        flags.append("single_threaded")
    if result["gap_days"] is not None and result["gap_days"] >= went_dark_days:
        flags.append(f"went_dark_{result['gap_days']}d_before_close")

    days, play = REENGAGE[inferred]
    play = play.format(competitor=result["competitor"] or "the competitor")
    close = parse_date(deal["close_date"])
    reengage_date = ""
    if close and days is not None:
        due = close + timedelta(days=days)
        if due < date.today():
            due = date.today()
            play = "Due now. " + play
        reengage_date = due.isoformat()

    stage = deal["stage_at_loss"].lower()
    return {
        "deal_id": deal["deal_id"],
        "deal_name": deal["deal_name"],
        "company": deal["company"],
        "owner": deal["owner"],
        "amount": parse_amount(deal["amount"]),
        "stage_at_loss": deal["stage_at_loss"],
        "late_stage": "yes" if stage in LATE_STAGES else "no",
        "rep_picked_reason": picked_raw or "(blank)",
        "audited_reason": CATEGORIES[inferred],
        "audited_key": inferred,
        "confidence": result["confidence"],
        "evidence": result["evidence"],
        "competitor": result["competitor"],
        "controllability": CONTROLLABILITY[inferred],
        "data_quality_flags": "; ".join(flags),
        "reengage_date": reengage_date,
        "reengage_play": play,
        "summary": result["summary"] or template_summary(deal, inferred, result),
        "classified_by": result["source"],
    }


def template_summary(deal: dict, inferred: str, result: dict) -> str:
    who = deal["company"] or deal["deal_name"]
    if inferred == "unknown":
        return f"{who}: no usable notes or activity signal, so the real reason is unknown."
    bits = {
        "competitor": f"lost to {result['competitor'] or 'a competitor'}",
        "champion_lost": "the champion left and the deal had no other sponsor",
        "no_decision": "the buyer chose to keep the status quo",
        "product_gap": "a product or security gap blocked the deal",
        "budget": "budget was not available",
        "timing": "the project was pushed out",
        "went_dark": "the buyer went quiet and the deal was closed out later",
        "price": "price was the stated blocker, value was not proven",
    }
    return f"{who}: {bits[inferred]} (evidence: {result['evidence']})."


# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------


def build_stats(rows: list[dict]) -> dict:
    total = sum(r["amount"] for r in rows)
    by_audited = defaultdict(lambda: [0, 0.0])
    for r in rows:
        by_audited[r["audited_reason"]][0] += 1
        by_audited[r["audited_reason"]][1] += r["amount"]
    picked = Counter(r["rep_picked_reason"] for r in rows)
    flag_counts = Counter()
    for r in rows:
        for f in filter(None, r["data_quality_flags"].split("; ")):
            flag_counts[re.sub(r"_\d+d_", "_", f)] += 1
    mismatched = [r for r in rows if "picklist_mismatch" in r["data_quality_flags"]]
    vague = [r for r in rows if "vague_picklist" in r["data_quality_flags"]]
    controllable = sum(r["amount"] for r in rows if r["controllability"].startswith("Controllable"))
    return {
        "n": len(rows), "total": total, "by_audited": dict(by_audited), "picked": picked,
        "flags": flag_counts, "mismatched": mismatched, "vague": vague, "controllable": controllable,
    }


def field_fixes(stats: dict) -> list[str]:
    fixes = []
    n = stats["n"] or 1
    if stats["vague"]:
        fixes.append(f"'Other' or blank was picked on {len(stats['vague'])} of {n} deals. Make a short note required when "
                     f"'Other' is chosen, and add the buckets your notes keep pointing to.")
    if stats["mismatched"]:
        fixes.append(f"{len(stats['mismatched'])} of {n} picklist values contradict the rep's own notes. "
                     f"Review these in pipeline review before they reach a board deck.")
    if stats["flags"].get("competitor_not_named"):
        fixes.append(f"Competitor was not named on {plural(stats['flags']['competitor_not_named'], 'competitive loss').replace('losss', 'losses')}. "
                     f"Make Competitor required when the loss reason is a competitor.")
    if stats["flags"].get("missing_notes"):
        fixes.append(f"{plural(stats['flags']['missing_notes'], 'deal')} had no loss notes at all. Require a one-line note "
                     f"on the Closed Lost stage.")
    if stats["flags"].get("single_threaded"):
        fixes.append(f"{plural(stats['flags']['single_threaded'], 'lost deal')} had one contact or fewer. Worth a multi-threading "
                     f"check at the Evaluation stage.")
    if stats["flags"].get("went_dark_before_close"):
        fixes.append(f"{plural(stats['flags']['went_dark_before_close'], 'deal')} went quiet long before they were closed. "
                     f"Those were dead earlier than the pipeline said, so check your stale-deal rule.")
    return fixes or ["No structural issues found in this export."]


def template_exec_summary(stats: dict) -> str:
    if not stats["by_audited"]:
        return "No deals to summarise."
    top_reason, (top_n, top_amt) = max(stats["by_audited"].items(), key=lambda kv: kv[1][1])
    pct = lambda part: f"{(part / stats['total'] * 100):.0f}%" if stats["total"] else "0%"
    return (f"{stats['n']} closed-lost deals worth {money(stats['total'])} were audited. "
            f"The biggest audited loss reason by value is '{top_reason}' ({plural(top_n, 'deal')}, {money(top_amt)}, {pct(top_amt)} of lost value). "
            f"Rep-picked reasons were vague on {plural(len(stats['vague']), 'deal')} and contradicted the rep's own notes on "
            f"{len(stats['mismatched'])}. {money(stats['controllable'])} ({pct(stats['controllable'])}) was lost for reasons "
            f"sales could have influenced (went dark, champion loss, value not proven).")


def llm_exec_summary(client, model: str, stats: dict, rows: list[dict]) -> str | None:
    lines = "\n".join(f"- {r['deal_name']} | {money(r['amount'])} | picked: {r['rep_picked_reason']} | audited: "
                      f"{r['audited_reason']} ({r['confidence']}) | flags: {r['data_quality_flags'] or 'none'}" for r in rows)
    prompt = f"""You are a RevOps lead writing a short closed-lost readout for a sales leadership meeting.
Write 4-6 plain sentences. Lead with the biggest pattern by lost value, then the data-quality problem, then
one concrete fix for sales, one for product, one for RevOps. Use only the data below. Do not invent numbers.
Currency is GBP.

Totals: {stats['n']} deals, {money(stats['total'])} lost, {money(stats['controllable'])} lost for sales-controllable reasons.
Deals:
{lines}"""
    try:
        text = _ask(client, model, prompt, 600)
        return text or None
    except Exception as exc:
        print(f"  ! Claude summary failed ({exc.__class__.__name__}); using template summary.")
        return None


def write_outputs(rows: list[dict], stats: dict, exec_summary: str, out_dir: Path, mode: str, source: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_csv = out_dir / "closed_lost_audit.csv"
    import_csv = out_dir / "import_audited_reasons.csv"
    report_md = out_dir / "closed_lost_report.md"

    fields = ["deal_id", "deal_name", "company", "owner", "amount", "stage_at_loss", "late_stage", "rep_picked_reason",
              "audited_reason", "confidence", "evidence", "competitor", "controllability", "data_quality_flags",
              "reengage_date", "reengage_play", "summary", "classified_by"]
    with audit_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "amount": int(r["amount"]) if float(r["amount"]).is_integer() else r["amount"]})

    # Optional CRM import file: only rows the agent is reasonably sure about.
    with import_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Record ID", "Deal Name", "Lost Reason (Audited)", "Lost Reason Confidence", "Re-engage Date"])
        for r in rows:
            if r["audited_key"] != "unknown" and r["confidence"] in ("high", "medium"):
                w.writerow([r["deal_id"], r["deal_name"], r["audited_reason"], r["confidence"], r["reengage_date"]])

    md = [f"# Closed-lost reason audit",
          f"",
          f"_Source: `{source.name}` · {stats['n']} deals · generated {date.today().isoformat()} · mode: {mode}_",
          f"",
          f"## Summary",
          f"",
          exec_summary,
          f"",
          f"## What reps picked vs what the notes say",
          f"",
          f"| Deal | Amount | Rep picked | Audited reason | Confidence | Evidence |",
          f"|---|---:|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['deal_name']} | {money(r['amount'])} | {r['rep_picked_reason']} | {r['audited_reason']} | "
                  f"{r['confidence']} | {r['evidence']} |")
    md += ["", "## Lost value by audited reason", "", "| Audited reason | Deals | Lost value |", "|---|---:|---:|"]
    for reason, (n, amt) in sorted(stats["by_audited"].items(), key=lambda kv: -kv[1][1]):
        md.append(f"| {reason} | {n} | {money(amt)} |")
    md += ["", "## Data-quality issues", ""]
    if stats["flags"]:
        md += [f"- **{flag}**: {count}" for flag, count in stats["flags"].most_common()]
    else:
        md.append("- None found")
    md += ["", "## Fix the field (RevOps)", ""] + [f"- {x}" for x in field_fixes(stats)]
    md += ["", "## Re-engage queue", "", "| Date | Deal | Owner | Audited reason | Play |", "|---|---|---|---|---|"]
    for r in sorted([r for r in rows if r["reengage_date"]], key=lambda r: r["reengage_date"]):
        md.append(f"| {r['reengage_date']} | {r['deal_name']} | {r['owner']} | {r['audited_reason']} | {r['reengage_play']} |")
    unknown = [r for r in rows if not r["reengage_date"]]
    if unknown:
        md += ["", "Needs rep input before recycling: " + ", ".join(r["deal_name"] for r in unknown)]
    md += ["", "---", "", "_This report was generated from a CRM export. The agent did not change anything in your CRM._", ""]
    report_md.write_text("\n".join(md))
    return {"audit": audit_csv, "import": import_csv, "report": report_md}


# ---------------------------------------------------------------------------
# 7. Main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv(HERE / ".env")
    p = argparse.ArgumentParser(description="Audit closed-lost deals and find the real loss reasons.")
    p.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT, help="closed-lost deals CSV (HubSpot or Salesforce export)")
    p.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT, help="output folder (default: ./out)")
    p.add_argument("--no-llm", action="store_true", help="use built-in rules even if ANTHROPIC_API_KEY is set")
    p.add_argument("--max-llm-deals", type=int, default=200, help="cap on deals sent to Claude per run (cost guard)")
    p.add_argument("--went-dark-days", type=int, default=int(os.environ.get("WENT_DARK_DAYS", "30")))
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"Input file not found: {args.input}")
    known = [c.strip() for c in os.environ.get(
        "KNOWN_COMPETITORS", "Gong,Clari,Outreach,Salesloft,Apollo,People.ai,BoostUp").split(",") if c.strip()]
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    client = None if args.no_llm else get_client()
    mode = f"Claude ({model})" if client else "built-in rules (no API key)"

    deals = read_deals(args.input)
    bar = "=" * 76
    print(bar)
    print(f" CLOSED-LOST REASON AGENT  |  {args.input.name}  |  {len(deals)} deals  |  {mode}")
    print(bar)

    rows, failures = [], 0
    for i, deal in enumerate(deals):
        result = classify_rules(deal, known, args.went_dark_days)
        if client and i < args.max_llm_deals:
            llm = classify_llm(client, model, deal, result)
            failures = 0 if llm else failures + 1
            result = llm or result
            if failures >= 2:
                print("  ! Two Claude calls in a row failed. Switching to built-in rules for the rest of this run.")
                client, mode = None, "built-in rules (Claude calls failed)"
        rows.append(audit(deal, result, args.went_dark_days))

    for r in rows:
        tag = "MISMATCH" if "picklist_mismatch" in r["data_quality_flags"] else \
              "VAGUE" if "vague_picklist" in r["data_quality_flags"] else "OK"
        print(f"\n[{tag}] {r['deal_name']}  ({money(r['amount'])}, lost at {r['stage_at_loss'] or '?'}, owner {r['owner'] or '?'})")
        print(f"    rep picked : {r['rep_picked_reason']}")
        print(f"    audited    : {r['audited_reason']}  [{r['confidence']}]  evidence: {r['evidence']}")
        if r["data_quality_flags"]:
            print(f"    flags      : {r['data_quality_flags']}")
        print(f"    re-engage  : {r['reengage_date'] or 'n/a'}  {r['reengage_play']}")

    stats = build_stats(rows)
    summary = (llm_exec_summary(client, model, stats, rows) if client else None) or template_exec_summary(stats)
    files = write_outputs(rows, stats, summary, args.output, mode, args.input)

    print(f"\n{bar}\n SUMMARY\n{bar}")
    print(summary)
    print("\nLost value by audited reason:")
    for reason, (n, amt) in sorted(stats["by_audited"].items(), key=lambda kv: -kv[1][1]):
        print(f"  {reason:<34} {plural(n, 'deal'):>8}  {money(amt):>10}")
    print("\nFix the field:")
    for fix in field_fixes(stats):
        print(f"  - {fix}")
    print(f"\n{bar}\n FILES (nothing was written to your CRM)")
    for label, path in files.items():
        try:
            shown = path.relative_to(Path.cwd())
        except ValueError:
            shown = path
        print(f"  {label:<7} ./{shown}" if not str(shown).startswith("/") else f"  {label:<7} {shown}")
    print(bar)


if __name__ == "__main__":
    main()
