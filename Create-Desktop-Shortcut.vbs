Option Explicit

Dim fso, shell, scriptDir, exePath, desktopPath, shortcutPath, answer, shortcut
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = fso.BuildPath(scriptDir, "PC-Builder.exe")

If Not fso.FileExists(exePath) Then
    MsgBox "Не найден PC-Builder.exe рядом со скриптом.", vbExclamation, "PC-Builder"
    WScript.Quit 1
End If

desktopPath = shell.SpecialFolders("Desktop")
shortcutPath = fso.BuildPath(desktopPath, "PC-Builder.lnk")
If fso.FileExists(shortcutPath) Then
    answer = MsgBox("Ярлык PC-Builder уже существует. Заменить его?", vbQuestion + vbYesNo, "PC-Builder")
    If answer <> vbYes Then WScript.Quit 0
End If

Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = exePath
shortcut.WorkingDirectory = scriptDir
shortcut.Description = "Запуск PC-Builder"
shortcut.Save
MsgBox "Ярлык создан на рабочем столе.", vbInformation, "PC-Builder"
