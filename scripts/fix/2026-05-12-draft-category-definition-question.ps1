[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)  # 0 = MailItem

$mail.Subject = "Property serviceability check"
$mail.BodyFormat = 2  # HTML
$mail.Display()  # open first so Outlook inserts the default signature

$existingHtml = $mail.HTMLBody

$bodyContent = @"
<div style="font-family: Calibri, sans-serif; font-size: 11pt; color: #1f1f1f;">

<table style="border-collapse: collapse; font-size: 10.5pt;">
  <thead>
    <tr style="background:#f0f0f0;">
      <th style="border:1px solid #999; padding:4px 8px; text-align:left;">#</th>
      <th style="border:1px solid #999; padding:4px 8px; text-align:left;">Property</th>
      <th style="border:1px solid #999; padding:4px 8px; text-align:left;">Address</th>
      <th style="border:1px solid #999; padding:4px 8px; text-align:center;">Result</th>
      <th style="border:1px solid #999; padding:4px 8px; text-align:right;">Distance to fiber</th>
    </tr>
  </thead>
  <tbody>
"@

$rows = @(
    @{ N=1;  Name="Royal Garden Mineral Wells";                       Addr="1500 SE Martin Luther King Jr St, Mineral Wells, TX 76067"; Res="Cat 1"; Dist="164 ft"   },
    @{ N=2;  Name="Pioneer Crossing Mineral Wells";                   Addr="2509 E Hubbard St, Mineral Wells, TX 76067";                Res="Cat 1"; Dist="113 ft"   },
    @{ N=3;  Name="Pioneer Crossing Kountze";                         Addr="860 MLK Court, Kountze, TX 77625";                          Res="Cat 3"; Dist="184 mi"   },
    @{ N=4;  Name="Pioneer Crossing Jasper";                          Addr="1820 S Bowie Street, Jasper, TX 75951";                     Res="Cat 3"; Dist="203 mi"   },
    @{ N=5;  Name="Pioneer Crossing Livingston";                      Addr="1101 N Dogwood Avenue, Livingston, TX 77351";               Res="Cat 3"; Dist="146 mi"   },
    @{ N=6;  Name="Pioneer Crossing Diboll";                          Addr="700 Lumberjack Dr, Diboll, TX 75941";                       Res="Cat 3"; Dist="161 mi"   },
    @{ N=7;  Name="Royal Garden Pioneer Crossing for Seniors Lufkin"; Addr="1202 Old Gobbler's Knob Rd, Lufkin, TX 75904";              Res="Cat 3"; Dist="165 mi"   },
    @{ N=8;  Name="Pioneer Crossing for Families Lufkin";             Addr="1805 John Reddit Drive, Lufkin, TX 75904";                  Res="Cat 3"; Dist="165 mi"   },
    @{ N=9;  Name="Pioneer Crossing Vernon";                          Addr="1916 Stadium Drive, Vernon, TX 76384";                      Res="Cat 3"; Dist="109 mi"   },
    @{ N=10; Name="Pioneer Crossing Burkburnett";                     Addr="1406 Shady Ln, Burkburnett, TX 76354";                      Res="Cat 3"; Dist="73 mi"    },
    @{ N=11; Name="Royal Garden Wichita Falls";                       Addr="4606 Johnson Rd, Wichita Falls, TX 76310";                  Res="Cat 3"; Dist="63 mi"    },
    @{ N=12; Name="Pioneer Crossing Henrietta";                       Addr="255 Fair View Rd, Henrietta, TX 76365";                     Res="Cat 3"; Dist="46 mi"    },
    @{ N=13; Name="Pioneer Crossing Sulphur Springs";                 Addr="668 Gossett Lane, Sulphur Springs, TX 75482";               Res="Cat 3"; Dist="70 mi"    },
    @{ N=14; Name="Reserve at San Marcos";                            Addr="4210 Texas Hwy 123, San Marcos, TX 78666";                  Res="Cat 3"; Dist="55 mi"    },
    @{ N=15; Name="Pioneer Crossing Ingleside";                       Addr="1550 12th St, Ingleside, TX 78362";                         Res="Cat 3"; Dist="185 mi"   }
)

$rowsHtml = ""
foreach ($r in $rows) {
    $resColor = switch ($r.Res) {
        "Cat 1" { "#d8f3dc" }
        "Cat 2" { "#fff3bf" }
        "Cat 3" { "#ffd6d6" }
        default { "#f0f0f0" }
    }
    $rowsHtml += @"
    <tr>
      <td style="border:1px solid #999; padding:4px 8px;">$($r.N)</td>
      <td style="border:1px solid #999; padding:4px 8px;">$($r.Name)</td>
      <td style="border:1px solid #999; padding:4px 8px;">$($r.Addr)</td>
      <td style="border:1px solid #999; padding:4px 8px; text-align:center; background:$resColor;">$($r.Res)</td>
      <td style="border:1px solid #999; padding:4px 8px; text-align:right;">$($r.Dist)</td>
    </tr>
"@
}

$bodyContent += $rowsHtml + @"
  </tbody>
</table>

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

Write-Host "Draft created and opened in Outlook."
