$value = '"' + $env:SystemRoot + '\System32\cmd.exe" /c "%1" %*'
Set-ItemProperty -Path "HKLM:\SOFTWARE\Classes\batfile\shell\open\command" -Name "(Default)" -Value $value
Write-Host "完了: $value"
