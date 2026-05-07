"""
Industry Briefing - Daily email digest for financial services professionals
Covers recordkeeping, investment, and custodial industry news powered by Claude AI.
"""

import os
import re
import sys
import json
import smtplib
import asyncio
import aiohttp
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

# ── Configuration ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS     = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD= os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL   = os.environ.get("RECIPIENT_EMAIL", GMAIL_ADDRESS)
RECIPIENTS        = [r.strip() for r in RECIPIENT_EMAIL.split(",")]

TIMEZONE = "America/Chicago"
MODEL    = "claude-sonnet-4-5"
MAX_TOK  = 4096
HEADERS  = {
    "Content-Type": "application/json",
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
}
SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]

# ── Claude helper ─────────────────────────────────────────────────────────────
async def ask_claude(session, label, prompt, use_search=False):
    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": MODEL,
        "max_tokens": MAX_TOK,
        "messages": messages,
    }
    if use_search:
        body["tools"] = SEARCH_TOOL

    for turn in range(10):
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=HEADERS, json=body
        ) as r:
            if r.status != 200:
                raw = await r.text()
                raise RuntimeError(f"[{label}] HTTP {r.status}: {raw[:400]}")
            data = await r.json()

        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            break

        if stop_reason == "tool_use":
            tool_results = []
            for block in content:
                if block.get("type") == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": "Search results retrieved.",
                    })
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                body["messages"] = messages
                continue
        break

    text = "".join(
        b["text"] for b in data.get("content", []) if b.get("type") == "text"
    ).strip()

    if not text:
        raise ValueError(
            f"[{label}] Empty response. content={json.dumps(data.get('content', []))[:300]}"
        )

    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    match = re.search(r'\{.*\}|\[.*\]', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"[{label}] No JSON found: {text[:300]}")


# ── Individual fetchers ───────────────────────────────────────────────────────
async def fetch_industry_news(session, today):
    return await ask_claude(session, "industry_news", f"""
You are an industry analyst covering the retirement and financial services industry on {today}.
Search the web for today's top news stories specifically about:
- Recordkeeping companies (Fidelity, Empower, Voya, Principal, Transamerica, Ascensus, etc.)
- Custodial and trust companies (Charles Schwab, Pershing, Fidelity, BNY Mellon, etc.)
- Investment managers and asset managers (Vanguard, BlackRock, T. Rowe Price, etc.)
- 401k, 403b, IRA, and retirement plan industry developments
- ERISA, DOL, SEC regulatory updates affecting the retirement industry

Return between 3 and 5 stories as JSON only — no markdown, no preamble, no explanation.
Include stories from the last 48 hours if today's news is limited.
{{"overview":"2-3 sentence summary of today's biggest industry themes","stories":[{{"title":"...","category":"recordkeeping|custodial|investment|regulatory|technology","summary":"2-3 sentences: what happened and why it matters to the industry","sources":["Source1","Source2"],"sourceCount":2}}]}}
""", use_search=True)

async def fetch_ma_activity(session, today):
    return await ask_claude(session, "ma_activity", f"""
Search the web for recent mergers, acquisitions, partnerships, and strategic transactions in:
- Retirement plan recordkeeping industry
- Custodial and trust services
- Investment management and asset management
- Financial technology (fintech) serving retirement plans

Look for news from the last 7 days as of {today}. Include rumored deals, completed transactions, and strategic partnerships.
Return JSON only — no markdown, no preamble:
{{"summary":"2-3 sentence overview of current M&A activity","deals":[{{"type":"acquisition|merger|partnership|investment|rumor","acquirer":"Company name","target":"Company name","value":"$X billion or undisclosed","status":"announced|completed|rumored|pending","description":"2-3 sentences on what this means for the industry","source":"Source name"}}]}}
If no deals found, return: {{"summary":"No significant M&A activity reported in the past 7 days.","deals":[]}}
""", use_search=True)

async def fetch_partner_updates(session, today):
    return await ask_claude(session, "partner_updates", f"""
Search the web for recent strategic news, product launches, leadership changes, or announcements from these key players in the retirement and financial services industry as of {today}:
- Major recordkeepers: Fidelity, Empower, Voya, Principal, Transamerica, Ascensus, John Hancock, Nationwide
- Custodians: Schwab, Pershing/BNY Mellon, Fidelity Institutional, Apex Clearing
- Investment managers: Vanguard, BlackRock, T. Rowe Price, American Funds, TIAA
- Industry organizations: SPARK, PSCA, ASPPA, ICI

Return JSON only — no markdown, no preamble:
{{"updates":[{{"company":"Company name","category":"recordkeeper|custodian|investment_manager|industry_org","headline":"Brief headline","detail":"2-3 sentences describing the update and its significance","source":"Source name"}}]}}
Return between 2 and 5 updates. If limited news, return the most recent relevant updates from the past week.
""", use_search=True)

async def fetch_regulatory_pulse(session, today):
    return await ask_claude(session, "regulatory", f"""
Search for the latest regulatory and legislative developments affecting retirement plans and financial services as of {today}:
- Department of Labor (DOL) guidance, rules, or enforcement actions
- SEC rules affecting investment advisers or retirement plans
- IRS retirement plan guidance or contribution limit updates
- Congressional activity on retirement legislation (SECURE Act updates, etc.)
- FINRA notices affecting broker-dealers serving retirement plans

Return JSON only — no markdown, no preamble:
{{"pulse":"1-2 sentence overall regulatory climate summary","items":[{{"agency":"DOL|SEC|IRS|Congress|FINRA|Other","title":"Brief title","summary":"2-3 sentences on what was issued and its practical impact","date":"Date or approximate timeframe","source":"Source name"}}]}}
Return between 1 and 4 items. If nothing new, return the most recent significant item with its date.
""", use_search=True)

async def fetch_market_snapshot(session, today):
    return await ask_claude(session, "markets", f"""
Search for today's market data relevant to retirement plan investors as of {today}.
Include: S&P 500, Nasdaq, Dow Jones, 10-year Treasury yield, and any relevant bond index.
Return JSON only — no markdown, no preamble:
{{"summary":"1-2 sentence market summary relevant to retirement investors","indices":[{{"name":"S&P 500","value":"5,800","change":"+12","pct":"+0.21%","direction":"up"}}],"bond_yield":{{"ten_year":"4.45%","change":"+0.02%","direction":"up"}},"note":"One sentence on what this means for retirement plan participants."}}
""", use_search=True)

async def fetch_quote(session):
    return await ask_claude(session, "quote", """
Pick a powerful, thought-provoking inspirational or motivational quote well suited to start a professional's workday.
Vary the source — consider leaders, philosophers, athletes, authors, or business figures.
Return JSON only — no markdown, no preamble:
{"quote":"Full quote text","author":"Author name","descriptor":"Brief descriptor of who they are (e.g. Former U.S. President, Stoic philosopher, NBA coach)"}
""", use_search=False)

async def fetch_holidays(session, today):
    return await ask_claude(session, "holidays", f"""
Today is {today}. Check whether today is a nationally recognized public holiday in any of these countries:
United States, Canada, India, Bangladesh.
Only include OFFICIAL national public holidays — not observances, awareness days, or minor holidays.
Return JSON only — no markdown, no preamble:
{{"holidays":[{{"country":"United States","name":"Memorial Day","description":"1-2 sentences about the holiday and how it is observed."}}]}}
If no holidays today, return: {{"holidays":[]}}
""", use_search=False)

# ── Topic loader ──────────────────────────────────────────────────────────────
TOPICS_FILE = os.path.join(os.path.dirname(__file__), "topics.json")

def load_active_topic(today_date):
    """
    Reads topics.json and returns the active topic for this week.
    Logic:
      - If a topic has status='active', use it.
      - Every Monday, advance to the next 'pending' topic, mark it 'active',
        mark the previously active one 'completed', and save the file.
      - Returns None if no topics are available.
    """
    try:
        with open(TOPICS_FILE, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not read topics.json: {e}", file=sys.stderr)
        return None

    topics = data.get("topics", [])
    today  = today_date
    is_monday = today.weekday() == 0  # 0 = Monday

    # Find currently active topic
    active = next((t for t in topics if t.get("status") == "active"), None)

    if is_monday:
        # Advance to next pending topic every Monday
        next_topic = next((t for t in topics if t.get("status") == "pending"), None)
        if next_topic:
            if active:
                active["status"] = "completed"
            next_topic["status"] = "active"
            next_topic["week_of"] = today.strftime("%Y-%m-%d")
            active = next_topic
            try:
                with open(TOPICS_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"  Topic advanced to: [{active['id']}] {active['title']}")
            except Exception as e:
                print(f"  WARNING: Could not save topics.json: {e}", file=sys.stderr)

    return active

async def fetch_fun_fact(session, topic):
    """Generate a Fun Fact based on the active compliance topic."""
    if not topic:
        return None
    return await ask_claude(session, "fun_fact", f"""
You are a retirement plan compliance expert writing a brief, practical daily tip for plan administrators,
recordkeepers, and TPAs. Today's topic is:

CATEGORY: {topic.get('category','').upper().replace('_',' ')}
TOPIC: {topic.get('title','')}
FOCUS: {topic.get('prompt_focus','')}

Write a concise, digestible fun fact or compliance tip on this topic. It should:
- Be practical and actionable — something a professional can use or remember
- Be 3-5 sentences maximum — this is a daily digest item, not an article
- Highlight one specific rule, deadline, dollar amount, or common mistake
- Be accurate based on current IRS/DOL guidance

Return JSON only — no markdown, no preamble:
{{"headline":"A short punchy headline for this tip (max 10 words)","fact":"The 3-5 sentence tip text.","category":"{topic.get('category','')}","topic_title":"{topic.get('title','')}","tip_label":"Key rule|Important deadline|Common mistake|Quick math|Did you know"}}
""", use_search=False)


# ── Email renderer ────────────────────────────────────────────────────────────
CATEGORY_BADGE = {
    "recordkeeping": ("#E6F1FB", "#0C447C", "Recordkeeping"),
    "custodial":     ("#E1F5EE", "#085041", "Custodial"),
    "investment":    ("#EEEDFE", "#3C3489", "Investment"),
    "regulatory":    ("#FAEEDA", "#633806", "Regulatory"),
    "technology":    ("#EAF3DE", "#27500A", "Technology"),
}

DEAL_TYPE_COLOR = {
    "acquisition": ("#FDE8E8", "#8B1A1A"),
    "merger":      ("#FDE8E8", "#8B1A1A"),
    "partnership": ("#E6F1FB", "#0C447C"),
    "investment":  ("#EEEDFE", "#3C3489"),
    "rumor":       ("#F5F5F5", "#666666"),
}

def direction_arrow(d): return "▲" if d == "up" else "▼"
def direction_color(d): return "#1a7a3c" if d == "up" else "#c0392b"

def render_email(today_str, industry_news, ma_activity, partner_updates, regulatory, markets, quote, holidays, fun_fact):

    # ── holiday block (only shown when there are holidays) ───
    holiday_items = holidays.get("holidays") or []
    if holiday_items:
        country_flag = {"United States": "🇺🇸", "Canada": "🇨🇦", "India": "🇮🇳", "Bangladesh": "🇧🇩"}
        rows = ""
        for h in holiday_items:
            flag = country_flag.get(h.get("country", ""), "🌍")
            rows += f"""
          <div style="margin-bottom:10px">
            <p style="margin:0 0 2px;font-size:13px;font-weight:700;color:#1a1a1a">{flag} {h.get('name','')} <span style="font-weight:400;color:#999">· {h.get('country','')}</span></p>
            <p style="margin:0;font-size:13px;color:#555;line-height:1.5">{h.get('description','')}</p>
          </div>"""
        holiday_block = f"""
  <!-- Holidays -->
  <div style="background:#EAF3DE;border-radius:12px;padding:18px 28px;margin-bottom:16px;border:1px solid #c8e0b0">
    <p style="margin:0 0 12px;font-size:11px;font-weight:700;color:#27500A;letter-spacing:.06em;text-transform:uppercase">Today's Holidays</p>
    {rows}
  </div>"""
    else:
        holiday_block = ""

    # ── fun fact block ───
    CATEGORY_COLORS = {
        "secure2":            ("#E6F1FB", "#0C447C", "#d0e4f7"),
        "compliance_testing": ("#EEEDFE", "#3C3489", "#dddcfc"),
        "form_5500":          ("#FAEEDA", "#633806", "#f5dfc0"),
        "form_5330":          ("#FDE8E8", "#8B1A1A", "#f9d0d0"),
        "epcrs":              ("#EAF3DE", "#27500A", "#d0e8c0"),
    }
    TIP_LABEL_ICON = {
        "Key rule": "📌",
        "Important deadline": "⏰",
        "Common mistake": "⚠️",
        "Quick math": "🔢",
        "Did you know": "💡",
    }
    if fun_fact:
        cat = fun_fact.get("category", "secure2")
        bg, fg, border = CATEGORY_COLORS.get(cat, ("#f0f0f0", "#333", "#ddd"))
        tip_label = fun_fact.get("tip_label", "Did you know")
        icon = TIP_LABEL_ICON.get(tip_label, "💡")
        cat_display = cat.replace("_", " ").upper().replace("SECURE2", "SECURE 2.0")
        fun_fact_block = f"""
  <!-- Fun Fact -->
  <div style="background:{bg};border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid {border}">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px">
      <p style="margin:0;font-size:11px;font-weight:700;color:{fg};letter-spacing:.06em;text-transform:uppercase">💼 Compliance Fun Fact · {cat_display}</p>
      <span style="font-size:11px;color:{fg};background:rgba(255,255,255,0.6);padding:2px 8px;border-radius:5px;font-weight:600">{icon} {tip_label}</span>
    </div>
    <p style="margin:0 0 6px;font-size:15px;font-weight:700;color:#1a1a1a;line-height:1.4">{fun_fact.get('headline','')}</p>
    <p style="margin:0 0 10px;font-size:13px;color:#333;line-height:1.7">{fun_fact.get('fact','')}</p>
    <p style="margin:0;font-size:11px;color:{fg};font-style:italic">Topic this week: {fun_fact.get('topic_title','')}</p>
  </div>"""
    else:
        fun_fact_block = ""

    # ── story cards ───
    story_cards = ""
    for s in (industry_news.get("stories") or []):
        cat = s.get("category", "recordkeeping")
        bg, fg, label = CATEGORY_BADGE.get(cat, ("#f0f0f0", "#333", cat.title()))
        srcs = ", ".join((s.get("sources") or [])[:3])
        cnt = s.get("sourceCount", len(s.get("sources") or []))
        story_cards += f"""
        <div style="background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:16px 20px;margin-bottom:12px">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px">
            <p style="margin:0;font-size:15px;font-weight:600;color:#1a1a1a;line-height:1.4">{s['title']}</p>
            <span style="background:{bg};color:{fg};font-size:11px;padding:3px 9px;border-radius:6px;white-space:nowrap;flex-shrink:0">{label}</span>
          </div>
          <p style="margin:0 0 10px;font-size:13px;color:#555;line-height:1.6">{s['summary']}</p>
          <p style="margin:0;font-size:12px;color:#999">{srcs} &nbsp;·&nbsp; {cnt} source{'s' if cnt != 1 else ''}</p>
        </div>"""

    # ── M&A deal cards ───
    deal_cards = ""
    for d in (ma_activity.get("deals") or []):
        dtype = d.get("type", "acquisition")
        bg, fg = DEAL_TYPE_COLOR.get(dtype, ("#f0f0f0", "#333"))
        status_color = "#1a7a3c" if d.get("status") == "completed" else "#b36a00" if d.get("status") == "announced" else "#666"
        deal_cards += f"""
        <div style="background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:16px 20px;margin-bottom:12px">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px">
            <p style="margin:0;font-size:15px;font-weight:600;color:#1a1a1a">{d.get('acquirer','—')} → {d.get('target','—')}</p>
            <span style="background:{bg};color:{fg};font-size:11px;padding:3px 9px;border-radius:6px;white-space:nowrap;flex-shrink:0">{dtype.title()}</span>
          </div>
          <p style="margin:0 0 6px;font-size:12px;color:{status_color};font-weight:600;text-transform:uppercase;letter-spacing:.04em">{d.get('status','').title()} · {d.get('value','Undisclosed')}</p>
          <p style="margin:0 0 8px;font-size:13px;color:#555;line-height:1.6">{d.get('description','')}</p>
          <p style="margin:0;font-size:12px;color:#999">{d.get('source','')}</p>
        </div>"""

    if not deal_cards:
        deal_cards = '<p style="margin:0;font-size:13px;color:#999;font-style:italic">No significant M&A activity reported this week.</p>'

    # ── partner update rows ───
    partner_rows = ""
    for u in (partner_updates.get("updates") or []):
        cat = u.get("category", "recordkeeper")
        cat_label = cat.replace("_", " ").title()
        partner_rows += f"""
        <div style="padding:14px 0;border-bottom:1px solid #f0f0f0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:13px;font-weight:700;color:#1a1a1a">{u.get('company','')}</span>
            <span style="font-size:11px;color:#999">· {cat_label}</span>
          </div>
          <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#333">{u.get('headline','')}</p>
          <p style="margin:0 0 4px;font-size:13px;color:#555;line-height:1.5">{u.get('detail','')}</p>
          <p style="margin:0;font-size:12px;color:#999">{u.get('source','')}</p>
        </div>"""

    # ── regulatory items ───
    reg_items = ""
    for item in (regulatory.get("items") or []):
        reg_items += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f0f0f0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="background:#FAEEDA;color:#633806;font-size:11px;padding:2px 8px;border-radius:5px;font-weight:600">{item.get('agency','')}</span>
            <span style="font-size:12px;color:#999">{item.get('date','')}</span>
          </div>
          <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#1a1a1a">{item.get('title','')}</p>
          <p style="margin:0 0 4px;font-size:13px;color:#555;line-height:1.5">{item.get('summary','')}</p>
          <p style="margin:0;font-size:12px;color:#999">{item.get('source','')}</p>
        </div>"""

    # ── market index rows ───
    idx_rows = ""
    for i in (markets.get("indices") or []):
        c = direction_color(i.get("direction", "up"))
        a = direction_arrow(i.get("direction", "up"))
        idx_rows += f"""
        <tr>
          <td style="padding:6px 12px;font-size:14px;color:#1a1a1a;border-bottom:1px solid #f0f0f0">{i['name']}</td>
          <td style="padding:6px 12px;font-size:14px;font-weight:600;text-align:right;border-bottom:1px solid #f0f0f0">{i['value']}</td>
          <td style="padding:6px 12px;font-size:13px;color:{c};text-align:right;border-bottom:1px solid #f0f0f0">{a} {i['change']} ({i['pct']})</td>
        </tr>"""

    bond = markets.get("bond_yield", {})
    bond_color = direction_color(bond.get("direction", "up"))
    bond_arrow = direction_arrow(bond.get("direction", "up"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Industry Briefing — {today_str}</title></head>
<body style="margin:0;padding:0;background:#f5f5f3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="background:#0C2340;border-radius:12px;padding:24px 28px;margin-bottom:16px">
    <p style="margin:0 0 4px;font-size:12px;color:#7ca3c8;letter-spacing:.06em;text-transform:uppercase">Industry Intelligence</p>
    <h1 style="margin:0 0 6px;font-size:26px;font-weight:700;color:#ffffff">{today_str}</h1>
    <p style="margin:0;font-size:14px;color:#a8c4df;line-height:1.5">{industry_news.get('overview','')}</p>
  </div>

  <!-- Quote of the Day -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 10px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Quote of the Day</p>
    <blockquote style="margin:0 0 8px;padding-left:14px;border-left:3px solid #0C2340;font-size:16px;font-style:italic;color:#1a1a1a;line-height:1.7">"{quote.get('quote','')}"</blockquote>
    <p style="margin:0;font-size:13px;color:#777">— {quote.get('author','')} <span style="color:#bbb">· {quote.get('descriptor','')}</span></p>
  </div>

  {holiday_block}

  {fun_fact_block}

  <!-- Industry News -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 16px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Industry News</p>
    {story_cards}
  </div>

  <!-- M&A Activity -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 6px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Mergers & Acquisitions</p>
    <p style="margin:0 0 16px;font-size:13px;color:#555">{ma_activity.get('summary','')}</p>
    {deal_cards}
  </div>

  <!-- Strategic Partner Updates -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Strategic Partner Updates</p>
    {partner_rows}
  </div>

  <!-- Regulatory Pulse -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 6px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Regulatory Pulse</p>
    <p style="margin:0 0 12px;font-size:13px;color:#555;font-style:italic">{regulatory.get('pulse','')}</p>
    {reg_items}
  </div>

  <!-- Market Snapshot -->
  <div style="background:#fff;border-radius:12px;padding:20px 28px;margin-bottom:16px;border:1px solid #e8e8e8">
    <p style="margin:0 0 6px;font-size:11px;font-weight:700;color:#999;letter-spacing:.06em;text-transform:uppercase">Market Snapshot</p>
    <p style="margin:0 0 12px;font-size:13px;color:#555">{markets.get('summary','')}</p>
    <table style="width:100%;border-collapse:collapse">
      <tr style="background:#f8f8f6">
        <th style="padding:6px 12px;font-size:11px;color:#999;text-align:left;font-weight:500">Index</th>
        <th style="padding:6px 12px;font-size:11px;color:#999;text-align:right;font-weight:500">Price</th>
        <th style="padding:6px 12px;font-size:11px;color:#999;text-align:right;font-weight:500">Change</th>
      </tr>
      {idx_rows}
      <tr>
        <td style="padding:6px 12px;font-size:14px;color:#1a1a1a;border-bottom:1px solid #f0f0f0">10-yr Treasury</td>
        <td style="padding:6px 12px;font-size:14px;font-weight:600;text-align:right;border-bottom:1px solid #f0f0f0">{bond.get('ten_year','—')}</td>
        <td style="padding:6px 12px;font-size:13px;color:{bond_color};text-align:right;border-bottom:1px solid #f0f0f0">{bond_arrow} {bond.get('change','—')}</td>
      </tr>
    </table>
    <p style="margin:10px 0 0;font-size:12px;color:#888;font-style:italic">{markets.get('note','')}</p>
  </div>

  <!-- Footer -->
  <p style="text-align:center;font-size:11px;color:#bbb;margin:16px 0 0">
    Industry Intelligence Briefing · {datetime.now(ZoneInfo(TIMEZONE)).strftime('%I:%M %p CT')} · Powered by Claude AI
  </p>

</div>
</body>
</html>"""
    return html


# ── Email sender ──────────────────────────────────────────────────────────────
def send_email(subject, html_body, recipients):
    for recipient in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = recipient
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, recipient, msg.as_string())


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    tz  = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_str   = now.strftime("%A, %B %-d, %Y")
    today_short = now.strftime("%b %-d")

    print(f"[{now.strftime('%H:%M')}] Generating industry briefing for {today_str}...")
    print(f"  model={MODEL}  api_key={'SET' if ANTHROPIC_API_KEY else 'MISSING'}")

    # Load the active compliance topic from topics.json
    active_topic = load_active_topic(now.date())
    if active_topic:
        print(f"  Topic: [{active_topic['id']}] {active_topic['title']}")
    else:
        print("  WARNING: No active topic found in topics.json", file=sys.stderr)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch_industry_news(session, today_str),
            fetch_ma_activity(session, today_str),
            fetch_partner_updates(session, today_str),
            fetch_regulatory_pulse(session, today_str),
            fetch_market_snapshot(session, today_str),
            fetch_quote(session),
            fetch_holidays(session, today_str),
            fetch_fun_fact(session, active_topic),
            return_exceptions=True
        )

    industry_news, ma_activity, partner_updates, regulatory, markets, quote, holidays, fun_fact = results

    for name, result in zip(
        ["industry_news", "ma_activity", "partner_updates", "regulatory", "markets", "quote", "holidays", "fun_fact"], results
    ):
        if isinstance(result, Exception):
            print(f"  FAILED [{name}]: {type(result).__name__}: {result}", file=sys.stderr)
        else:
            print(f"  OK     [{name}]")

    if isinstance(industry_news,   Exception): industry_news   = {"overview": "News unavailable.", "stories": []}
    if isinstance(ma_activity,     Exception): ma_activity     = {"summary": "M&A data unavailable.", "deals": []}
    if isinstance(partner_updates, Exception): partner_updates = {"updates": []}
    if isinstance(regulatory,      Exception): regulatory      = {"pulse": "Regulatory data unavailable.", "items": []}
    if isinstance(markets,         Exception): markets         = {"summary": "Market data unavailable.", "indices": []}
    if isinstance(quote,           Exception): quote           = {"quote": "The secret of getting ahead is getting started.", "author": "Mark Twain", "descriptor": "American author"}
    if isinstance(holidays,        Exception): holidays        = {"holidays": []}
    if isinstance(fun_fact,        Exception): fun_fact        = None

    print("  Rendering and sending email...")
    html    = render_email(today_str, industry_news, ma_activity, partner_updates, regulatory, markets, quote, holidays, fun_fact)
    subject = f"Industry Briefing · {today_short}"
    send_email(subject, html, RECIPIENTS)
    print(f"  Email sent to: {', '.join(RECIPIENTS)}")

if __name__ == "__main__":
    asyncio.run(main())
