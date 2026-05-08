[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$msgPath = "C:\Users\cass\OneDrive - Ubiquity Management\Desktop\RE_ Salesforce Requested Revisions _ Points to discuss with BDMs 3_30.msg"

$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")

# Open the original .msg so we can reply and preserve the thread
$original = $namespace.OpenSharedItem($msgPath)
$reply = $original.Reply()
$reply.BodyFormat = 2  # HTML
$reply.Display()       # show first so Outlook inserts Cass's default signature

# Grab existing HTML body (signature + quoted original) then prepend our new content
$existingHtml = $reply.HTMLBody

$bodyContent = @"
<div style="font-family: Calibri, sans-serif; font-size: 11pt; color: #1f1f1f;">
<p>Hey Taylor, updates below.</p>

<p><b>Accounts multi-select:</b> built. On MDU Opps there&rsquo;s now an Accounts related list on the left rail (under Contacts). Tag as many Accounts as you want with an optional Role (Owner, Management Company, Portfolio, Other). Search will pull any tagged Account regardless of role. I backfilled the 109 opps that had data in the old Account / Mgmt Co / Portfolio fields, so nothing is lost.</p>

<p>Also relabeling the standard &ldquo;Account Name&rdquo; to &ldquo;Primary Account&rdquo; so it&rsquo;s clear it&rsquo;s the one that feeds SiteTracker, IronClad, reports etc. Junction is for tagging, Primary Account is the anchor.</p>

<p><b>Closed Won:</b> leaving it. Business uses it so I can&rsquo;t rename globally. MDU folks will hit the error once and learn.</p>

<p><b>On Hold Reason:</b> rule&rsquo;s ready, need your picklist values. Toss me a list when you can.</p>

<p><b>Naming convention:</b> want me to take a first pass or you want to?</p>

<p><b>Living Units icon:</b> gone.</p>

<p>Poke around and let me know if anything feels off.</p>

<p>Thanks,<br/>
Cass</p>
</div>
"@

# Insert our content BEFORE Outlook's signature + quoted thread
# The existing HTML already has signature and quoted thread. Inject our body at the top of <body>
if ($existingHtml -match "(?is)(<body[^>]*>)(.*)") {
    $openTag = $matches[1]
    $rest = $matches[2]
    $newHtml = $existingHtml -replace "(?is)<body[^>]*>", "$openTag$bodyContent"
    $reply.HTMLBody = $newHtml
} else {
    # fallback: just prepend
    $reply.HTMLBody = $bodyContent + $existingHtml
}

Write-Host "Draft created and opened in Outlook."
