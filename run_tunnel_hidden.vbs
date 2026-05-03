Set oShell = CreateObject("WScript.Shell")
oShell.Run "ngrok start --config ""D:\stock-prediction\ngrok.yml"" stocksight", 0, False
