"""
Deploy the Inside Sales Dashboard Visualforce page to Salesforce.
"""

import json
import requests
from simple_salesforce import Salesforce

SF_USERNAME = "cass1@ubiquitygp.com"
SF_PASSWORD = "Karate88!"
SF_SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"

VF_PAGE_NAME = "InsideSalesDashboard"
VF_PAGE_LABEL = "Inside Sales Dashboard"

VF_MARKUP = r'''<apex:page showHeader="false" sidebar="false" standardStylesheets="false" applyBodyTag="false" docType="html-5.0">
<html xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<head>
    <apex:slds />
    <style>
        body { font-family: 'Salesforce Sans', Arial, sans-serif; background: #f4f6f9; margin: 0; padding: 16px; }
        .metric-card {
            background: #fff; border-radius: 8px; padding: 16px 20px; text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08); flex: 1; min-width: 140px;
        }
        .metric-value { font-size: 1.75rem; font-weight: 700; color: #032d60; margin: 2px 0; }
        .metric-label { font-size: 0.75rem; color: #706e6b; text-transform: uppercase; letter-spacing: 0.5px; }
        .metric-sub { font-size: 0.8rem; color: #0176d3; margin-top: 2px; }
        .metrics-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
        .section { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 16px; }
        .section-title { font-size: 0.9rem; font-weight: 700; color: #032d60; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 2px solid #e5e5e5; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; font-size: 0.7rem; text-transform: uppercase; color: #706e6b; padding: 6px 10px; border-bottom: 2px solid #e5e5e5; }
        td { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; font-size: 0.825rem; color: #181818; }
        tr:hover td { background: #f4f6f9; }
        .amount { color: #2e844a; font-weight: 600; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
        .badge-open { background: #e5f6fd; color: #0176d3; }
        .badge-won { background: #d4edda; color: #2e844a; }
        .badge-lost { background: #fde8e8; color: #c23934; }
        .links-row { display: flex; gap: 8px; flex-wrap: wrap; }
        .link-btn { padding: 8px 16px; background: #fff; border-radius: 6px; text-decoration: none; color: #0176d3; font-weight: 600; font-size: 0.825rem; box-shadow: 0 2px 4px rgba(0,0,0,0.08); transition: background 0.15s; cursor: pointer; }
        .link-btn:hover { background: #e5f6fd; }
        .activity-row { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
        .activity-row:last-child { border-bottom: none; }
        .activity-name { flex: 1; font-size: 0.825rem; color: #181818; }
        .activity-num { width: 60px; text-align: center; font-size: 0.825rem; font-weight: 700; color: #032d60; }
        .activity-change { width: 50px; text-align: right; font-size: 0.75rem; font-weight: 600; }
        .loading { text-align: center; padding: 40px; color: #706e6b; }
        .tab-bar { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 2px solid #e5e5e5; }
        .tab { padding: 10px 20px; font-size: 0.875rem; font-weight: 600; color: #706e6b; cursor: pointer; border-bottom: 3px solid transparent; margin-bottom: -2px; transition: all 0.15s; }
        .tab:hover { color: #032d60; }
        .tab.active { color: #0176d3; border-bottom-color: #0176d3; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .opp-link { color: #0176d3; text-decoration: none; }
        .opp-link:hover { text-decoration: underline; }
        .note-item { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
        .note-item:last-child { border-bottom: none; }
        .note-date { font-size: 0.7rem; color: #706e6b; }
        .note-body { font-size: 0.825rem; color: #181818; margin-top: 2px; }
        .note-subject { font-size: 0.825rem; font-weight: 600; color: #032d60; }
    </style>
</head>
<body>
    <div id="dashboard" class="loading">Loading dashboard...</div>

    <script>
    var sid = '{!$Api.Session_ID}';
    var baseUrl = '{!$Api.Partner_Server_URL_600}';
    var instanceUrl = baseUrl.substring(0, baseUrl.indexOf('/services'));
    var lightningUrl = instanceUrl.replace('.my.salesforce.com', '.lightning.force.com');
    var currentUserId = '{!$User.Id}';
    var currentUserName = '{!$User.FirstName} {!$User.LastName}';

    function query(soql) {
        return fetch(instanceUrl + '/services/data/v59.0/query/?q=' + encodeURIComponent(soql), {
            headers: { 'Authorization': 'Bearer ' + sid, 'Content-Type': 'application/json' }
        }).then(function(r) { return r.json(); });
    }

    function fmt(n) { return '$' + (n || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    function escHtml(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

    var yrFilter = 'CreatedDate >= 2026-01-01T00:00:00Z';
    var yrCloseFilter = 'CloseDate >= 2026-01-01';
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    // Load both tabs in parallel
    Promise.all([
        // === TEAM TAB ===
        // 0: Open opps 2026
        query("SELECT COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE IsClosed = false AND " + yrFilter),
        // 1: Closed Won 2026
        query("SELECT COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE StageName = 'Closed Won' AND " + yrCloseFilter),
        // 2: Tasks completed this week by owner
        query("SELECT Owner.Name, COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND CompletedDateTime >= THIS_WEEK GROUP BY Owner.Name ORDER BY COUNT(Id) DESC"),
        // 3: Tasks completed last week by owner
        query("SELECT Owner.Name, COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND CompletedDateTime >= LAST_WEEK AND CompletedDateTime < THIS_WEEK GROUP BY Owner.Name ORDER BY COUNT(Id) DESC"),
        // 4: Open opps by owner 2026
        query("SELECT Owner.Name, COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE IsClosed = false AND " + yrFilter + " GROUP BY Owner.Name ORDER BY SUM(Amount) DESC"),
        // 5: Recent opps 2026
        query("SELECT Id, Name, StageName, Amount, Owner.Name FROM Opportunity WHERE " + yrFilter + " AND IsClosed = false ORDER BY CreatedDate DESC LIMIT 5"),
        // 6: Opps by month 2026
        query("SELECT CALENDAR_MONTH(CreatedDate) mo, COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE " + yrFilter + " GROUP BY CALENDAR_MONTH(CreatedDate) ORDER BY CALENDAR_MONTH(CreatedDate)"),
        // 7: Closed Won by month 2026
        query("SELECT CALENDAR_MONTH(CloseDate) mo, COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE StageName = 'Closed Won' AND " + yrCloseFilter + " GROUP BY CALENDAR_MONTH(CloseDate) ORDER BY CALENDAR_MONTH(CloseDate)"),
        // 8: All opps 2026 total
        query("SELECT COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE " + yrFilter),

        // === MY PIPELINE TAB ===
        // 9: My open opps
        query("SELECT COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE IsClosed = false AND OwnerId = '" + currentUserId + "' AND " + yrFilter),
        // 10: My closed won
        query("SELECT COUNT(Id) cnt, SUM(Amount) total FROM Opportunity WHERE StageName = 'Closed Won' AND OwnerId = '" + currentUserId + "' AND " + yrCloseFilter),
        // 11: My tasks this week
        query("SELECT COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND OwnerId = '" + currentUserId + "' AND CompletedDateTime >= THIS_WEEK"),
        // 12: My tasks last week
        query("SELECT COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND OwnerId = '" + currentUserId + "' AND CompletedDateTime >= LAST_WEEK AND CompletedDateTime < THIS_WEEK"),
        // 13: My open opps list
        query("SELECT Id, Name, StageName, Amount, CloseDate FROM Opportunity WHERE IsClosed = false AND OwnerId = '" + currentUserId + "' AND " + yrFilter + " ORDER BY CloseDate ASC"),
        // 14: My recent activities
        query("SELECT Id, Subject, Status, ActivityDate, TaskSubtype, Description FROM Task WHERE OwnerId = '" + currentUserId + "' AND Status = 'Completed' ORDER BY CompletedDateTime DESC LIMIT 15"),
        // 15: My open tasks
        query("SELECT Id, Subject, ActivityDate, TaskSubtype FROM Task WHERE OwnerId = '" + currentUserId + "' AND Status = 'Open' ORDER BY ActivityDate ASC"),
    ]).then(function(results) {
        // === TEAM DATA ===
        var openOpps = results[0].records[0];
        var closedWon = results[1].records[0];
        var tasksThisWeek = results[2].records;
        var tasksLastWeek = results[3].records;
        var oppsByOwner = results[4].records;
        var recentOpps = results[5].records;
        var oppsByMonth = results[6].records;
        var wonByMonth = results[7].records;
        var allOpps2026 = results[8].records[0];

        // === MY DATA ===
        var myOpenOpps = results[9].records[0];
        var myClosedWon = results[10].records[0];
        var myTasksThisWeek = results[11].records[0].cnt;
        var myTasksLastWeek = results[12].records[0].cnt;
        var myOppsList = results[13].records;
        var myActivities = results[14].records;
        var myOpenTasks = results[15].records;

        // Team task totals
        var totalThisWeek = 0;
        tasksThisWeek.forEach(function(r) { totalThisWeek += r.cnt; });
        var totalLastWeek = 0;
        tasksLastWeek.forEach(function(r) { totalLastWeek += r.cnt; });
        var lastWeekMap = {};
        tasksLastWeek.forEach(function(r) { lastWeekMap[r.Name] = r.cnt; });
        var wonByMonthMap = {};
        wonByMonth.forEach(function(r) { wonByMonthMap[r.mo] = r; });

        var html = '';

        // === HEADER ===
        html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0;">';
        html += '<div style="font-size:1.1rem;font-weight:700;color:#032d60;">2026 Sales Dashboard</div>';
        html += '<div class="links-row">';
        html += '<a class="link-btn" href="' + lightningUrl + '/lightning/o/Report/home" target="_top">Reports</a>';
        html += '<a class="link-btn" href="' + lightningUrl + '/lightning/o/Dashboard/home" target="_top">Dashboards</a>';
        html += '</div></div>';

        // === TABS ===
        html += '<div class="tab-bar">';
        html += '<div class="tab active" onclick="switchTab(\'team\',this)">Team</div>';
        html += '<div class="tab" onclick="switchTab(\'mine\',this)">My Pipeline</div>';
        html += '</div>';

        // ============================================================
        // TEAM TAB
        // ============================================================
        html += '<div id="tab-team" class="tab-content active">';

        // Metric cards
        html += '<div class="metrics-row">';
        html += '<div class="metric-card"><div class="metric-label">Total Opps (2026)</div><div class="metric-value">' + allOpps2026.cnt + '</div><div class="metric-sub">' + fmt(allOpps2026.total) + '</div></div>';
        html += '<div class="metric-card"><div class="metric-label">Open Pipeline</div><div class="metric-value">' + openOpps.cnt + '</div><div class="metric-sub">' + fmt(openOpps.total) + '</div></div>';
        html += '<div class="metric-card"><div class="metric-label">Closed Won</div><div class="metric-value">' + closedWon.cnt + '</div><div class="metric-sub">' + fmt(closedWon.total) + '</div></div>';
        html += '<div class="metric-card"><div class="metric-label">Activities This Week</div><div class="metric-value">' + totalThisWeek + '</div><div class="metric-sub">Last week: ' + totalLastWeek + '</div></div>';
        html += '</div>';

        // By month
        html += '<div class="section"><div class="section-title">2026 by Month</div><table>';
        html += '<tr><th>Month</th><th style="text-align:right">Created</th><th style="text-align:right">Amount</th><th style="text-align:right">Won</th><th style="text-align:right">Won Amt</th></tr>';
        oppsByMonth.forEach(function(r) {
            var won = wonByMonthMap[r.mo];
            html += '<tr><td>' + months[r.mo - 1] + '</td><td style="text-align:right">' + r.cnt + '</td><td style="text-align:right" class="amount">' + fmt(r.total) + '</td>';
            html += '<td style="text-align:right">' + (won ? won.cnt : 0) + '</td><td style="text-align:right" class="amount">' + fmt(won ? won.total : 0) + '</td></tr>';
        });
        html += '</table></div>';

        // Pipeline by rep
        html += '<div class="section"><div class="section-title">Pipeline by Rep (2026)</div><table>';
        html += '<tr><th>Rep</th><th style="text-align:right">Open Opps</th><th style="text-align:right">Pipeline</th></tr>';
        oppsByOwner.forEach(function(r) {
            html += '<tr><td>' + r.Name + '</td><td style="text-align:right">' + r.cnt + '</td><td style="text-align:right" class="amount">' + fmt(r.total) + '</td></tr>';
        });
        html += '</table></div>';

        // Activity by rep
        html += '<div class="section"><div class="section-title">Activity by Rep</div>';
        html += '<div style="display:flex;padding:0 0 6px 0;border-bottom:2px solid #e5e5e5;margin-bottom:4px;">';
        html += '<div class="activity-name" style="font-size:0.7rem;text-transform:uppercase;color:#706e6b;">Rep</div>';
        html += '<div class="activity-num" style="font-size:0.7rem;text-transform:uppercase;color:#706e6b;">This Week</div>';
        html += '<div class="activity-change" style="font-size:0.7rem;text-transform:uppercase;color:#706e6b;">Last Wk</div>';
        html += '</div>';
        tasksThisWeek.forEach(function(r) {
            var last = lastWeekMap[r.Name] || 0;
            var color = r.cnt > last ? '#2e844a' : (r.cnt < last ? '#c23934' : '#706e6b');
            html += '<div class="activity-row"><div class="activity-name">' + r.Name + '</div>';
            html += '<div class="activity-num">' + r.cnt + '</div>';
            html += '<div class="activity-change" style="color:' + color + '">' + last + '</div></div>';
        });
        html += '</div>';

        // Latest opps
        html += '<div class="section"><div class="section-title">Latest Opportunities (2026)</div><table>';
        html += '<tr><th>Name</th><th>Stage</th><th style="text-align:right">Amount</th><th>Rep</th></tr>';
        recentOpps.forEach(function(r) {
            html += '<tr><td><a class="opp-link" href="' + lightningUrl + '/lightning/r/Opportunity/' + r.Id + '/view" target="_top">' + escHtml(r.Name) + '</a></td>';
            html += '<td><span class="badge badge-open">' + r.StageName + '</span></td><td style="text-align:right" class="amount">' + fmt(r.Amount) + '</td><td>' + r.Owner.Name + '</td></tr>';
        });
        html += '</table></div>';

        html += '</div>'; // end team tab

        // ============================================================
        // MY PIPELINE TAB
        // ============================================================
        html += '<div id="tab-mine" class="tab-content">';

        // My metric cards
        html += '<div class="metrics-row">';
        html += '<div class="metric-card"><div class="metric-label">My Open Opps</div><div class="metric-value">' + myOpenOpps.cnt + '</div><div class="metric-sub">' + fmt(myOpenOpps.total) + '</div></div>';
        html += '<div class="metric-card"><div class="metric-label">My Closed Won</div><div class="metric-value">' + myClosedWon.cnt + '</div><div class="metric-sub">' + fmt(myClosedWon.total) + '</div></div>';
        html += '<div class="metric-card"><div class="metric-label">My Activities This Week</div><div class="metric-value">' + myTasksThisWeek + '</div><div class="metric-sub">Last week: ' + myTasksLastWeek + '</div></div>';
        html += '</div>';

        // My open tasks
        if (myOpenTasks.length > 0) {
            html += '<div class="section"><div class="section-title">Open Tasks</div><table>';
            html += '<tr><th>Task</th><th>Type</th><th>Due Date</th></tr>';
            myOpenTasks.forEach(function(r) {
                var subtype = r.TaskSubtype === 'Call' ? 'Call' : (r.TaskSubtype === 'Email' ? 'Email' : 'Task');
                html += '<tr><td><a class="opp-link" href="' + lightningUrl + '/lightning/r/Task/' + r.Id + '/view" target="_top">' + escHtml(r.Subject) + '</a></td>';
                html += '<td>' + subtype + '</td><td>' + (r.ActivityDate || '-') + '</td></tr>';
            });
            html += '</table></div>';
        }

        // My opportunities
        html += '<div class="section"><div class="section-title">My Opportunities (2026)</div>';
        if (myOppsList.length === 0) {
            html += '<div style="color:#706e6b;padding:12px 0;">No open opportunities</div>';
        } else {
            html += '<table><tr><th>Name</th><th>Stage</th><th style="text-align:right">Amount</th><th>Close Date</th></tr>';
            myOppsList.forEach(function(r) {
                var badgeClass = r.StageName === 'Closed Won' ? 'badge-won' : (r.StageName === 'Closed Lost' ? 'badge-lost' : 'badge-open');
                html += '<tr><td><a class="opp-link" href="' + lightningUrl + '/lightning/r/Opportunity/' + r.Id + '/view" target="_top">' + escHtml(r.Name) + '</a></td>';
                html += '<td><span class="badge ' + badgeClass + '">' + r.StageName + '</span></td>';
                html += '<td style="text-align:right" class="amount">' + fmt(r.Amount) + '</td><td>' + (r.CloseDate || '-') + '</td></tr>';
            });
            html += '</table>';
        }
        html += '</div>';

        // My recent activities
        html += '<div class="section"><div class="section-title">Recent Activities</div>';
        if (myActivities.length === 0) {
            html += '<div style="color:#706e6b;padding:12px 0;">No recent activities</div>';
        } else {
            myActivities.forEach(function(r) {
                var subtype = r.TaskSubtype === 'Call' ? 'Call' : (r.TaskSubtype === 'Email' ? 'Email' : 'Task');
                html += '<div class="note-item">';
                html += '<div style="display:flex;justify-content:space-between;"><div class="note-subject"><a class="opp-link" href="' + lightningUrl + '/lightning/r/Task/' + r.Id + '/view" target="_top">' + escHtml(r.Subject) + '</a></div><div class="note-date">' + subtype + ' - ' + (r.ActivityDate || '') + '</div></div>';
                if (r.Description) {
                    var desc = r.Description.length > 120 ? r.Description.substring(0, 120) + '...' : r.Description;
                    html += '<div class="note-body">' + escHtml(desc) + '</div>';
                }
                html += '</div>';
            });
        }
        html += '</div>';

        html += '</div>'; // end my pipeline tab

        document.getElementById('dashboard').innerHTML = html;
        document.getElementById('dashboard').className = '';
    }).catch(function(err) {
        document.getElementById('dashboard').innerHTML = '<div style="color:red;">Error loading dashboard: ' + err.message + '</div>';
    });

    function switchTab(tabName, el) {
        document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
        document.getElementById('tab-' + tabName).classList.add('active');
        el.classList.add('active');
    }
    </script>
</body>
</html>
</apex:page>'''


def main():
    sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_SECURITY_TOKEN)
    base = f"https://{sf.sf_instance}/services/data/v59.0/tooling"
    headers = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}

    # Check if page already exists
    r = requests.get(
        f"{base}/query/?q=SELECT+Id+FROM+ApexPage+WHERE+Name='{VF_PAGE_NAME}'",
        headers=headers,
    )
    existing = r.json().get("records", [])

    payload = {
        "Name": VF_PAGE_NAME,
        "MasterLabel": VF_PAGE_LABEL,
        "Markup": VF_MARKUP,
        "ApiVersion": 59.0,
    }

    if existing:
        page_id = existing[0]["Id"]
        print(f"Updating existing page {page_id}...")
        r = requests.patch(f"{base}/sobjects/ApexPage/{page_id}", headers=headers, data=json.dumps(payload))
        if r.status_code == 204:
            print("Updated successfully!")
        else:
            print(f"Error: {r.status_code} {r.text}")
    else:
        print("Creating new page...")
        r = requests.post(f"{base}/sobjects/ApexPage", headers=headers, data=json.dumps(payload))
        if r.status_code == 201:
            print(f"Created successfully! ID: {r.json()['id']}")
        else:
            print(f"Error: {r.status_code} {r.text}")

    print()
    print("To add this to your home page:")
    print("  1. Go to Setup > Lightning App Builder")
    print("  2. Edit the Inside Sales home page")
    print("  3. Drag a 'Visualforce' component onto the page")
    print(f"  4. Select '{VF_PAGE_LABEL}' from the dropdown")
    print("  5. Set height to at least 900 pixels")
    print("  6. Save and Activate")


if __name__ == "__main__":
    main()
