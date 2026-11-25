$ErrorActionPreference = 'Stop'
$global:relayTestCalls = @()
$global:relayTestValid = $false
$relayTestRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
function Get-ScheduledTask {
    param($TaskName)
    $argsValue = if ($global:relayTestValid) { '"' + (Join-Path $relayTestRoot 'src\satellite_runner.py') + '"' } else { 'unrelated-application' }
    [pscustomobject]@{ TaskName=$TaskName; State='Running'; Actions=[pscustomobject]@{Arguments=$argsValue} }
}
function Stop-ScheduledTask { param($TaskName) $global:relayTestCalls += 'stop-task' }
function Start-ScheduledTask { param($TaskName) $global:relayTestCalls += 'start-task' }
function Get-CimInstance {
    param($ClassName)
    [pscustomobject]@{Name='python.exe';CommandLine=(Join-Path $relayTestRoot 'src\satellite_runner.py');ProcessId=101}
    [pscustomobject]@{Name='python.exe';CommandLine='unrelated.py';ProcessId=102}
}
function Stop-Process { param($Id,$ErrorAction) $global:relayTestCalls += ('stop-process-' + $Id) }
try { & (Join-Path $PSScriptRoot 'restart_relay.ps1') -TaskName Test; throw 'An unrelated task should have been rejected' }
catch { if ($_.Exception.Message -notlike '*does not reference*') { throw } }
if ($global:relayTestCalls.Count -ne 0) { throw 'Unrelated task was changed' }
$global:relayTestValid = $true
& (Join-Path $PSScriptRoot 'restart_relay.ps1') -TaskName Test | Out-Null
if (($global:relayTestCalls -join ',') -ne 'stop-task,stop-process-101,start-task') { throw 'Wrong restart sequence or unrelated process selected' }
Write-Output 'Relay restart identity guard, child selection and explicit task restart passed with mocked OS actions.'

