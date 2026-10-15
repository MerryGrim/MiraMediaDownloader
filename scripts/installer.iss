; Mira Media Downloader — per-user, single-file compressed Windows installer.
#ifndef AppVersion
  #define AppVersion "1.4.4"
#endif
#ifndef AppSource
  #define AppSource "..\build\dist\MiraMediaDownloader"
#endif
#ifndef SetupOutput
  #define SetupOutput "..\build\installer"
#endif
#include "..\native\vc_runtime_requirement.h"

[Setup]
AppId={{58B21ECA-0F07-4C08-A8AF-7C4CDCEFB839}
AppName=Mira Media Downloader
AppVersion={#AppVersion}
AppPublisher=Mira
AppCopyright=GPL-2.0-or-later
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=Mira Media Downloader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupArchitecture=x64
MinVersion=10.0.17763
OutputDir={#SetupOutput}
OutputBaseFilename=MiraMediaDownloader-{#AppVersion}-Setup-x64
SetupIconFile=..\assets\mira.ico
UninstallDisplayIcon={app}\MiraMediaDownloader.exe
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=1
WizardStyle=modern windows11 includetitlebar hidebevels
DisableWelcomePage=no
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
WizardImageFile=..\assets\installer-welcome-cloud-v1.png
WizardImageBackColor=$F7FAFE
WizardImageStretch=yes
WizardSmallImageFile=..\assets\installer-small-mira.png
CloseApplications=yes
CloseApplicationsFilter=MiraMediaDownloader.exe,MiraMediaDownloaderCore.exe,QtWebEngineProcess.exe
RestartApplications=no
SetupLogging=yes
Uninstallable=yes
UninstallFilesDir={app}\uninstall
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Messages]
english.WelcomeLabel1=Welcome to Mira
english.WelcomeLabel2=Save what you love.%n%nMira Media Downloader saves available images from X and Pixiv in the best available quality.%n%nChoose an installation folder and make yourself at home. The app offers English, Russian and Simplified Chinese, with light and dark themes.
russian.WelcomeLabel1=Добро пожаловать в Mira
russian.WelcomeLabel2=Сохраним то, что нравится.%n%nMira Media Downloader сохраняет доступные картинки из X и Pixiv в лучшем доступном качестве.%n%nВыберите место для приложения и устраивайтесь поудобнее. Внутри — русский, английский и китайский языки, светлая и тёмная темы.
chinesesimp.WelcomeLabel1=欢迎使用 Mira
chinesesimp.WelcomeLabel2=收藏你喜欢的图片。%n%nMira Media Downloader 可保存 X 和 Pixiv 中可获取的最高画质图片。%n%n选择安装文件夹，轻松开始收藏。应用支持简体中文、英语和俄语，以及浅色和深色主题。
english.FinishedHeadingLabel=Mira is ready
russian.FinishedHeadingLabel=Mira готова к работе
chinesesimp.FinishedHeadingLabel=Mira 已准备就绪

[CustomMessages]
english.VcRuntimeOffer=Mira needs Microsoft Visual C++ x64 Runtime %1 or newer.%n%nDownload the separate official Microsoft installer (about 19 MB) and open it now? You will review and accept Microsoft's license in its own installation window. Administrator approval may be required.%n%nThe Microsoft component is not included in Mira's package.
russian.VcRuntimeOffer=Для Mira нужен Microsoft Visual C++ x64 Runtime %1 или новее.%n%nСкачать отдельный официальный установщик Microsoft (около 19 МБ) и открыть его сейчас? Его лицензию вы прочитаете и примете в окне Microsoft. Может потребоваться разрешение администратора.%n%nКомпонент Microsoft не входит в комплект Mira.
chinesesimp.VcRuntimeOffer=Mira 需要 Microsoft Visual C++ x64 Runtime %1 或更高版本。%n%n是否立即下载并打开 Microsoft 官方独立安装程序（约 19 MB）？您将在 Microsoft 自己的安装窗口中阅读并接受其许可。可能需要管理员授权。%n%nMira 安装包不包含此 Microsoft 组件。
english.VcRuntimeDeclined=The required Microsoft Visual C++ x64 Runtime is not installed. Install it from Microsoft's official page, then run Mira Setup again. No Mira files have been installed.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
russian.VcRuntimeDeclined=Не установлен необходимый Microsoft Visual C++ x64 Runtime. Установите его с официальной страницы Microsoft и запустите установку Mira снова. Файлы Mira ещё не установлены.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
chinesesimp.VcRuntimeDeclined=尚未安装所需的 Microsoft Visual C++ x64 Runtime。请从 Microsoft 官方页面安装，然后重新运行 Mira 安装程序。尚未安装任何 Mira 文件。%n%n{#MIRA_VC_RUNTIME_HELP_URL}
english.VcRuntimeSilent=Microsoft Visual C++ x64 Runtime %1 or newer is required. Unattended Mira Setup does not download or install Microsoft components. Install the runtime separately and retry.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
russian.VcRuntimeSilent=Нужен Microsoft Visual C++ x64 Runtime %1 или новее. Автоматическая установка Mira не скачивает и не устанавливает компоненты Microsoft. Установите runtime отдельно и повторите попытку.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
chinesesimp.VcRuntimeSilent=需要 Microsoft Visual C++ x64 Runtime %1 或更高版本。Mira 无人值守安装不会下载或安装 Microsoft 组件。请单独安装运行库后重试。%n%n{#MIRA_VC_RUNTIME_HELP_URL}
english.VcDownloadTitle=Preparing Mira
russian.VcDownloadTitle=Подготавливаем Mira
chinesesimp.VcDownloadTitle=正在准备 Mira
english.VcDownloadDescription=Downloading the official Microsoft Visual C++ x64 installer
russian.VcDownloadDescription=Скачиваем официальный установщик Microsoft Visual C++ x64
chinesesimp.VcDownloadDescription=正在下载 Microsoft Visual C++ x64 官方安装程序
english.VcDownloadFailed=The Microsoft installer could not be downloaded or verified. Nothing was executed. Check your connection and try again, or install the runtime from Microsoft's official page.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
russian.VcDownloadFailed=Не удалось скачать или проверить установщик Microsoft. Ничего не запускалось. Проверьте соединение и повторите попытку либо установите runtime с официальной страницы Microsoft.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
chinesesimp.VcDownloadFailed=无法下载或验证 Microsoft 安装程序，未运行任何文件。请检查网络后重试，或从 Microsoft 官方页面安装运行库。%n%n{#MIRA_VC_RUNTIME_HELP_URL}
english.VcRuntimeCancelled=The separate Microsoft installation was cancelled. Install the required runtime before installing Mira. No Mira files have been installed.
russian.VcRuntimeCancelled=Отдельная установка Microsoft отменена. Перед установкой Mira нужен этот runtime. Файлы Mira ещё не установлены.
chinesesimp.VcRuntimeCancelled=已取消独立的 Microsoft 安装。请先安装所需运行库，再安装 Mira。尚未安装任何 Mira 文件。
english.VcRuntimeFailed=The separate Microsoft installation did not finish successfully (code %1). Install the runtime from Microsoft's official page and run Mira Setup again.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
russian.VcRuntimeFailed=Отдельная установка Microsoft не завершилась успешно (код %1). Установите runtime с официальной страницы Microsoft и запустите установку Mira снова.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
chinesesimp.VcRuntimeFailed=独立的 Microsoft 安装未成功完成（代码 %1）。请从 Microsoft 官方页面安装运行库，然后重新运行 Mira 安装程序。%n%n{#MIRA_VC_RUNTIME_HELP_URL}
english.VcRuntimeStillMissing=The required Microsoft runtime files are still unavailable. If Microsoft requested a restart, restart Windows, then run Mira Setup again.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
russian.VcRuntimeStillMissing=Необходимые файлы Microsoft Runtime ещё недоступны. Если Microsoft попросила перезагрузку, перезагрузите Windows и запустите установку Mira снова.%n%n{#MIRA_VC_RUNTIME_HELP_URL}
chinesesimp.VcRuntimeStillMissing=所需的 Microsoft 运行库文件仍不可用。如果 Microsoft 提示需要重启，请重启 Windows 后重新运行 Mira 安装程序。%n%n{#MIRA_VC_RUNTIME_HELP_URL}
english.VcRuntimeRestart=Microsoft Runtime requires a Windows restart. Restart Windows, then run Mira Setup again. No Mira files have been installed.
russian.VcRuntimeRestart=Microsoft Runtime требуется перезагрузка Windows. Перезагрузите компьютер и запустите установку Mira снова. Файлы Mira ещё не установлены.
chinesesimp.VcRuntimeRestart=Microsoft 运行库需要重启 Windows。请重启后重新运行 Mira 安装程序。尚未安装任何 Mira 文件。
english.VcLegacyUnknown=This folder contains changed or unrecognized Microsoft runtime files. Mira will leave them untouched. Choose a new empty folder for this version. Your modified Qt libraries are not checked or removed.
russian.VcLegacyUnknown=В этой папке есть изменённые или неопознанные файлы Microsoft Runtime. Mira оставит их на месте. Выберите для этой версии новую пустую папку. Изменённые библиотеки Qt не проверяются и не удаляются.
chinesesimp.VcLegacyUnknown=此文件夹包含已修改或无法识别的 Microsoft 运行库文件。Mira 不会更改这些文件。请为此版本选择新的空文件夹。不会检查或删除您修改的 Qt 库。
english.VcLegacyCannotClean=The recognized old Microsoft runtime files could not be removed from this application folder. Close the old Mira application or choose a new empty folder, then retry.
russian.VcLegacyCannotClean=Не удалось удалить распознанные старые файлы Microsoft Runtime из папки приложения. Закройте прежнюю Mira либо выберите новую пустую папку и повторите попытку.
chinesesimp.VcLegacyCannotClean=无法从此应用文件夹删除已识别的旧 Microsoft 运行库文件。请关闭旧版 Mira，或选择新的空文件夹后重试。

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Mira Media Downloader"; Filename: "{app}\MiraMediaDownloader.exe"; WorkingDir: "{app}"; AppUserModelID: "Mira.MiraMediaDownloader"
Name: "{autodesktop}\Mira Media Downloader"; Filename: "{app}\MiraMediaDownloader.exe"; WorkingDir: "{app}"; AppUserModelID: "Mira.MiraMediaDownloader"; Tasks: desktopicon

[Run]
Filename: "{app}\MiraMediaDownloader.exe"; Description: "{cm:LaunchProgram,Mira Media Downloader}"; Flags: nowait postinstall skipifsilent; Check: CanLaunchMiraAfterInstall

[Code]
var
  VcDownloadPage: TDownloadWizardPage;
  VcRuntimeRestartRequired: Boolean;
  LegacyCrtPaths, LegacyCrtHashes: TArrayOfString;

#include "..\native\legacy_crt_hashes.iss"

function NativeFileAttributes(const FileName: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function LegacyCrtPath(const RelativePath: String; var FileName: String): Boolean;
var
  Root, Remaining, Part, Current: String;
  Separator: Integer;
  Attributes: Cardinal;
begin
  Result := False;
  { The generated names contain only fixed relative path components. }
  if (RelativePath = '') or (Pos(':', RelativePath) <> 0) or
     (Pos('..', RelativePath) <> 0) or (RelativePath[1] = '\') or
     (Pos('/', RelativePath) <> 0) then
    Exit;
  Root := AddBackslash(ExpandFileName(ExpandConstant('{app}')));
  FileName := ExpandFileName(Root + RelativePath);
  if Pos(Lowercase(Root), Lowercase(FileName)) <> 1 then
    Exit;
  { Never follow an application-directory junction or symlink while removing
    legacy files, even when its target happens to contain a matching DLL. }
  Current := RemoveBackslashUnlessRoot(Root);
  Remaining := RelativePath;
  repeat
    Attributes := NativeFileAttributes(Current);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then
      Exit;
    Separator := Pos('\', Remaining);
    if Separator = 0 then
    begin
      Current := AddBackslash(Current) + Remaining;
      Remaining := '';
    end
    else
    begin
      Part := Copy(Remaining, 1, Separator - 1);
      Current := AddBackslash(Current) + Part;
      Delete(Remaining, 1, Separator);
    end;
  until Remaining = '';
  Attributes := NativeFileAttributes(FileName);
  Result := (Attributes = $FFFFFFFF) or ((Attributes and $400) = 0);
end;

function IsCrtName(const Name: String): Boolean;
var
  Value: String;
begin
  Value := Lowercase(Name);
  Result := (ExtractFileExt(Value) = '.dll') and
    ((Pos('msvcp', Value) = 1) or (Pos('msvcr', Value) = 1) or
     (Pos('vcruntime', Value) = 1) or (Pos('concrt', Value) = 1) or
     (Pos('vcomp', Value) = 1));
end;

function RecognizedLegacyCrt(const RelativePath: String): Boolean;
var
  Index: Integer;
  FileName: String;
begin
  Result := False;
  for Index := 0 to GetArrayLength(LegacyCrtPaths) - 1 do
    if CompareText(RelativePath, LegacyCrtPaths[Index]) = 0 then
    begin
      if not LegacyCrtPath(RelativePath, FileName) then
        Exit;
      try
        Result := Lowercase(GetSHA256OfFile(FileName)) = LegacyCrtHashes[Index];
      except
        Result := False;
      end;
      Exit;
    end;
end;

function LegacyCrtTreeIsKnown(const Directory, RelativeDirectory: String; Depth: Integer): Boolean;
var
  Entry: TFindRec;
  RelativeName, FullName: String;
begin
  Result := False;
  if Depth > 64 then
    Exit;
  Result := True;
  if not FindFirst(AddBackslash(Directory) + '*', Entry) then
    Exit;
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then
      begin
        RelativeName := RelativeDirectory + Entry.Name;
        FullName := AddBackslash(Directory) + Entry.Name;
        if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          { Do not enumerate linked user directories or Qt replacement trees. }
          if (Entry.Attributes and $400) = 0 then
            if not LegacyCrtTreeIsKnown(FullName, RelativeName + '\', Depth + 1) then
            begin
              Result := False;
              Exit;
            end;
        end
        else if IsCrtName(Entry.Name) then
          if not RecognizedLegacyCrt(RelativeName) then
          begin
            Result := False;
            Exit;
          end;
      end;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

function LegacyCrtUpgradeIsSafe: Boolean;
var
  Index: Integer;
  FileName: String;
begin
  Result := False;
  for Index := 0 to GetArrayLength(LegacyCrtPaths) - 1 do
  begin
    if not LegacyCrtPath(LegacyCrtPaths[Index], FileName) then
      Exit;
    if FileExists(FileName) and not RecognizedLegacyCrt(LegacyCrtPaths[Index]) then
      Exit;
  end;
  Result := LegacyCrtTreeIsKnown(ExpandConstant('{app}'), '', 0);
end;

procedure RemoveRecognizedLegacyCrt;
var
  Index: Integer;
  FileName: String;
begin
  { Validate every candidate before deleting any. Unknown files are preserved;
    only exact known 1.4.3 SHA-256 matches may be retired. No recursive delete. }
  if not LegacyCrtUpgradeIsSafe then
    RaiseException(CustomMessage('VcLegacyUnknown'));
  for Index := 0 to GetArrayLength(LegacyCrtPaths) - 1 do
  begin
    if not LegacyCrtPath(LegacyCrtPaths[Index], FileName) then
      RaiseException(CustomMessage('VcLegacyUnknown'));
    if FileExists(FileName) then
    begin
      if not RecognizedLegacyCrt(LegacyCrtPaths[Index]) then
        RaiseException(CustomMessage('VcLegacyUnknown'));
      if not DeleteFile(FileName) then
        RaiseException(CustomMessage('VcLegacyCannotClean'));
      Log('Removed recognized obsolete Microsoft runtime file: ' + LegacyCrtPaths[Index]);
    end;
  end;
end;

function SystemRuntimeIsReady: Boolean;
var
  Names: TArrayOfString;
  Index: Integer;
  VersionMS, VersionLS: Cardinal;
  RequiredVersion: Int64;
begin
  Result := False;
  { SetupArchitecture=x64 uses the native System32 directory. No
    current-directory, PATH or application-local runtime DLL is considered. }
  Names := ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll',
            'vcruntime140.dll', 'vcruntime140_1.dll'];
  RequiredVersion := PackVersionComponents({#MIRA_VC_RUNTIME_MAJOR},
    {#MIRA_VC_RUNTIME_MINOR}, {#MIRA_VC_RUNTIME_BUILD}, {#MIRA_VC_RUNTIME_REVISION});
  for Index := 0 to GetArrayLength(Names) - 1 do
  begin
    if not GetVersionNumbers(AddBackslash(ExpandConstant('{sys}')) + Names[Index], VersionMS, VersionLS) then
      Exit;
    if ComparePackedVersion(PackVersionNumbers(VersionMS, VersionLS), RequiredVersion) < 0 then
      Exit;
  end;
  Result := True;
end;

procedure InitializeWizard;
begin
  GetLegacyCrtFiles(LegacyCrtPaths, LegacyCrtHashes);
  VcDownloadPage := CreateDownloadPage(CustomMessage('VcDownloadTitle'),
    CustomMessage('VcDownloadDescription'), nil);
  VcDownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function NeedRestart: Boolean;
begin
  Result := VcRuntimeRestartRequired;
end;

function CanLaunchMiraAfterInstall: Boolean;
begin
  Result := not VcRuntimeRestartRequired;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
  DownloadSucceeded: Boolean;
begin
  Result := '';
  if not LegacyCrtUpgradeIsSafe then
  begin
    Result := CustomMessage('VcLegacyUnknown');
    Exit;
  end;
  if SystemRuntimeIsReady then
  begin
    Log('Required Microsoft x64 runtime is already available in System32.');
    Exit;
  end;
  if WizardSilent then
  begin
    Result := FmtMessage(CustomMessage('VcRuntimeSilent'), ['{#MIRA_VC_RUNTIME_MIN_VERSION}']);
    Exit;
  end;
  if MsgBox(FmtMessage(CustomMessage('VcRuntimeOffer'), ['{#MIRA_VC_RUNTIME_MIN_VERSION}']),
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES then
  begin
    Result := CustomMessage('VcRuntimeDeclined');
    Exit;
  end;

  DownloadSucceeded := False;
  VcDownloadPage.Clear;
  { This fixed Microsoft URL was Authenticode-verified as Microsoft Corporation
    at release preparation. The SHA-256 pins those exact signed bytes. The
    Microsoft component is downloaded separately and never bundled with Mira. }
  VcDownloadPage.Add('{#MIRA_VC_REDIST_URL}', 'vc_redist.x64.exe', '{#MIRA_VC_REDIST_SHA256}');
  VcDownloadPage.Show;
  try
    try
      VcDownloadPage.Download;
      DownloadSucceeded := True;
    except
      Log('Microsoft prerequisite download/identity verification did not complete.');
      if VcDownloadPage.AbortedByUser then
        Result := CustomMessage('VcRuntimeCancelled')
      else
        Result := CustomMessage('VcDownloadFailed');
    end;
  finally
    VcDownloadPage.Hide;
  end;
  if not DownloadSucceeded then
    Exit;

  { A normal visible Microsoft UI handles its own EULA and administrator
    approval. /norestart only prevents an automatic restart during Mira Setup;
    no /quiet, /passive or implicit license-acceptance flag is used. }
  if not Exec(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/norestart', '',
      SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode) then
  begin
    if ExitCode = 1223 then
      Result := CustomMessage('VcRuntimeCancelled')
    else
      Result := FmtMessage(CustomMessage('VcRuntimeFailed'), [IntToStr(ExitCode)]);
    Exit;
  end;
  if (ExitCode = 1602) or (ExitCode = 1223) then
  begin
    Result := CustomMessage('VcRuntimeCancelled');
    Exit;
  end;
  if (ExitCode = 3010) or (ExitCode = 1641) then
    VcRuntimeRestartRequired := True
  else if (ExitCode <> 0) and (ExitCode <> 1638) then
  begin
    Result := FmtMessage(CustomMessage('VcRuntimeFailed'), [IntToStr(ExitCode)]);
    Exit;
  end;
  if not SystemRuntimeIsReady then
  begin
    if VcRuntimeRestartRequired then
    begin
      NeedsRestart := True;
      Result := CustomMessage('VcRuntimeRestart');
    end
    else
      Result := CustomMessage('VcRuntimeStillMissing');
  end;
end;

function DefaultInstallDir(Param: String): String;
begin
  if DirExists('D:\') then
    Result := 'D:\Apps\Mira Media Downloader'
  else
    Result := ExpandConstant('{localappdata}\Programs\Mira Media Downloader');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  LegacyCore: String;
begin
  if CurStep = ssInstall then
  begin
    RemoveRecognizedLegacyCrt;
    Exit;
  end;
  if CurStep <> ssPostInstall then
    Exit;
  { Retire only the exact known 1.4.1 root executable after a successful
    installation. Never recursively remove an old folder or unknown file. }
  LegacyCore := ExpandConstant('{app}\MiraMediaDownloaderCore.exe');
  if FileExists(LegacyCore) and
     FileExists(ExpandConstant('{app}\runtime\MiraMediaDownloaderCore.exe')) then
  begin
    try
      if Lowercase(GetSHA256OfFile(LegacyCore)) =
         'fe714e03557ad7fed35b45c115609114ccaac8d1224cf9929df9c62a6742c113' then
      begin
        if DeleteFile(LegacyCore) then
          Log('Removed recognized obsolete 1.4.1 root Core executable.')
        else
          Log('Recognized obsolete executable could not be removed.');
      end;
    except
      Log('Obsolete executable was retained because its identity could not be verified.');
    end;
  end;
end;
