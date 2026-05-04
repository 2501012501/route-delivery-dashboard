' Wrapper that launches auto-refresh.bat with NO visible window.
' The scheduled task points wscript.exe -> this .vbs -> auto-refresh.bat
' which avoids the black cmd window popping up every hour.

Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BatPath = ScriptDir & "\auto-refresh.bat"

Set Shell = CreateObject("WScript.Shell")
' Args: cmd, windowStyle (0 = hidden), waitOnReturn (True = block until done)
Shell.Run Chr(34) & BatPath & Chr(34), 0, True
