import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, X } from 'lucide-react';
import { openUrl } from '@tauri-apps/plugin-opener';
import { desktop } from './bridge';
import { processingStatus } from './processing';
import type { Hello, Project } from './types';
import { version } from '../package.json';

export type GuidePage = 'selection' | 'gpu' | 'rendering';

export function QuickGuide({ page, onPage, onClose, capabilities, device }: {
  page: GuidePage; onPage: (page: GuidePage) => void; onClose: () => void;
  capabilities?: Hello['capabilities']; device?: Project['device'];
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [linkError, setLinkError] = useState('');
  const status = processingStatus(capabilities, device);
  const releaseUrl = `https://github.com/AmreetKumarkhuntia/earse-it/releases/tag/v${version}`;
  useEffect(() => { dialog.current?.showModal(); }, []);
  const openRelease = async () => {
    try {
      setLinkError('');
      if (desktop) await openUrl(releaseUrl);
      else window.open(releaseUrl, '_blank', 'noopener,noreferrer');
    } catch { setLinkError(`Could not open your browser. Copy this address: ${releaseUrl}`); }
  };

  return <dialog ref={dialog} className="help-modal guide-dialog" aria-labelledby="help-title" onClose={onClose}>
    <button className="modal-close icon-button" aria-label="Close guide" onClick={() => dialog.current?.close()}><X size={20} /></button>
    <span className="eyebrow">ERASE-IT · QUICK GUIDE</span>
    <h2 id="help-title">{{ selection: 'Your first cutout', gpu: 'Use your NVIDIA GPU', rendering: 'Choose your finished output' }[page]}</h2>
    <div className="guide-tabs" role="group" aria-label="Guide topic">
      <button aria-pressed={page === 'selection'} onClick={() => onPage('selection')}>Select & track</button>
      <button aria-pressed={page === 'gpu'} onClick={() => onPage('gpu')}>GPU setup</button>
      <button aria-pressed={page === 'rendering'} onClick={() => onPage('rendering')}>Rendering</button>
    </div>
    {page === 'selection' ? <>
      <ol className="guide-steps">
        <li><strong>Import and pause.</strong> Import a short video, then pause on a clear view of your subject. Download the Tiny model in Processing if prompted.</li>
        <li><strong>Mark what to keep.</strong> Choose Keep <kbd>1</kbd> and click or draw a short stroke inside the subject. You do not need to trace its outline. Or choose Box <kbd>B</kbd> and drag around it.</li>
        <li><strong>Remove unwanted areas.</strong> Choose Remove <kbd>2</kbd> and click or stroke inside any background that was included. Check the Cutout preview.</li>
        <li><strong>Track both ways.</strong> Follow the subject through your chosen range. If it drifts, pause on that frame, add Keep or Remove marks, and track again.</li>
        <li><strong>Export.</strong> Adjust the edges, then choose your format, background, and resolution in Render & Export. Every frame in your in/out range needs a mask before export is enabled.</li>
      </ol>
      <div className="keyboard-help"><span><kbd>Space</kbd> Play / pause</span><span><kbd>←</kbd><kbd>→</kbd> Step a frame</span><span><kbd>Esc</kbd> Close guide</span></div>
      <p>Original plays your video. Masked previews review one frame at a time and may play more slowly. Changing a selection clears old masks; track again to rebuild them.</p>
    </> : page === 'rendering' ? <>
      <ol className="guide-steps">
        <li><strong>Choose a format.</strong> MOV uses ProRes 4444 for editing and transparency. MP4 uses H.264 for smaller files and regular playback. PNG image sequences keep lossless frames; mask sequences contain 16-bit grayscale masks.</li>
        <li><strong>Choose the background.</strong> Keep it transparent in MOV or PNG, or choose green screen, blue screen, black, white, or a custom color. Use Preview background to check the result. MP4 always has a solid background.</li>
        <li><strong>Choose the size.</strong> Native preserves the original pixels. 720p, 1080p, 1440p (QHD), 2K (DCI), and 4K (Ultra HD) fit your footage within that size, keeping the whole picture and its portrait or landscape orientation. Check Output size for the exact dimensions.</li>
        <li><strong>Set quality and audio.</strong> High is a good default. Maximum makes larger video files; Standard makes smaller ones. Turn off Include source audio for a silent video. PNG sequences include frame-rate metadata but no audio.</li>
        <li><strong>Render again as needed.</strong> Background, resolution, quality, and audio settings reuse your masks. You can export multiple versions without tracking again. Use a new output name for each render.</li>
      </ol>
      <p>Rendering reads the original video, not the smaller preview. Upscaling enlarges pixels without adding detail. The project frame rate and selected in/out range stay consistent in every export.</p>
      <p>Green and blue screens are opaque backgrounds for chroma keying. For the cleanest edges in an editor, prefer a transparent MOV or PNG sequence.</p>
    </> : <>
      <div className="guide-status" role="status"><strong>{status.label}</strong><p>{status.detail}</p></div>
      <button className="primary guide-download" onClick={() => void openRelease()}>Open v{version} downloads <ArrowUpRight size={15} /></button>
      {linkError && <p role="alert">{linkError}</p>}
      <p>One Windows setup installs erase-it and offers optional NVIDIA support. GPU acceleration requires an <strong>NVIDIA GPU</strong> and a compatible driver. AMD and Intel GPU acceleration is not supported yet.</p>
      <ol className="guide-steps">
        <li><strong>Run setup for v{version}.</strong> Download <code>erase-it-{version}-windows-x64-setup.exe</code> from this version’s release. Close erase-it and run that EXE, even if the app is already installed.</li>
        <li><strong>Choose Yes for NVIDIA GPU acceleration.</strong> Setup downloads and verifies the matching runtime automatically. Allow about 3.2 GB of internet data and 12 GB of free space during setup (5 GB afterwards). If a download fails, choose Retry; verified downloads are reused.</li>
        <li><strong>Restart and choose Automatic.</strong> Import or reopen your project. Processing should show your GPU’s name. Choose Automatic or NVIDIA GPU, then select or track a subject.</li>
        <li><strong>If it still shows CPU:</strong> check the status above. If the NVIDIA runtime is installed but no GPU is detected, update the NVIDIA driver for your card, restart Windows, and try again. Run <code>nvidia-smi</code> in a terminal to check whether the driver sees your card.</li>
      </ol>
      <p>GPU processing speeds up <strong>selection and tracking</strong>. Import, video decoding, and export still use the CPU, so CPU activity during those steps is expected. The tracking progress shows the device actually in use.</p>
      <p>Choose NVIDIA support again when installing an app update. Setup includes Python, PyTorch with CUDA, and SAM 2; your NVIDIA graphics driver is installed separately. Download the Tiny model in Processing on first use.</p>
      <p>If a runtime prevents startup, close the app and remove only <code>%APPDATA%\\io.github.amreetkumarkhuntia.eraseit\\runtimes\\nvidia</code> to return to the bundled CPU runtime.</p>
      {capabilities?.runtime_error && <details><summary>Runtime error details</summary><pre className="guide-command">{capabilities.runtime_error}</pre></details>}
    </>}
  </dialog>;
}
