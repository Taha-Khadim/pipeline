; Inno Setup script for Lumora Code — Client Pipeline.
; Build with: iscc build\installer.iss
; (Run build-exe.bat first to produce the PyInstaller bundle.)

#define AppName       "Lumora Code"
#define AppFullName   "Lumora Code — Client Pipeline"
#define AppVersion    "1.0.0"
#define AppPublisher  "Lumora Code"
#define AppExe        "lumora-pipeline.exe"
#define BundleDir     "dist-pyinstaller\lumora-pipeline"

[Setup]
AppId={{8b7d6411-0c2a-4d56-9a40-9d04d76b7d9b}
AppName={#AppFullName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\LumoraPipeline
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=lumora-pipeline-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\favicon.svg
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppFullName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppFullName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
