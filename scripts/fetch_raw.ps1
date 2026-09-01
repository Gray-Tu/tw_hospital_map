# 下載健保署「健保特約醫事機構」名冊（醫學中心／區域醫院／地區醫院）
# 用法： powershell -File scripts\fetch_raw.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$root\data\raw" | Out-Null

$targets = [ordered]@{
  'medical_center' = 'https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D21001-003'
  'regional'       = 'https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D21002-005'
  'district'       = 'https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D21003-003'
}

foreach ($k in $targets.Keys) {
  $out = "$root\data\raw\nhi_$k.csv"
  Invoke-WebRequest -Uri $targets[$k] -OutFile $out -TimeoutSec 120 -UseBasicParsing
  "{0,-16} {1,9:N0} bytes" -f $k, (Get-Item $out).Length
}
