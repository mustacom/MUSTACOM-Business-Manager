; ---------------------------------------------------------------------------
; MUSTACOM BUSINESS MANAGER - Inno Setup installer
; Compile with:  iscc /DAppVersion=1.0.0 installer\mustacom.iss
; (build\build_windows.ps1 and the GitHub Actions workflow do this for you)
; Produces:      installer\Output\MUSTACOM-Business-Manager-Setup.exe
; ---------------------------------------------------------------------------
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName      "MUSTACOM Business Manager"
#define AppPublisher "MUSTACOM"
#define AppURL       "www.mustacom.com"
#define AppExeName   "MUSTACOM-Business-Manager.exe"

[Setup]
AppId={{7C4E9F2A-3B8D-4E61-9A2C-MUSTACOM01}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} setup

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; per-user install by default (data lives in %APPDATA%\MUSTACOM\BusinessManager)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=Output
OutputBaseFilename=MUSTACOM-Business-Manager-Setup
SetupIconFile=..\assets\mustacom.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; French first (default market), English as fallback language
ShowLanguageDialog=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.CreateStartMenuShortcuts=Créer des raccourcis dans le menu Démarrer
en.CreateStartMenuShortcuts=Create Start Menu shortcuts

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenu";  Description: "{cm:CreateStartMenuShortcuts}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; the frozen onedir bundle produced by build\mustacom.spec
Source: "..\dist\mustacom\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenu
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
