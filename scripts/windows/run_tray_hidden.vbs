        ' scripts/windows/run_tray_hidden.vbs
' Skryté spuštění tray aplikace pro TOOZHUB2
' Tento VBS skript spustí PowerShell skript start_tray.ps1 bez viditelného okna

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Zjistit složku, kde se tento VBS skript nachází
scriptPath = WScript.ScriptFullName
scriptFolder = fso.GetParentFolderName(scriptPath)

' Cesta k start_tray.ps1 (ve stejné složce jako tento VBS)
trayScript = fso.BuildPath(scriptFolder, "start_tray.ps1")

' Spustit PowerShell skript s ExecutionPolicy Bypass a skrytým oknem
cmd = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & trayScript & """"

' 0 = hidden window, False = nečekat na ukončení procesu
shell.Run cmd, 0, False


