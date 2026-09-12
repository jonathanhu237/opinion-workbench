#define MyAppName "舆情工作台"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "OpinionWorkbench"
#define MyAppExeName "OpinionWorkbench.exe"

[Setup]
AppId={{B5B5D4ED-3FB2-4F36-9C67-2D1C6D4E57D2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\OpinionWorkbench
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\windows
OutputBaseFilename=OpinionWorkbench-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
Uninstallable=yes

[Files]
Source: "build\app\OpinionWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
