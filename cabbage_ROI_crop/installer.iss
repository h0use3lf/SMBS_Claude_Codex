; ROI Cropper 설치 프로그램 (Inno Setup 6). build.bat에서 /DAppVersion=x.y.z 로 호출.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2A7E-3B4D-4E8A-9C21-5D7A0B3E9F11}
AppName=ROI Cropper
AppVersion={#AppVersion}
DefaultDirName={autopf}\ROI Cropper
DefaultGroupName=ROI Cropper
; 관리자 권한 없이 사용자 폴더에 설치 (실험실 PC 등)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=ROI_Cropper_Setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ROI_Cropper.exe
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[Files]
Source: "dist\ROI_Cropper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\ROI Cropper"; Filename: "{app}\ROI_Cropper.exe"
Name: "{group}\{cm:UninstallProgram,ROI Cropper}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ROI Cropper"; Filename: "{app}\ROI_Cropper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ROI_Cropper.exe"; Description: "{cm:LaunchProgram,ROI Cropper}"; Flags: nowait postinstall skipifsilent
