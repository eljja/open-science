<#
open-science 오프라인 설치 (Windows, 인터넷·npm 불필요)

  .\install_offline.ps1 -Project D:\research\myproj                       # OpenCode 2
  .\install_offline.ps1 -Project D:\research\myproj -Target opencode-v1   # OpenCode 1.x
  옵션: -Python C:\Python311\python.exe  -InstallDir D:\tools\open-science  -AddToPath  -SetGlobalNoUpdate  -SkipVerify

필요한 것: 번들과 같은 버전의 Python(manifest.json 의 python, 기본 3.11). 관리자 권한 불필요.
#>
param(
  [Parameter(Mandatory = $true)][string]$Project,
  [ValidateSet("opencode", "opencode-v1")][string]$Target = "opencode",
  [string]$Python = "",
  [string]$InstallDir = "$env:LOCALAPPDATA\open-science",
  [switch]$AddToPath,
  [switch]$SetGlobalNoUpdate,
  [switch]$SkipVerify
)
$ErrorActionPreference = "Stop"
# PowerShell 5.1: Stop 상태에서 네이티브 명령의 stderr 출력이 예외로 바뀌는 문제 회피 — 종료 코드로만 판정
function Invoke-Native {
  param([string]$Exe, [string[]]$ArgList, [switch]$Quiet)
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try {
    if ($Quiet) { & $Exe @ArgList 2>&1 | Out-Null }
    else { & $Exe @ArgList 2>&1 | ForEach-Object { Write-Host "  $_" } }
    return $LASTEXITCODE
  } finally { $ErrorActionPreference = $old }
}
$B = $PSScriptRoot
$man = Get-Content -Raw -Encoding UTF8 "$B\manifest.json" | ConvertFrom-Json
$track = if ($Target -eq "opencode") { "opencode2" } else { "opencode1" }

Write-Host "[1/6] 체크섬 검증"
if (-not $SkipVerify) {
  $bad = 0
  foreach ($line in Get-Content -Encoding UTF8 "$B\SHA256SUMS.txt") {
    if ($line -match '^([0-9a-f]{64})\s+(.+)$') {
      $f = Join-Path $B ($Matches[2] -replace '/', '\')
      $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLower()
      if ($h -ne $Matches[1]) { Write-Warning "불일치: $($Matches[2])"; $bad++ }
    }
  }
  if ($bad -gt 0) { throw "체크섬 불일치 $bad 개 — 번들이 손상되었거나 변경됨" }
  Write-Host "  OK"
}

Write-Host "[2/6] Python 확인 (번들 wheel: Python $($man.python))"
if (-not $Python) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = (& py "-$($man.python)" -c "import sys; print(sys.executable)" 2>$null)
  }
  if (-not $Python) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }
}
if (-not $Python) { throw "Python $($man.python) 을 찾지 못함. -Python 으로 경로를 지정하세요." }
$pv = (& $Python -c "import sys; print('%d.%d' % sys.version_info[:2])")
if ($pv -ne $man.python) { Write-Warning "Python $pv 감지 — 번들 wheel 은 $($man.python) 용입니다. 설치가 실패하면 같은 버전으로 번들을 다시 만드세요." }
Write-Host "  $Python ($pv)"

Write-Host "[3/6] 가상환경 + wheel 오프라인 설치 → $InstallDir\venv"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$VPY = "$InstallDir\venv\Scripts\python.exe"
if (-not (Test-Path $VPY)) {
  $null = Invoke-Native $Python @("-m","venv","$InstallDir\venv")
  if (-not (Test-Path $VPY)) { $null = Invoke-Native $Python @("-m","venv","--without-pip","$InstallDir\venv") }
}
if (-not (Test-Path $VPY)) { throw "가상환경 생성 실패: $InstallDir\venv" }
# ensurepip 가 없는 Python(임베디드/일부 배포판) 대비: 번들의 pip wheel 로 부트스트랩
if ((Invoke-Native $VPY @("-m","pip","--version") -Quiet) -ne 0) {
  $pipWhl = Get-ChildItem "$B\wheels" -Filter "pip-*.whl" | Select-Object -First 1
  if (-not $pipWhl) { throw "pip 가 없고 번들에 pip wheel 도 없습니다." }
  Write-Host "  pip 부트스트랩: $($pipWhl.Name)"
  if ((Invoke-Native $VPY @("$($pipWhl.FullName)\pip","install","--no-index","--find-links","$B\wheels","pip")) -ne 0) { throw "pip 부트스트랩 실패" }
}
if ((Invoke-Native $VPY @("-m","pip","install","--no-index","--find-links","$B\wheels","--upgrade","sciharness")) -ne 0) { throw "pip 오프라인 설치 실패" }
if ((Invoke-Native $VPY @("-c","import sciharness, mcp, jupyter_client, matplotlib; print('sciharness', sciharness.__version__)")) -ne 0) { throw "패키지 import 확인 실패" }

Write-Host "[4/6] OpenCode 바이너리 배치 ($track)"
$srcBin = "$B\bin\$track"
if (-not (Test-Path $srcBin)) { throw "번들에 $track 바이너리가 없습니다(build_bundle.py --opencode 옵션 확인)." }
New-Item -ItemType Directory -Force -Path "$InstallDir\bin\$track" | Out-Null
Copy-Item -Force "$srcBin\*" "$InstallDir\bin\$track\"
$OC = Get-ChildItem "$InstallDir\bin\$track" -Filter "opencode*" | Select-Object -First 1
Write-Host "  $($OC.FullName)"

Write-Host "[5/6] 키트 설치 → $Project"
Copy-Item -Recurse -Force "$B\kit" "$InstallDir\" 
New-Item -ItemType Directory -Force -Path $Project | Out-Null
if (Test-Path "$B\models\models.json") {
  New-Item -ItemType Directory -Force -Path "$Project\.science" | Out-Null
  Copy-Item -Force "$B\models\models.json" "$Project\.science\models.json"
}
if ((Invoke-Native $VPY @("$InstallDir\kit\tools\install.py","--target",$Target,"--project",$Project,"--python",$VPY,"--offline")) -ne 0) { throw "install.py 실패" }
# OpenCode 1.x: 시작 시 npm 으로 받는 @opencode-ai/plugin 을 번들 사본으로 미리 배치(폐쇄망 지연/실패 방지)
$depz = "$B\v1-deps\opencode-plugin-deps.zip"
if ($Target -eq "opencode-v1" -and (Test-Path $depz)) {
  $cfgHome = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $HOME ".config" }
  foreach ($d in @("$Project\.opencode", (Join-Path $cfgHome "opencode"))) {
    if (Test-Path "$d\node_modules\@opencode-ai\plugin") { Write-Host "  V1 플러그인 의존성 이미 있음: $d"; continue }
    if (Test-Path "$d\package.json") { Write-Warning "$d\package.json 이 이미 있어 덮어쓰지 않음 — 폐쇄망에서는 $depz 를 수동으로 병합하세요."; continue }
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    Expand-Archive -Force -Path $depz -DestinationPath $d
    Write-Host "  V1 플러그인 의존성 배치: $d"
  }
}
$launcher = "$Project\.opencode\opencode-offline.ps1"
@"
# open-science 오프라인 실행기 (install_offline.ps1 생성)
. "`$PSScriptRoot\sciharness.env.ps1"
Set-Location "`$PSScriptRoot\.."
& "$($OC.FullName)" @args
"@ | Set-Content -Encoding UTF8 $launcher

Write-Host "[6/6] 마무리"
if ($AddToPath) {
  $up = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($up -notlike "*$InstallDir\bin\$track*") {
    [Environment]::SetEnvironmentVariable("Path", "$up;$InstallDir\bin\$track", "User")
    Write-Host "  사용자 PATH 에 추가: $InstallDir\bin\$track (새 터미널부터 적용)"
  }
}
if ($Target -eq "opencode") {
  $g = "$env:USERPROFILE\.config\opencode\opencode.jsonc"
  if ($SetGlobalNoUpdate -and -not (Test-Path $g)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $g) | Out-Null
    '{ "update": "disable" }' | Set-Content -Encoding UTF8 $g
    Write-Host "  전역 설정 생성: $g (update=disable)"
  } elseif (-not (Test-Path $g) -or -not (Select-String -Quiet -Path $g -Pattern '"update"')) {
    Write-Host "  참고: OpenCode 2 업데이트 확인을 끄려면 전역 설정($g)에 `"update`": `"disable`" 추가 (또는 -SetGlobalNoUpdate)"
  }
}
Write-Host ""
Write-Host "완료. 실행:  & '$launcher'"
Write-Host "모델 연결: 사내 OpenAI 호환 LLM 은 OFFLINE_README.md 의 제공자 설정 예시를 opencode 설정에 추가하세요."
