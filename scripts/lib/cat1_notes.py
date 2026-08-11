"""Categorize CAT1 opportunities by what their Salesforce notes reveal.

Single source of truth for the note-mining heuristics, shared by the triage
workbook generator and any later bulk-update script. Extracted from the
2026-06-10 investigation probe.

The classification is keyword-derived and therefore fuzzy: every consumer should
surface the triggering note snippet alongside the label so a human can verify
individual calls. Stage is authoritative; notes add the "why".
"""
from __future__ import annotations

import re

# strip the migrated "Author | 2024-07-24 20:36:03" prefix -> note body only
_PREFIX = re.compile(r"^.*?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")


def clean(text: str | None) -> str:
    return _PREFIX.sub("", text or "").strip()


# (label, action, regex) -- order = priority, first match wins
RULES = [
    ("Built / Activated", "Reassign owner or close-won (already live)",
     r"\bactivat|under construction|now live|is live|went live|in service|in-service|energized"),
    ("Secured (PAL/ROE/EMA signed)", "Reassign owner (agreement secured)",
     r"pal signed|roe signed|ema signed|amendment.*sign|addendum.*sign|fully executed|commission|door fee|msa.*execut|draft pal sent|easement (agreement|in place)|easement with"),
    ("Existing Bulk / incumbent (competitor locked)", "Leave or close-lost (legit dead)",
     r"existing bulk|existing fiber|\bbulk (agreement|deal|contract)|bulk with|dp bulk|on (a )?bulk|moving (status |to )?existing bulk|spectrum|charter|\bcox\b|coax|already (served|wired|fiber)|incumbent|att fiber|at&t|google fiber|frontier|verizon|fios|hardwired|1 ?gb internet|internet in every unit|community-?wide wi-?fi|high.?speed internet|\d ?year agreement|current.*agreement"),
    ("Blocked — moratorium / exclusivity", "Leave (external block)",
     r"moratorium|exclusiv|under exclusivity|no access|cannot access|hoa restrict"),
    ("Owner denial / declined / halted", "Leave or close-lost (legit dead)",
     r"declin|not interest|no interest|denied|denial|rejected|passed on us|chose (another|a different)|going with|signed with (another|competitor)|not pursuing|not moving forward|project.*(halted|dead|cancel)"),
    ("Disqualified / not a target", "Deprioritize / DQ (size/serviceability)",
     r"disqualif|no mdu|not an mdu|unserviceable|no longer exists|sfu community|sfu\b|single family|under 25|under-25|only \d+ unit|too small|\b[1-9] units?\b|\b1[0-5] units?\b|duplex|below.*threshold|costar.*\d+ unit|\d+ units?,? per costar"),
    ("Low return / not viable", "Deprioritize (economics)",
     r"low return|low roi|not viable|poor (economics|return)|doesn'?t pencil|not worth|low priority|deprioriti|potential for low"),
    ("Hand off to Markets/local team", "Route to correct team",
     r"markets? team|local team|pass(ed)? (on|to)|hand ?off|hand(ed)? (to|over)|belongs to|route to|transfer to"),
    ("Sold / ownership change", "Re-verify owner then work",
     r"sold|new owner|under new|acquir|management chang|change of owner|new management|reo\b|foreclos"),
    ("Unresponsive / no contact", "Work or close (stalled on contact)",
     r"unrespons|no response|no reply|left (a )?(vm|voicemail|message)|no contact|ghosted|follow.?up.*no|attempted|no answer"),
    ("Active outreach (was being worked)", "Reassign to active rep, continue",
     r"reached (back )?out|emailed|working on reaching|setup a meeting|set up a meeting|restart.*conversation|lead off|new opp|creating .*opp|submitting (pal|roe)"),
    ("Construction / build phase", "Track (in build)",
     r"construction|permitting|trenching|boring|design (plan|phase)|make ready|mdu build|build phase"),
]

NO_STORY = ("No clear story in notes (early research only)", "Triage manually")

# 4 action groups
GROUP = {
    "Built / Activated": "A. Done (won/live)",
    "Secured (PAL/ROE/EMA signed)": "A. Done (won/live)",
    "Existing Bulk / incumbent (competitor locked)": "B. Dead/blocked",
    "Blocked — moratorium / exclusivity": "B. Dead/blocked",
    "Owner denial / declined / halted": "B. Dead/blocked",
    "Disqualified / not a target": "B. Dead/blocked",
    "Low return / not viable": "B. Dead/blocked",
    "Hand off to Markets/local team": "C. Route/re-verify",
    "Sold / ownership change": "C. Route/re-verify",
    "Active outreach (was being worked)": "D. Workable (orphaned)",
    "Unresponsive / no contact": "D. Workable (orphaned)",
    "Construction / build phase": "D. Workable (orphaned)",
    NO_STORY[0]: "D. Workable (orphaned)",
}

# note story -> suggested Substatus__c ("Pursuit Status"); "" = no clean match
SUGGESTED_PURSUIT_STATUS = {
    "Existing Bulk / incumbent (competitor locked)": "Incumbent EMA",
    "Owner denial / declined / halted": "Chose Another Provider",
    "Low return / not viable": "Budget Not Approved / Business Case",
    "Unresponsive / no contact": "Owner Unresponsive",
    "Disqualified / not a target": "No Marketing/Bulk Needed",
}

# valid Substatus__c picklist values (for workbook dropdown / validation)
PURSUIT_STATUS_VALUES = [
    "Owner Unresponsive",
    "Budget Not Approved / Business Case",
    "Chose Another Provider",
    "Bulk/Marketing Rejected",
    "ISP or Funding Needed",
    "Incumbent EMA",
    "No Marketing/Bulk Needed",
]


def categorize(blob: str) -> tuple[str, str]:
    """Return (note_story_label, action) for a blob of note text."""
    low = (blob or "").lower()
    for label, action, pat in RULES:
        if re.search(pat, low):
            return label, action
    return NO_STORY


def classify_opp(note_bodies, description=""):
    """Classify one opp from its cleaned note bodies (+ optional description).

    Returns dict: story, action, group, suggested_pursuit_status, snippet.
    `snippet` is the first note body that triggered the chosen rule (evidence),
    else the newest body.
    """
    bodies = [b for b in (note_bodies or []) if b]
    blob = " || ".join(bodies)
    story, action = categorize(blob + " " + (description or ""))
    pat = next((p for (lbl, a, p) in RULES if lbl == story), None)
    snippet = ""
    if pat:
        for b in bodies:
            if re.search(pat, b.lower()):
                snippet = b
                break
    if not snippet and bodies:
        snippet = bodies[0]
    return {
        "story": story,
        "action": action,
        "group": GROUP.get(story, "?"),
        "suggested_pursuit_status": SUGGESTED_PURSUIT_STATUS.get(story, ""),
        "snippet": re.sub(r"\s+", " ", snippet).strip(),
    }
