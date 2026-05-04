' Wrapper that launches auto-refresh.bat with NO visible window.
' The scheduled task points wscript.exe -> this .vbs -> auto-refresh.bat
' which avoids the black cmd window popping up every hour.
'
' Self-logs to %LOCALAPPDATA%\RouteToDelivery\logs\vbs-debug.log so we can
' verify the wrapper itself ran even if the .bat fails to start.

Option Explicit

Dim FSO, Shell, ScriptDir, BatPath, LogDir, LogPath, LogFile, ExitCode

Set FSO = CreateObject("Scripting.FileSystemObject")
Set Shell = CreateObject("WScript.Shell")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BatPath = ScriptDir & "\auto-refresh.bat"

' Logs live OUTSIDE OneDrive (which locks files mid-write).
' %LOCALAPPDATA%\RouteToDelivery\logs is local-only, no sync interference.
LogDir = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\RouteToDelivery\logs"
LogPath = LogDir & "\vbs-debug.log"

' Make sure the logs folder exists (create parent then child if needed)
If Not FSO.FolderExists(Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\RouteToDelivery") Then
    FSO.CreateFolder(Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\RouteToDelivery")
End If
If Not FSO.FolderExists(LogDir) Then
    FSO.CreateFolder(LogDir)
End If

' Open the debug log in append mode (8) and create if missing (True)
Set LogFile = FSO.OpenTextFile(LogPath, 8, True)
LogFile.WriteLine "=== " & Now & " vbs wrapper started ==="
LogFile.WriteLine "ScriptFullName: " & WScript.ScriptFullName
LogFile.WriteLine "ScriptDir:      " & ScriptDir
LogFile.WriteLine "BatPath:        " & BatPath
LogFile.WriteLine "BatPath exists: " & FSO.FileExists(BatPath)
LogFile.WriteLine "LogDir:         " & LogDir

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
