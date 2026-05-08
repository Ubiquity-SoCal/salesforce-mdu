[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$subjectDate = Get-Date -Format "M/d/yyyy"

$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.Subject = "New SMB ROE Sites Assigned to Fiber First - $subjectDate"
$mail.BodyFormat = 2  # HTML
$mail.Display()  # open first so Outlook inserts default signature

$bodyContent = @"
<div style="font-family: Calibri, sans-serif; font-size: 11pt; color: #333;">
<p>Hi team,</p>

<p>Ten additional properties have been added to the <b>SMB ROE - FF Sales</b> list view in Salesforce for Fiber First to work. All sites below have been flagged with <b>FF_Sales_Project = SMB ROE</b> on the Property Location record, with assignment date, build effort, and RE notes filled in.</p>

<p><b>Salesforce List View:</b> <a href="https://fun-power-747.lightning.force.com/lightning/o/Property_Location__c/list?filterName=FF_SMB_ROE">FF Sales - SMB ROE (Property Locations)</a></p>

<h3 style="color:#1f4e79; margin-bottom:4px;">Arizona (5) &mdash; RE: Tanya Friese</h3>
<p style="margin-top:4px;"><i>Common pattern: owners are open to ROE but want a tenant service order first.</i></p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; font-family:Calibri, sans-serif; font-size:10pt;">
<tr style="background:#1f4e79; color:white;">
  <th>Address</th><th>Assigned</th><th>Build Effort</th><th>Notes</th>
</tr>
<tr>
  <td>745 W Baseline Rd, Mesa AZ 85210</td><td>4/14</td><td>Hard</td>
  <td>Won't sign ROE without a service order. Existing Saia ROE at 4210 E Main (unit only). Owner: Gabriel Saia, Saia Family Trust, 480-220-2030, gabe@eires.com.</td>
</tr>
<tr>
  <td>535 E Southern Ave, Mesa AZ 85204</td><td>4/8</td><td>Hard</td>
  <td>Olive Tree Plaza. Won't sign ROE until tenant interest. Leasing (Cobe): Dave Collins 480-415-0055. Owner: Olive Tree Plaza Properties LLC c/o John Scantland 310-470-4226.</td>
</tr>
<tr>
  <td>1731 W Baseline Rd, Mesa AZ 85202</td><td>4/15</td><td>Hard</td>
  <td>Owner open to ROE if a tenant orders services. Owner: Sam Moses, Moses Investments, 480-296-8980, sam.moses@cox.net. Leasing: Louis Moses 480-628-2405.</td>
</tr>
<tr>
  <td>645 S Country Club Dr, Mesa AZ 85210</td><td>4/2</td><td>Medium</td>
  <td>Prefers to sign ROE after a tenant orders; willing to review form. Owner: Stuart Shoen, Mesa Commercial Partners, 602-363-0532, staurt@sacholdings.com. Also owns 715 S Country Club.</td>
</tr>
<tr>
  <td>1136 E Harmony Ave, Mesa AZ 85204</td><td>4/2</td><td>Medium</td>
  <td>Stapley Executive Center. Owner wants to hold ROE until a tenant orders. Owner: Ramesh Narasimhan, Harmony Mesa Properties, 602-629-0206, ram@ncseng.com.</td>
</tr>
</table>

<h3 style="color:#1f4e79; margin-bottom:4px;">Texas (5) &mdash; RE: Rosemarie Shortino</h3>
<p style="margin-top:4px;"><i>All five are Westwood Financial managed. Direction from RE: deal with Kathy Holverson directly. She is OK with FF reaching out to tenants to gauge interest. Owner wants a $2,500/site door fee plus at least 2 service orders per building before moving forward.</i></p>
<p><b>Primary contact for all TX sites:</b> Kathy Holverson, Senior Property Manager, Westwood Financial &mdash; <a href="mailto:kholverson@westfin.com">kholverson@westfin.com</a> &middot; 972-284-0924</p>

<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; font-family:Calibri, sans-serif; font-size:10pt;">
<tr style="background:#1f4e79; color:white;">
  <th>Address</th><th>Assigned</th><th>Build Effort</th><th>Notes</th>
</tr>
<tr>
  <td>6900 Denton Hwy, Watauga TX 76148</td><td>4/15</td><td>Hard</td>
  <td>Contact Kathy Holverson (Westwood Financial). OK with FF contacting tenants. $2,500/site door fee + 2+ orders/bldg required.</td>
</tr>
<tr>
  <td>8245 Precinct Line Rd, N Richland Hills TX 76182</td><td>4/15</td><td>Hard</td>
  <td>Same Westwood direction. Owner on file: Central Valley Real Estate / Turbo Restaurant Mgmt (Grant Alvernaz 925-270-6213).</td>
</tr>
<tr>
  <td>8420 Denton Hwy, Watauga TX 76148</td><td>4/15</td><td>Hard</td>
  <td>Contact Kathy Holverson. $2,500/site door fee + 2+ orders/bldg required.</td>
</tr>
<tr>
  <td>8436 Denton Hwy, Watauga TX 76148</td><td>4/15</td><td>Hard</td>
  <td>Contact Kathy Holverson. $2,500/site door fee + 2+ orders/bldg required.</td>
</tr>
<tr>
  <td>6700 Denton Fwy, Watauga TX 76148</td><td>4/15</td><td>Hard</td>
  <td>Contact Kathy Holverson. $2,500/site door fee + 2+ orders/bldg required. Owner on file: Invmax LLC, 817-632-6200.</td>
</tr>
</table>

<p style="margin-top:16px;">Full RE notes, contact history, and owner/management details live on each Property Location record in Salesforce. Let me know if you need anything else.</p>

<p>Thanks,</p>
</div>
"@

$mail.HTMLBody = $bodyContent + $mail.HTMLBody

Write-Host "Draft created. Add recipients in Outlook and send." -ForegroundColor Green
