; electron-builder NSIS hooks: install the bundled OBS plugin when OBS Studio is present.
;
; OBS 30+ loads per-machine plugins from %ProgramData%\obs-studio\plugins\<name>\
; (bin\64bit\<name>.dll + data\). Standard users may create folders there, so this
; works for the default per-user install without elevation.

!macro whatObsPluginsDir
  ; With "all" context, $APPDATA is %ProgramData%.
  SetShellVarContext all
  StrCpy $R8 "$APPDATA\obs-studio\plugins"
  SetShellVarContext current
!macroend

!macro customInstall
  SetRegView 64
  ReadRegStr $R9 HKLM "SOFTWARE\OBS Studio" ""
  SetRegView lastused
  ${If} $R9 != ""
  ${AndIf} ${FileExists} "$INSTDIR\resources\obs-plugin\what_overlay_plugin\bin\64bit\what_overlay_plugin.dll"
    !insertmacro whatObsPluginsDir
    DetailPrint "OBS Studio found at $R9; installing the What Caption Box plugin to $R8"
    CreateDirectory "$R8"
    ClearErrors
    CopyFiles /SILENT "$INSTDIR\resources\obs-plugin\*.*" "$R8"
    ${If} ${Errors}
      MessageBox MB_OK|MB_ICONEXCLAMATION "The What OBS plugin could not be copied to $R8. If OBS is running, close it and run this installer again."
    ${EndIf}
  ${EndIf}
!macroend

!macro customUnInstall
  !insertmacro whatObsPluginsDir
  RMDir /r "$R8\what_overlay_plugin"
!macroend
