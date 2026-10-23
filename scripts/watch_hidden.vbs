' Launch the Hades II vault watcher without a console window.
' Installed into the user's Startup folder by scripts/install-autostart.cmd.
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "C:\Users\jackc\orca\projects\hades-track"
shell.Run """C:\Users\jackc\orca\projects\hades-track\.venv\Scripts\pythonw.exe"" -m hades_track.cli watch", 0, False
