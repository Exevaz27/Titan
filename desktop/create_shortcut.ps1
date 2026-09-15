$baseDir = "C:\Users\Exevaz27\.gemini\antigravity\scratch\asistente-argen-win"
$icoPath = "$baseDir\assets\titan.ico"
$pythonw = "$baseDir\.venv\Scripts\pythonw.exe"

$WshShell = New-Object -ComObject WScript.Shell

# 1. Iniciar_Titan.lnk
$lnk1 = "$baseDir\Iniciar_Titan.lnk"
$s1 = $WshShell.CreateShortcut($lnk1)
$s1.TargetPath = $pythonw
$s1.Arguments = "titan_app.py"
$s1.WorkingDirectory = $baseDir
$s1.IconLocation = "$icoPath,0"
$s1.Description = "Iniciar Titán Asistente Virtual"
$s1.Save()

# 2. Titan.lnk
$lnk2 = "$baseDir\Titan.lnk"
$s2 = $WshShell.CreateShortcut($lnk2)
$s2.TargetPath = $pythonw
$s2.Arguments = "titan_app.py"
$s2.WorkingDirectory = $baseDir
$s2.IconLocation = "$icoPath,0"
$s2.Description = "Titán Asistente Virtual para Windows"
$s2.Save()

Write-Host "[OK] Accesos directos con icono creados:"
Write-Host " - $lnk1"
Write-Host " - $lnk2"
