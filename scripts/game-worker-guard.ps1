# Pure command-line classification only. Dot-sourcing does not inspect/stop processes.

function Test-DailyGameWorker {

 param([string]$ProcessName,[string]$CommandLine,[string]$ProjectRoot=$PSScriptRoot)

 if($ProcessName -notmatch '^python(w)?\.exe$' -or [string]::IsNullOrWhiteSpace($CommandLine)){return $false}

 # Only a directly invoked script counts; python -m tests and python -c/document text do not.

 $tokens=@([regex]::Matches($CommandLine,'"[^"]*"|\S+') | ForEach-Object {$_.Value.Trim('"')})

 if($tokens.Count -lt 2){return $false}

 $i=1

 while($i -lt $tokens.Count -and $tokens[$i] -in @('-u','-B','-I','-E','-s','-S','-O','-OO')){$i++}

 if($i -ge $tokens.Count -or $tokens[$i].StartsWith('-')){return $false}

 $script=$tokens[$i].Replace('/','\');$name=[IO.Path]::GetFileName($script).ToLowerInvariant()

 if([IO.Path]::IsPathRooted($script)){

  if([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($script)).TrimEnd('\') -ine [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')){return $false}

 } elseif($script -match '\\' -and $script -notmatch '^\.\\[^\\]+$' -and $script -notmatch '^daily-automation\\[^\\]+$'){return $false}

 $args=@($tokens | Select-Object -Skip ($i+1))

 if($name -in @('gf2_input_once.py','endfield_continue_once.py','endfield_free_kills_once.py','reopen_launcher.py','restore_launcher.py','start_endfield_native.py')){return $true}

 if($name -eq 'daily_pipeline.py'){return ($args -contains 'run' -and $args -contains '--execute')}

 $gated=@('runner.py','ark_operations.py','ark_operations_v2.py','ark_accelerated.py','ark_supplemental.py','gf2_safe.py','gf2_supplemental.py','gf2_breakthrough.py','endfield_safe.py','endfield_regional.py','endfield_stock.py','endfield_bootstrap.py','endfield_close.py','prepare_game.py')

 if($name -notin $gated){return $false}

 if($args -contains '--execute'){return $true}

 return ($name -in @('runner.py','ark_operations.py','ark_operations_v2.py','ark_accelerated.py') -and $args -contains '--worker')

}
