Set oShell = CreateObject("WScript.Shell")
oShell.Run "D:\stock-prediction\venv\Scripts\pythonw.exe D:\stock-prediction\" & WScript.Arguments(0), 0, False
