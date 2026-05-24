' tray/start_tray_hidden.vbs
' Skryté spuštění tray aplikace pro Správu vozidel
' Tento VBS skript spustí tray aplikaci bez viditelného okna

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Zjistit složku, kde se tento VBS skript nachází
scriptPath = WScript.ScriptFullName
scriptFolder = fso.GetParentFolderName(scriptPath)
projectRoot = fso.GetParentFolderName(scriptFolder)

' Cesta k tray aplikaci
trayScript = fso.BuildPath(scriptFolder, "tray_app.py")

' Zkontrolovat, zda existuje venv
pythonExe = "python"
venvPython = fso.BuildPath(projectRoot, "venv\Scripts\python.exe")
If fso.FileExists(venvPython) Then
    pythonExe = venvPython
End If

' Spustit Python skript s skrytým oknem
cmd = pythonExe & " """ & trayScript & """"

' 0 = hidden window, False = nečekat na ukončení procesu
shell.Run cmd, 0, False

