; The helper and its pinned download manifest are embedded in the setup EXE.
!define ERASE_IT_HOOK_DIR "${__FILEDIR__}"
Var NvidiaSetupResult

!macro NSIS_HOOK_POSTINSTALL
  !if /FileExists "${ERASE_IT_HOOK_DIR}\..\resources\setup\nvidia-download.json"
    ClearErrors
    ${GetOptions} $CMDLINE "/NVIDIA" $NvidiaSetupResult
    ${IfNot} ${Errors}
      Goto erase_it_nvidia_install
    ${EndIf}
    ClearErrors
    IfSilent erase_it_nvidia_done
    ${If} $PassiveMode = 1
      Goto erase_it_nvidia_done
    ${EndIf}
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "erase-it is installed.$\r$\n$\r$\nInstall NVIDIA GPU acceleration too?$\r$\n$\r$\nThis downloads about 3.2 GB and needs about 12 GB of free space during setup (5 GB afterwards). An NVIDIA GPU and compatible driver are required.$\r$\n$\r$\nChoose No to use CPU processing. You can rerun this same installer to add GPU support later." IDYES erase_it_nvidia_install
    Goto erase_it_nvidia_done

    erase_it_nvidia_install:
    InitPluginsDir
    File /oname=$PLUGINSDIR\install-nvidia.ps1 "${ERASE_IT_HOOK_DIR}\..\..\scripts\install-nvidia.ps1"
    File /oname=$PLUGINSDIR\download-nvidia.ps1 "${ERASE_IT_HOOK_DIR}\..\..\scripts\download-nvidia.ps1"
    File /oname=$PLUGINSDIR\nvidia-download.json "${ERASE_IT_HOOK_DIR}\..\resources\setup\nvidia-download.json"
    SetDetailsView show
    DetailPrint "Installing optional NVIDIA support. This may take several minutes."
    nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\install-nvidia.ps1" -Download -Manifest "$PLUGINSDIR\nvidia-download.json" -DataDirectory "$APPDATA\${BUNDLEID}"'
    Pop $NvidiaSetupResult
    ${If} $NvidiaSetupResult != "0"
      DetailPrint "NVIDIA setup did not finish. erase-it is installed and can use the CPU."
      IfSilent erase_it_nvidia_failed_silent
      ${If} $PassiveMode = 1
        Goto erase_it_nvidia_failed_silent
      ${EndIf}
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "NVIDIA support could not be installed. Check the details above and your internet connection.$\r$\n$\r$\nRetry reuses verified downloads. Cancel finishes setup with CPU processing; you can rerun this installer later." IDRETRY erase_it_nvidia_install
      Goto erase_it_nvidia_done
      erase_it_nvidia_failed_silent:
      SetErrorLevel 30
    ${Else}
      DetailPrint "NVIDIA support installed. Choose Automatic in erase-it."
    ${EndIf}
    erase_it_nvidia_done:
  !else
    ; Development builds do not publish runtime downloads.
    ClearErrors
    ${GetOptions} $CMDLINE "/NVIDIA" $NvidiaSetupResult
    ${IfNot} ${Errors}
      DetailPrint "This development installer has no NVIDIA download manifest. Use a published release."
      SetErrorLevel 30
    ${EndIf}
    ClearErrors
  !endif
!macroend
