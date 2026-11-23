param(
 [Parameter(Mandatory=$true)][ValidateSet('arknights','gf2','endfield')][string]$Game,
 [Parameter(Mandatory=$true)][string]$Receipt,
 [string]$Python='python',
 [ValidateSet('mumu','pc')][string]$Transport='mumu',
 [switch]$Execute
)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if($Game -eq 'arknights' -and $Transport -ne 'mumu'){
 throw 'Arknights supports only the MuMu transport.'
}
if($Game -ne 'arknights' -and $Transport -ne 'pc'){
 throw "Use python scripts/mumu_daily.py status --game $Game for supervised guest cleanup. Only the explicit -Transport pc route inspects or closes Windows clients."
}
$r=Get-Content -LiteralPath $Receipt -Raw|ConvertFrom-Json
$ok=if($Game -eq 'gf2'){$r.verified -eq $true}else{$r.daily_reward_verified -eq $true}
if($Game -eq 'arknights' -and $r.schema -eq 2){
 if(-not $ok){throw 'Daily rewards not visually verified; do not close.'}
 $verify = & $Python (Join-Path $root 'ark_operations_v2.py') --verify-complete --summary $Receipt
 if($LASTEXITCODE -ne 0){throw 'Schema2 completion evidence rejected; do not close.'}
 $verdict=$verify|ConvertFrom-Json
 if($verdict.verified_complete -ne $true){throw 'Missing schema2 verification verdict.'}
} elseif($Game -ne 'endfield' -and (-not $ok -or @($r.tasks|Where-Object {$_.status -ne 'maa_completed'}).Count)){
 throw 'Receipt is not verified complete; do not close.'
}
$verified = & $Python (Join-Path $root 'verify_completion.py') --game $Game --receipt $Receipt
if($LASTEXITCODE -ne 0){throw ('Full-scope verification blocked cleanup: '+$verified)}
$bound=$verified|ConvertFrom-Json
$paths=$bound.paths
$running=Get-CimInstance Win32_Process
. (Join-Path $root 'game-worker-guard.ps1')
$workers=@($running|Where-Object {Test-DailyGameWorker -ProcessName $_.Name -CommandLine $_.CommandLine -ProjectRoot $root})
if($workers.Count){throw 'Automation worker still running; do not close.'}
if($paths.agent -and @($running|Where-Object {$_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($paths.agent)}).Count){
 throw 'GF2 official agent still running.'
}
$path=$paths.game
$maa=$paths.maa
$expectedNames=@([IO.Path]::GetFileName($maa))
if($path){$expectedNames+= [IO.Path]::GetFileName($path)}
if(@($running|Where-Object {$_.Name -in $expectedNames -and -not $_.ExecutablePath}).Count){
 throw 'Cannot verify target process path.'
}
$targets=@($running|Where-Object {$_.ExecutablePath -in @($path,$maa) -and $_.ExecutablePath})
if($Game -eq 'endfield' -and @($targets|Where-Object {$_.ExecutablePath -eq $path}).Count){
 throw 'Endfield is still running; use endfield_close.py first and inspect the official close result.'
}
if(-not $Execute){
 [PSCustomObject]@{mode='plan';game=$Game;targets=@($targets.ProcessId)}|ConvertTo-Json
 return
}
if(Test-Path -LiteralPath (Join-Path $root 'STOP')){throw 'STOP exists; inspect before cleanup.'}
if($Game -eq 'arknights'){
 $adb=$paths.adb
 $vm = & $paths.mumu_cli info -v $paths.vm_index | ConvertFrom-Json
 if($LASTEXITCODE -ne 0){throw 'Cannot verify emulator instance'}
 if($vm.is_android_started){
  $actualSerial=[string]$vm.adb_host_ip+':'+[string]$vm.adb_port
  if($actualSerial -ne $paths.serial){throw 'ADB serial changed; refusing another device'}
  & $adb connect $paths.serial | Out-Null
  if($LASTEXITCODE -ne 0){throw 'ADB connection failed'}
  & $adb -s $paths.serial shell am force-stop com.hypergryph.arknights
  if($LASTEXITCODE -ne 0){throw 'ADB stop failed'}
  $pidText=& $adb -s $paths.serial shell pidof com.hypergryph.arknights
  if($pidText){throw 'Arknights still running'}
 }
}
foreach($item in $targets){
 $p=Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
 if(-not $p){continue}
 if($p.Path -ne $item.ExecutablePath){throw 'Process identity changed; do not close'}
 if(-not $p.CloseMainWindow()){throw "Cannot gracefully close PID $($p.Id); inspect."}
 if(-not $p.WaitForExit(8000)){throw "Close pending for PID $($p.Id); inspect dialog."}
}
$after=Get-CimInstance Win32_Process
if(@($after|Where-Object {($_.ExecutablePath -in @($path,$maa) -and $_.ExecutablePath) -or ($_.Name -in $expectedNames -and -not $_.ExecutablePath)}).Count){
 throw 'Expected game or MAA still present; cleanup not verified.'
}
[PSCustomObject]@{game=$Game;day=$bound.day;closed=$true;game_closed=$true;maa_closed=$true;receipt=$Receipt;at=(Get-Date).ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $root "cleanup-$Game.json") -Encoding utf8
