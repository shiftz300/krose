Unicode true
!include MUI2.nsh
!include x64.nsh
!ifndef VERSION
  !error "VERSION is required"
!endif
!ifndef PAYLOAD
  !error "PAYLOAD is required"
!endif
Name "Krose ${VERSION}"
OutFile "Krose-${VERSION}-windows-x64-setup.exe"
InstallDir "$PROGRAMFILES64\Krose"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_ICON "${__FILEDIR__}/../src/plugin/resources/Krose.ico"
!define MUI_UNICON "${__FILEDIR__}/../src/plugin/resources/Krose.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Krose requires 64-bit Windows."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd
Section "Standalone application" App
  SectionIn RO
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  File "${PAYLOAD}\Krose.exe"
  File /r /x *.samples "${PAYLOAD}\Resources"
  SetOutPath "$COMMONFILES64\Krose\Samples\${VERSION}"
  File "${PAYLOAD}\Resources\Factory.samples"
  File "${PAYLOAD}\Resources\SEGrand.samples"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Krose"
  CreateShortcut "$SMPROGRAMS\Krose\Krose.lnk" "$INSTDIR\Krose.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "DisplayName" "Krose"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "Publisher" "maincore"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "DisplayIcon" "$INSTDIR\Krose.exe,0"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose" "NoRepair" 1
SectionEnd
Section "VST3 plugin" VST3
  SetOutPath "$COMMONFILES64\VST3\Krose.vst3"
  File /r /x *.samples "${PAYLOAD}\Krose.vst3\*.*"
SectionEnd
Section "Uninstall"
  SetRegView 64
  SetShellVarContext all
  Delete "$INSTDIR\Krose.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\Resources"
  RMDir "$INSTDIR"
  Delete "$COMMONFILES64\Krose\Samples\${VERSION}\Factory.samples"
  Delete "$COMMONFILES64\Krose\Samples\${VERSION}\SEGrand.samples"
  RMDir "$COMMONFILES64\Krose\Samples\${VERSION}"
  RMDir "$COMMONFILES64\Krose\Samples"
  RMDir "$COMMONFILES64\Krose"
  RMDir /r "$COMMONFILES64\VST3\Krose.vst3"
  Delete "$SMPROGRAMS\Krose\Krose.lnk"
  RMDir "$SMPROGRAMS\Krose"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Krose"
SectionEnd
