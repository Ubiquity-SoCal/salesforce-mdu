# Wrapper the Windows Scheduled Task calls. Runs the Python sync health monitor and, if it
# reports an ALERT (exit 2 or 3), raises a Windows toast so Koa sees it without asking - plus a
# msg.exe popup fallback. Healthy runs are silent (status still written to the .txt every time).
#
# Deliberately local, not GitHub Actions: it must survive the scheduler failure it watches for.

$ErrorActionPreference = 'Continue'
$py     = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'sync_health_monitor.py'
$log    = Join-Path $PSScriptRoot 'sync-health-monitor.log'

$output = & $py $script --max-age-hours 36 2>&1 | Out-String
$code   = $LASTEXITCODE
$stamp  = (Get-Date).ToString('yyyy-MM-dd HH:mm')
Add-Content -Path $log -Value "[$stamp] exit=$code $($output.Trim())" -Encoding utf8

if ($code -eq 0) { exit 0 }   # healthy: stay quiet

$title = 'Salesforce Sync ALERT'
$body  = $output.Trim()
if ([string]::IsNullOrWhiteSpace($body)) { $body = "Sync health check failed (exit $code). See $log" }

# --- primary: native Windows Runtime toast (no module dependency) ---
$toastOk = $false
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    $tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
                [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $tmpl.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($tmpl.CreateTextNode($title)) | Out-Null
    $texts.Item(1).AppendChild($tmpl.CreateTextNode($body))  | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($tmpl)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Salesforce Sync Monitor').Show($toast)
    $toastOk = $true
} catch {
    Add-Content -Path $log -Value "[$stamp] toast failed: $($_.Exception.Message)" -Encoding utf8
}

# --- fallback: message box to the console session, guaranteed visible on Win11 Pro ---
if (-not $toastOk) {
    try { & msg.exe * "/TIME:0" "$title`n$body" } catch {}
}

exit $code
