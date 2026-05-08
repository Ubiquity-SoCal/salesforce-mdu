[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)  # 0 = MailItem

$mail.To = "taylor@ubiquitygp.com"
$mail.Subject = "3 quick questions before Salesforce cutover"
$mail.BodyFormat = 2  # HTML
$mail.Display()  # open first so Outlook inserts the default signature

$existingHtml = $mail.HTMLBody

$bodyContent = @"
<div style="font-family: Calibri, sans-serif; font-size: 11pt; color: #1f1f1f;">
<p>Hi Taylor,</p>

<p>Three records from the Monday migration need your call before Monday&rsquo;s Salesforce cutover. All three are duplicate-name collisions I don&rsquo;t want to guess on:</p>

<ol>
<li><b>Omaha Boyd Street.</b> Monday has three records (6314 Boyd, 6518 Boyd, 6303 Taylor Circle) all tagged with the same &ldquo;Boyd Street Apartments&rdquo; agreement. One complex under a single PAL, or three separate opportunities sharing a bulk agreement?</li>

<li><b>Mercy Housing California.</b> Monday has its own record, but Salesforce has Cantebria Senior Homes with agreement name <code>Encinitas_MDU_Mercy Housing California</code>. Separate opportunity, or already covered by Cantebria?</li>

<li><b>1810 N 8th Apartments (Colt RE)</b>, currently Under Contract in Monday. Salesforce has <code>1807 Mulford Apartments_Colt RE</code> with agreement name <code>Killeen_MDU_1807 Mulford &amp; 1810 N 8th St</code> covering both addresses. Split into two opportunities or keep consolidated under the Mulford record?</li>
</ol>

<p>Once I have your answers I&rsquo;ll finalize these in Salesforce so nothing is lost in the handoff.</p>

<p>Thanks,<br/>
Cass</p>
</div>
"@

# Insert content before the default signature
if ($existingHtml -match "(?is)(<body[^>]*>)(.*)") {
    $openTag = $matches[1]
    $newHtml = $existingHtml -replace "(?is)<body[^>]*>", "$openTag$bodyContent"
    $mail.HTMLBody = $newHtml
} else {
    $mail.HTMLBody = $bodyContent + $existingHtml
}

Write-Host "Draft created and opened in Outlook for taylor@ubiquitygp.com"
