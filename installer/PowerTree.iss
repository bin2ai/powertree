; Inno Setup script for PowerTree (compile with ISCC when Inno Setup 6 is
; installed; build_installer.ps1 picks it up automatically).
;   iscc installer\PowerTree.iss /DAppDist=dist\PowerTree

#ifndef AppDist
#define AppDist "..\dist\PowerTree"
#endif

[Setup]
AppName=PowerTree
AppVersion=0.5
AppPublisher=PowerTree
DefaultDirName={autopf}\PowerTree
DefaultGroupName=PowerTree
UninstallDisplayIcon={app}\PowerTree.exe
OutputBaseFilename=PowerTree-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Files]
Source: "{#AppDist}\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\PowerTree"; Filename: "{app}\PowerTree.exe"
Name: "{autodesktop}\PowerTree"; Filename: "{app}\PowerTree.exe"

[Registry]
; associate .ptproj with PowerTree
Root: HKA; Subkey: "Software\Classes\.ptproj"; ValueType: string; ValueData: "PowerTreeProject"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PowerTreeProject"; ValueType: string; ValueData: "PowerTree Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PowerTreeProject\shell\open\command"; ValueType: string; ValueData: """{app}\PowerTree.exe"" ""%1"""

[Run]
Filename: "{app}\PowerTree.exe"; Description: "Launch PowerTree"; Flags: postinstall nowait skipifsilent
