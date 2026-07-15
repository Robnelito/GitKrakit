#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "GitKrakit"
#define CompanyName "Robnelito"
#define AppExeName "GitKrakit.exe"

[Setup]
AppId={{68D32EA8-EC39-468D-BAD0-5B10D52BA4B8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#CompanyName}
AppPublisherURL=https://github.com/Robnelito/GitKrakit
AppSupportURL=https://github.com/Robnelito/GitKrakit/issues
DefaultDirName={localappdata}\{#CompanyName}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=GitKrakit-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "..\pyu-data\new\win.exe"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent
