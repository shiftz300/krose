; Inno Setup 7.1.1. Build with /DAppVersion=... /DPayload=... /O...
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef Payload
  #error Payload is required
#endif

[Setup]
AppId=Krose
AppName=Krose
AppVersion={#AppVersion}
AppPublisher=maincore
VersionInfoCompany=maincore
VersionInfoDescription=Krose installer
DefaultDirName={code:DefaultDirectory}
DefaultGroupName=Krose
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=6.1
OutputBaseFilename=Krose-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark
SetupIconFile=..\src\plugin\resources\Krose.ico
UninstallDisplayIcon={app}\Krose.exe
CloseApplications=yes
RestartApplications=no

[Types]
Name: "full"; Description: "Standalone application and VST3 plugin"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "app"; Description: "Standalone application"; Types: full custom; Flags: fixed
Name: "vst3"; Description: "VST3 plugin"; Types: full custom

[Files]
Source: "{#Payload}\Krose.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: app
Source: "{#Payload}\*.dll"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: app
Source: "{#Payload}\Resources\*"; DestDir: "{app}\Resources"; Excludes: "*.samples"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: app
Source: "{#Payload}\Resources\Factory.samples"; DestDir: "{commoncf64}\Krose\Samples\{#AppVersion}"; Flags: ignoreversion
Source: "{#Payload}\Resources\SEGrand.samples"; DestDir: "{commoncf64}\Krose\Samples\{#AppVersion}"; Flags: ignoreversion
Source: "{#Payload}\Krose.vst3\*"; DestDir: "{commoncf64}\VST3\Krose.vst3"; Excludes: "*.samples"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: vst3

[Icons]
Name: "{group}\Krose"; Filename: "{app}\Krose.exe"; Components: app

[Code]
const
  LegacyKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose';
var
  LegacyDirectory: String;

function InitializeSetup: Boolean;
var
  Name, Folder: String;
begin
  LegacyDirectory := '';
  if RegQueryStringValue(HKLM64, LegacyKey, 'DisplayName', Name) and
     (Name = 'Krose') and
     RegQueryStringValue(HKLM64, LegacyKey, 'InstallLocation', Folder) and
     FileExists(AddBackslash(Folder) + 'Krose.exe') then
    LegacyDirectory := Folder;
  Result := True;
end;

function DefaultDirectory(Param: String): String;
begin
  if LegacyDirectory <> '' then Result := LegacyDirectory
  else Result := ExpandConstant('{autopf}\Krose');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldUninstaller: String;
begin
  { Only retire the old NSIS record after successfully replacing the same app.
    Never invoke its uninstaller, which would remove the newly installed files. }
  if (CurStep = ssDone) and (LegacyDirectory <> '') and
     (CompareText(AddBackslash(LegacyDirectory), AddBackslash(ExpandConstant('{app}'))) = 0) then begin
    OldUninstaller := AddBackslash(LegacyDirectory) + 'Uninstall.exe';
    if not FileExists(OldUninstaller) or DeleteFile(OldUninstaller) then
      RegDeleteKeyIncludingSubkeys(HKLM64, LegacyKey)
    else Log('Legacy uninstaller is in use; retaining its registration.');
  end;
end;
