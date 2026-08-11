"""Build an Outlook DRAFT summarizing the Wednesday forecast-gap review.

Reuses the query + classification logic from forecast_gap_review.py so the email
never drifts from the terminal report. Draft only (mail.Save(), never .Send()).

Usage:  python forecast_gap_email.py [Owner Name] ...   (no args = default 3)
"""
import sys, io
from datetime import date
import win32com.client

from forecast_gap_review import (connect, fetch, classify, DEFAULT_OWNERS, LABELS,
                                 is_system_stamp)

# Shared Outlook helper — auto-inserts Cass's signature below the body.
from pathlib import Path
_SHARED = next((p / "_shared" for p in Path(__file__).resolve().parents
                if (p / "_shared" / "outlook_draft.py").exists()), None)
if _SHARED and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
from outlook_draft import open_draft

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OWNERS = sys.argv[1:] or DEFAULT_OWNERS
TODAY = date.today()
TO = "cass@ubiquitygp.com"  # draft lands with you to review + set recipients

# flag -> (row background color, one-line "what to do")
FLAG_META = {
    'A1': ('#D5F5E3', 'Active build/deal, no projected close. Add a forecast date.'),
    'A2': ('#FADBD8', 'Aging, but nobody set a Pursuit Status. Classify it or close it.'),
    'B':  ('#FCF3CF', 'Projected close already passed. Re-forecast or close.'),
    'E':  ('#FCF3CF', 'Agreement signed but stage never advanced. Advance the stage.'),
    'F':  ('#FDEBD0', 'Committed next-step date is past. Confirm it is still moving.'),
}

# ---------------------------------------------------------------- compute
sf = connect()
recs = fetch(sf, OWNERS)
flags = classify(recs, TODAY)
n_classified = sum(1 for r in recs if r.get('Substatus__c'))
n_stamped = sum(1 for r in recs
                if not r.get('Substatus__c') and is_system_stamp(r.get('Next_Action__c')))


def total(key):
    return sum(len(flags[key].get(o, [])) for o in OWNERS)


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def fmt_units(r):
    u = r['units']
    try:
        f = float(u)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return ''


def rows_for(key):
    out = []
    for o in OWNERS:
        out.extend(flags[key].get(o, []))
    return out


# ---------------------------------------------------------------- HTML pieces
def summary_table():
    head = ("<tr>"
            "<th align='left'>Flag</th>"
            + "".join(f"<th>{esc(o.split()[0])}</th>" for o in OWNERS)
            + "<th>Total</th><th align='left'>What it means / action</th></tr>")
    body = ""
    for key, label in LABELS:
        bg, action = FLAG_META[key]
        cells = "".join(
            f"<td align='center'>{len(flags[key].get(o, []))}</td>" for o in OWNERS)
        body += (f"<tr style='background:{bg};'>"
                 f"<td><b>{key}</b> {esc(label)}</td>{cells}"
                 f"<td align='center'><b>{total(key)}</b></td>"
                 f"<td>{esc(action)}</td></tr>")
    return (f"<table border='1' cellspacing='0' cellpadding='6' "
            f"style='border-collapse:collapse; font-size:10.5pt;'>"
            f"<thead style='background:#305496; color:#fff;'>{head}</thead>"
            f"<tbody>{body}</tbody></table>")


def detail_table(key, columns):
    """columns = list of (header, lambda row -> value)."""
    rows = sorted(rows_for(key), key=lambda r: (r['owner'], r['stage']))
    if not rows:
        return "<p><i>None this week.</i></p>"
    head = "".join(f"<th align='left'>{h}</th>" for h, _ in columns)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{esc(fn(r))}</td>" for _, fn in columns) + "</tr>"
    return (f"<table border='1' cellspacing='0' cellpadding='5' "
            f"style='border-collapse:collapse; font-size:10pt;'>"
            f"<thead style='background:#305496; color:#fff;'>"
            f"<tr>{head}</tr></thead><tbody>{body}</tbody></table>")


# standout cleanups: extreme-overdue next actions + placeholder forecasts
def standouts():
    seen, items = set(), []
    for r in sorted(rows_for('F'), key=lambda r: -(r['nad_past'] or 0)):
        if (r['nad_past'] or 0) >= 90 and r['name'] not in seen:
            seen.add(r['name'])
            items.append(f"<b>{esc(r['name'])}</b> ({esc(r['owner'].split()[0])}, "
                         f"{esc(r['stage'])}): next step {r['nad_past']} days overdue. "
                         f"{esc(r['na'][:90])}")
    placeholders = []
    pseen = set()
    for r in rows_for('F'):
        if 'placeholder' in r['na'].lower() and r['name'] not in pseen:
            pseen.add(r['name'])
            placeholders.append(f"<b>{esc(r['name'])}</b> ({esc(r['owner'].split()[0])})")
    html = ""
    if items:
        html += "<p><b>Long-dead, should close now (90+ days past their own next step):</b></p><ul>"
        html += "".join(f"<li>{x}</li>" for x in items) + "</ul>"
    if placeholders:
        html += ("<p><b>Placeholder forecasts to replace with a real date:</b> "
                 + ", ".join(placeholders) + "</p>")
    return html or "<p><i>No standout cleanups this week.</i></p>"


loc = lambda r: f"{r['city']}, {r['state']}".strip(', ')
nextstep = lambda r: r['na'][:70] or '-'

html = f"""
<html><body style="font-family:Calibri,Arial,sans-serif; font-size:11pt; color:#222;">
<p>Pipeline gaps for {esc(', '.join(o.split()[0] for o in OWNERS))} as of <b>{TODAY}</b>.
This is the inverse of the 30-90 day forecast view: open Opps people are working but
that are missing or breaking a forecast. Signal is the manually typed Next Action field
(activity dates are not logged in SF, so they are ignored). <b>{n_classified}</b> open Opps
already carry a Pursuit Status (team has classified them as stuck) and are excluded from
everything below. A further <b>{n_stamped}</b> carry a scripted note recording that they were
revived out of Closed Lost; nobody has picked those up yet, so no forecast date is owed on them
and they are excluded too.</p>

<h3>Summary</h3>
{summary_table()}
<p style="font-size:9.5pt; color:#666;">Counts are per-flag, not unique Opps (one Opp
can appear under several flags). F is the widest net and overlaps the others.</p>

<h3>A1. Add a forecast date ({total('A1')})</h3>
<p>Genuinely active, just no projected close. Lowest-effort fix.</p>
{detail_table('A1', [('Owner', lambda r: r['owner'].split()[0]), ('Property', lambda r: r['name']),
                     ('Stage', lambda r: r['stage']), ('Units', fmt_units),
                     ('Location', loc), ('Next step', nextstep)])}

<h3>A2. Aging and unclassified ({total('A2')})</h3>
<p>Old next step, no forecast, and no Pursuit Status set. The team has not said why
these are stuck. Either set a Pursuit Status or close them.</p>
{detail_table('A2', [('Owner', lambda r: r['owner'].split()[0]), ('Property', lambda r: r['name']),
                     ('Stage', lambda r: r['stage']), ('Stale', lambda r: r['note']),
                     ('Units', fmt_units), ('Last note', lambda r: r['na'][:60])])}

<h3>B. Forecast already slipped ({total('B')})</h3>
<p>Projected close date is in the past, deal still open.</p>
{detail_table('B', [('Owner', lambda r: r['owner'].split()[0]), ('Property', lambda r: r['name']),
                    ('Stage', lambda r: r['stage']), ('Overdue', lambda r: r['note']),
                    ('Units', fmt_units)])}

<h3>Standout cleanups</h3>
{standouts()}

<p style="font-size:9.5pt; color:#666;">E (agreement signed, stage stuck = {total('E')}) and
F (overdue next action = {total('F')}) are best walked live from the terminal report
(<code>forecast_gap_review.py</code>); too long to list here.</p>

<p>Cass</p>
</body></html>
"""

# ---------------------------------------------------------------- Outlook draft
SUBJECT = f"Wednesday Pipeline Review: Forecast Gaps ({TODAY})"

outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
drafts = ns.GetDefaultFolder(16)  # olFolderDrafts
for item in list(drafts.Items):  # snapshot; clear prior run of this same review
    try:
        if getattr(item, 'Subject', None) == SUBJECT:
            item.Delete()
            print(f"Removed prior draft: {item.Subject!r}")
    except Exception:
        pass

# open_draft auto-inserts Cass's signature; Save (no Display) lands the draft
# silently in Drafts to review later — matches prior behavior.
mail = open_draft(subject=SUBJECT, body_html=html, to=TO, save=True, display=False)

print("Outlook draft saved.")
print(f"  To: {mail.To}")
print(f"  Subject: {mail.Subject}")
print(f"  Counts: " + ", ".join(f"{k}={total(k)}" for k, _ in LABELS))
