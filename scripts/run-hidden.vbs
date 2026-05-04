' Wrapper that launches auto-refresh.bat with NO visible window.
' The scheduled task points wscript.exe -> this .vbs -> auto-refresh.bat
' which avoids the black cmd window popping up every hour.
'
' Self-logs to logs\vbs-debug.log so we can verify the wrapper itself ran
' even if the .bat fails to start.

Option Explicit

Dim FSO, Shell, ScriptDir, BatPath, LogPath, LogFile, ExitCode

Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BatPath = ScriptDir & "\auto-refresh.bat"
LogPath = FSO.GetParentFolderName(ScriptDir) & "\logs\vbs-debug.log"

' Make sure the logs folder exists
If Not FSO.FolderExists(FSO.GetParentFolderName(LogPath)) Then
    FSO.CreateFolder(FSO.GetParentFolderName(LogPath))
End If

' Open the debug log in append mode (8) and create if missing (True)
Set LogFile = FSO.OpenTextFile(LogPath, 8, True)
LogFile.WriteLine "=== " & Now & " vbs wrapper started ==="
LogFile.WriteLine "ScriptFullName: " & WScript.ScriptFullName
LogFile.WriteLine "ScriptDir:      " & ScriptDir
LogFile.WriteLine "BatPath:        " & BatPath
LogFile.WriteLine "BatPath exists: " & FSO.FileExists(BatPath)

Set Shell = CreateObject("WScript.Shell")

On Error Resume Next
' Wrap the path in quotes (Chr(34) = "). Using cmd /c to be explicit about
' invoking the bat — more reliable across paths with spaces/commas.
ExitCode = Shell.Run("cmd /c """ & BatPath & """", 0, True)
If Err.Number <> 0 Then
    LogFile.WriteLine "ERROR running bat: " & Err.Description & " (#" & Err.Number & ")"
Else
    LogFile.WriteLine "Bat exit code: " & ExitCode
End If
On Error Goto 0

LogFile.WriteLine "=== " & Now & " vbs wrapper done ==="
LogFile.WriteLine ""
LogFile.Close
