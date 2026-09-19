import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react';
import { open, save } from '@tauri-apps/plugin-dialog';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BoxSelect, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Cpu, Film, FolderOpen, HardDrive, Layers2, LoaderCircle, Minus, MousePointer2, Pause, Play, Plus, Redo2, ScanLine, Scissors, ShieldCheck, Undo2, X } from 'lucide-react';
import { asset, cancel, desktop, request, subscribe, WorkerError } from './bridge';
import { appendPoint, clamp, coveredFrames, imageRect, makeBox, normalizePoint, timecode } from './geometry';
import type { Box, Edge, FrameResult, Hello, Model, Point, PreviewMode, Progress, Project, Prompts, Tool } from './types';
import { version as appVersion } from '../package.json';

const MODES: PreviewMode[] = ['overlay', 'cutout', 'mask', 'original'];
const EMPTY_PROMPT = { points: [] as Point[], box: null as Box | null };

function SelectionArt() {
  return <svg className="selection-art" viewBox="0 0 460 240" aria-hidden="true">
    <defs><pattern id="grid" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" fill="none" stroke="#343f35" strokeWidth=".5" /></pattern></defs>
    <rect x="28" y="20" width="400" height="194" rx="16" fill="url(#grid)" />
    <path d="M97 155L110 124L158 113L193 72H279L324 117L356 130L366 159L349 169H108Z" fill="#60705a" stroke="#a3b199" strokeWidth="2" />
    <path d="M174 114L205 84H272L303 114Z" fill="#253b31" /><path d="M237 84V114" stroke="#879d7b" strokeWidth="3" />
    <circle cx="155" cy="160" r="25" fill="#19211c" stroke="#a3b199" strokeWidth="2" /><circle cx="155" cy="160" r="11" fill="#45543e" />
    <circle cx="310" cy="160" r="25" fill="#19211c" stroke="#a3b199" strokeWidth="2" /><circle cx="310" cy="160" r="11" fill="#45543e" />
    <rect x="80" y="54" width="303" height="144" rx="9" fill="none" stroke="#cbf48b" strokeWidth="1.5" strokeDasharray="6 5" />
    {[ [80,54], [383,54], [80,198], [383,198] ].map(([x,y]) => <rect key={`${x}-${y}`} x={x-3} y={y-3} width="6" height="6" rx="1" fill="#cbf48b" />)}
    <path d="M278 137L279 165L287 158L294 175L301 171L293 155L304 153Z" fill="#e9efd9" stroke="#19211c" strokeWidth="2" />
    <rect x="286" y="36" width="82" height="22" rx="11" fill="#cbf48b" /><text x="327" y="51" textAnchor="middle" fontSize="10" fontFamily="sans-serif" fill="#213119">SUBJECT 01</text>
  </svg>;
}

export function App() {
  const [hello, setHello] = useState<Hello | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [frame, setFrame] = useState(0);
  const [mode, setMode] = useState<PreviewMode>('overlay');
  const [tool, setTool] = useState<Tool>('keep');
  const [preview, setPreview] = useState<FrameResult | null>(null);
  const [busy, setBusy] = useState<{ id: string; action: string } | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);
  const [edge, setEdge] = useState<Edge>({ feather: 1, grow: 0, invert: false });
  const [history, setHistory] = useState<{ past: Prompts[]; future: Prompts[] }>({ past: [], future: [] });
  const [stroke, setStroke] = useState<Point[]>([]);
  const [boxDraft, setBoxDraft] = useState<Box | null>(null);
  const [format, setFormat] = useState<'prores' | 'mask_sequence'>('prores');
  const [playing, setPlaying] = useState(false);
  const [help, setHelp] = useState(false);
  const [importOptions, setImportOptions] = useState(false);
  const [importFps, setImportFps] = useState('auto');
  const viewer = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [viewerSize, setViewerSize] = useState({ width: 800, height: 500 });
  const drawing = useRef<{ start: [number, number]; points: Point[] } | null>(null);
  const projectRef = useRef(project); projectRef.current = project;
  const frameRef = useRef(frame); frameRef.current = frame;
  const busyRef = useRef(busy); busyRef.current = busy;
  const error = useCallback((value: unknown) => {
    if (value instanceof WorkerError && value.code === 'CANCELLED') setNotice({ message: value.message, error: false });
    else setNotice({ message: value instanceof Error ? value.message : String(value), error: true });
  }, []);

  const run = useCallback(async <T,>(action: string, params: Record<string, unknown> = {}): Promise<T | undefined> => {
    if (busyRef.current) return;
    setPlaying(false);
    const operation = request<T>(action, params);
    busyRef.current = { id: operation.id, action };
    setBusy(busyRef.current); setProgress(null); setNotice(null);
    try { return await operation.promise; }
    catch (value) { error(value); }
    finally { busyRef.current = null; setBusy(null); setProgress(null); }
  }, [error]);

  useEffect(() => {
    const unsubscribe = subscribe(event => {
      if (event.event === 'progress') setProgress(event);
      else error(new Error(event.message));
    });
    if (desktop) request<Hello>('hello').promise.then(setHello).catch(error);
    return unsubscribe;
  }, [error]);

  useEffect(() => {
    if (!viewer.current) return;
    const observer = new ResizeObserver(([entry]) => setViewerSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(viewer.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!project || busy) return;
    let stale = false;
    const timer = window.setTimeout(() => request<FrameResult>('frame', { frame, mode }).promise
      .then(result => { if (!stale) setPreview(result); }).catch(value => { if (!stale) error(value); }), 35);
    return () => { stale = true; clearTimeout(timer); };
  }, [project, frame, mode, busy, error]);

  useEffect(() => {
    if (!playing || !project || mode === 'original') return;
    // Review playback advances only after each rendered frame arrives: no mask/frame mismatch.
    if (preview?.frame !== frame) return;
    const timer = window.setTimeout(() => {
      if (frame >= project.out_frame) setPlaying(false);
      else setFrame(frame + 1);
    }, 1000 * project.media.fps_den / project.media.fps_num);
    return () => clearTimeout(timer);
  }, [playing, frame, preview, project, mode]);

  useEffect(() => {
    if (mode !== 'original' || !video.current || !project) return;
    const element = video.current;
    if (playing) void element.play().catch(error);
    else { element.pause(); element.currentTime = frame * project.media.fps_den / project.media.fps_num; }
  }, [playing, mode, project, frame, error]);

  const acceptProject = (value: Project | undefined, reset = false) => {
    if (!value) return;
    setProject(value); setEdge(value.edge);
    if (reset) { setFrame(value.in_frame); setPreview(null); setHistory({ past: [], future: [] }); }
  };

  const importVideo = async () => {
    if (!desktop) { error(new Error('Open erase-it on your desktop to import and process videos.')); return; }
    try {
      const path = await open({ title: 'Import a video', multiple: false, filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] }] });
      if (typeof path === 'string') {
        setImportOptions(false);
        acceptProject(await run<Project>('import_video', { path, ...(importFps !== 'auto' ? { fps: importFps } : {}) }), true);
      }
    } catch (value) { error(value); }
  };

  const openProject = async (existing?: string) => {
    try {
      const path = existing ?? await open({ title: 'Open a project', multiple: false, filters: [{ name: 'erase-it project', extensions: ['cutout'] }] });
      if (typeof path === 'string') acceptProject(await run<Project>('open_project', { path }), true);
    } catch (value) { error(value); }
  };

  const saveProject = async () => {
    if (!project) return;
    try {
      const path = project.project_file ?? await save({ defaultPath: `${project.name}.cutout`, filters: [{ name: 'erase-it project', extensions: ['cutout'] }] });
      if (path) {
        const saved = await run<Project>('save_project', { path });
        acceptProject(saved);
        if (saved) setNotice({ message: 'Project saved. Your source video stays in its original location.', error: false });
      }
    } catch (value) { error(value); }
  };

  const updateSettings = async (changes: Record<string, unknown>) => acceptProject(await run<Project>('settings', changes));

  const changePrompts = async (next: Prompts, remember = true) => {
    if (!project || busyRef.current) return;
    if (remember) setHistory(value => ({ past: [...value.past.slice(-49), project.prompts], future: [] }));
    const result = await run<Project>('set_prompts', { prompts: next, frame });
    if (result) acceptProject(result);
    else request<Project>('project_info').promise.then(value => acceptProject(value)).catch(error);
  };

  const undo = async (redo = false) => {
    if (!project) return;
    const stack = redo ? history.future : history.past;
    const target = stack.at(-1);
    if (!target) return;
    setHistory(redo ? { past: [...history.past, project.prompts], future: history.future.slice(0, -1) }
      : { past: history.past.slice(0, -1), future: [...history.future, project.prompts] });
    await changePrompts(target, false);
  };

  const aspect = project ? project.media.width / project.media.height : 16 / 9;
  const rect = imageRect(viewerSize, aspect);
  const coordinates = (event: PointerEvent<HTMLDivElement>) => {
    const bounds = viewer.current!.getBoundingClientRect();
    return normalizePoint(event.clientX - bounds.left, event.clientY - bounds.top, rect);
  };
  const pointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!project || busy || playing || event.button !== 0 || preview?.frame !== frame) return;
    const position = coordinates(event);
    if (!position) return;
    if (mode === 'original') setMode('overlay');
    event.currentTarget.setPointerCapture(event.pointerId);
    const points: Point[] = tool === 'box' ? [] : [[...position, tool === 'keep' ? 1 : 0]];
    drawing.current = { start: position, points }; setStroke(points);
  };
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drawing.current) return;
    const position = coordinates(event);
    if (!position) return;
    if (tool === 'box') setBoxDraft(makeBox(drawing.current.start, position));
    else { drawing.current.points = appendPoint(drawing.current.points, [...position, tool === 'keep' ? 1 : 0]); setStroke(drawing.current.points); }
  };
  const pointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!project || !drawing.current) return;
    const draft = drawing.current; drawing.current = null;
    const existing = project.prompts[String(frame)] ?? EMPTY_PROMPT;
    const position = coordinates(event) ?? draft.start;
    const next = tool === 'box' ? { ...existing, box: makeBox(draft.start, position) } : { ...existing, points: [...existing.points, ...draft.points].slice(-128) };
    setStroke([]); setBoxDraft(null);
    if (tool !== 'box' || next.box) void changePrompts({ ...project.prompts, [frame]: next });
  };

  const track = async (direction: 'both' | 'forward' | 'backward') => {
    const result = await run<Project>('track', { frame, direction });
    if (result) acceptProject(result);
    else request<Project>('project_info').promise.then(value => acceptProject(value)).catch(error);
  };

  const downloadModel = async () => {
    const models = await run<Model[]>('download_model', { model: project?.model ?? 'tiny' });
    if (models) setHello(value => value ? { ...value, models } : value);
  };

  const exportVideo = async () => {
    if (!project) return;
    try {
      let path: string | null;
      if (format === 'prores') path = await save({ defaultPath: `${project.name}-cutout.mov`, filters: [{ name: 'ProRes 4444', extensions: ['mov'] }] });
      else {
        path = await save({ title: 'Name a new folder for the PNG masks', defaultPath: `${project.name}-masks` });
      }
      if (!path) return;
      const result = await run<{ path: string }>('export', { path, format });
      if (result) setNotice({ message: `Export saved to ${result.path}`, error: false });
    } catch (value) { error(value); }
  };

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
      if (busyRef.current) return;
      if (event.key === '1') setTool('keep');
      if (event.key === '2') setTool('remove');
      if (event.key.toLowerCase() === 'b') setTool('box');
      const current = projectRef.current;
      if (!current) return;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault(); setPlaying(false);
        setFrame(clamp(frameRef.current + (event.key === 'ArrowLeft' ? -1 : 1), 0, current.media.frame_count - 1));
      }
      if (event.key === ' ') { event.preventDefault(); setPlaying(value => !value); }
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, []);

  const fps = project ? project.media.fps_num / project.media.fps_den : 30;
  const currentPrompt = project?.prompts[String(frame)] ?? EMPTY_PROMPT;
  const displayedBox = boxDraft ?? currentPrompt.box;
  const selectedModel = hello?.models.find(model => model.id === (project?.model ?? 'tiny'));
  const selectedCount = project ? project.out_frame - project.in_frame + 1 : 0;
  const completed = project ? coveredFrames(project) : 0;
  const canTrack = !!project && !!project.prompts[String(frame)] && frame >= project.in_frame && frame <= project.out_frame && !busy;
  const percentage = progress?.total ? Math.min(100, Math.round(progress.current / progress.total * 100)) : 0;

  return <div className="app">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><Scissors size={21} strokeWidth={2} /></span><span>erase<span className="brand-light">-it</span><span className="version">BETA</span></span></div>
      <div className="workspace-label"><span className="tiny-dot" /> VIDEO WORKSPACE</div>
      <div className="top-actions"><span className="local-badge"><ShieldCheck size={14} /> Stays on your device</span><button className="icon-button" title="Help and keyboard shortcuts" aria-label="Help" onClick={() => setHelp(true)}><CircleHelp size={19} /></button></div>
    </header>

    <div className="workspace">
      <aside className="left-panel panel">
        <section><div className="section-label"><span>01</span> YOUR FOOTAGE</div>
          <button className="import-button" disabled={!!busy} onClick={() => void importVideo()}><Plus size={17} /> Import video <span className="shortcut">+</span></button>
          <button className="text-button import-options" onClick={() => setImportOptions(!importOptions)} disabled={!!busy}>Import options <ChevronDown size={12} /></button>
          {importOptions && <label className="field">Project frame rate<select value={importFps} onChange={event => setImportFps(event.target.value)}><option value="auto">Detect from video</option><option value="24000/1001">23.976 fps</option><option value="24">24 fps</option><option value="25">25 fps</option><option value="30000/1001">29.97 fps</option><option value="30">30 fps</option><option value="60000/1001">59.94 fps</option><option value="60">60 fps</option></select><small>Variable timing is normalized once for consistent masks and exports.</small></label>}
          {project ? <div className="media-card"><div className="media-icon"><Film size={25} /></div><strong title={project.source}>{project.name}</strong><span>{project.media.width} × {project.media.height} · {fps.toFixed(2)} fps</span><div className="media-tags"><span>{Math.ceil(project.media.duration)} SEC</span><span>{project.media.width >= 3840 || project.media.height >= 3840 ? '4K' : 'SDR'}</span><span>{project.media.has_audio ? 'AUDIO' : 'SILENT'}</span></div></div>
            : <div className="media-placeholder"><Film size={24} /><span>No footage yet</span><small>MP4, MOV, MKV, WebM</small></div>}
          <div className="project-actions"><button disabled={!!busy || !desktop} onClick={() => void openProject()}><FolderOpen size={13} /> Open project</button><button disabled={!project || !!busy} onClick={() => void saveProject()}>Save</button></div>
        </section>
        <section><div className="section-label"><span>02</span> SELECT SUBJECT</div><p className="section-copy">A stroke is all it takes.</p>
          <div className="tools">{([{ id: 'keep', icon: Plus, name: 'Keep', key: '1' }, { id: 'remove', icon: Minus, name: 'Remove', key: '2' }, { id: 'box', icon: BoxSelect, name: 'Box', key: 'B' }] as const).map(item => <button key={item.id} className={tool === item.id ? `tool active ${item.id}` : 'tool'} onClick={() => setTool(item.id)} disabled={!!busy}><item.icon size={18} /><span>{item.name}</span><kbd>{item.key}</kbd></button>)}</div>
          <p className="hint">{tool === 'box' ? 'Draw a box around the object you want to keep.' : tool === 'keep' ? 'Paint a short stroke inside your subject.' : 'Paint over areas that should be excluded from the selection.'}</p>
          <div className="edit-actions"><button title="Undo selection" disabled={!history.past.length || !!busy} onClick={() => void undo()}><Undo2 size={16} /></button><button title="Redo selection" disabled={!history.future.length || !!busy} onClick={() => void undo(true)}><Redo2 size={16} /></button><button disabled={!project?.prompts[String(frame)] || !!busy} onClick={() => { const next = { ...project!.prompts }; delete next[String(frame)]; void changePrompts(next); }}>Clear frame</button></div>
        </section>
        <section className="corrections"><div className="section-label">CORRECTION FRAMES <span className="count">{Object.keys(project?.prompts ?? {}).length}</span></div>
          {Object.keys(project?.prompts ?? {}).length ? <div className="keyframes">{Object.keys(project!.prompts).map(Number).sort((a,b) => a-b).map(index => <button disabled={!!busy} key={index} className={index === frame ? 'selected' : ''} onClick={() => { setPlaying(false); setFrame(index); }}><span className="diamond" />{timecode(index, fps)}<span>#{index + 1}</span></button>)}</div> : <p className="hint">Your selections appear here. Add a correction wherever the tracking needs a little help.</p>}
        </section>
        <div className="left-footer"><HardDrive size={15} /><span>Local files. Local processing.<br /><strong>Your footage is yours.</strong></span></div>
      </aside>

      <main className="main-panel">
        <div className="viewer-toolbar"><div className="clip-title"><Film size={15} /><span>{project?.name ?? 'Untitled workspace'}</span></div><div className="view-switch" role="group" aria-label="Preview mode">{MODES.map(value => <button key={value} className={mode === value ? 'active' : ''} onClick={() => { setPlaying(false); setMode(value); }} disabled={!!busy}>{value}</button>)}</div></div>
        <div ref={viewer} className={`viewer ${project ? 'has-video' : ''} ${mode === 'cutout' ? 'checkerboard' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { drawing.current = null; setStroke([]); setBoxDraft(null); }}>
          {!project ? <div className="empty-state"><span className="eyebrow">LESS BACKGROUND. MORE POSSIBILITY.</span><SelectionArt /><h1>Make your subject<br /><em>the whole story.</em></h1><p>Isolate a person, a car, or anything in between.<br />Select it. Track it. Take it to your editor.</p><button className="primary" disabled={!!busy} onPointerDown={event => event.stopPropagation()} onClick={() => void importVideo()}><Plus size={17} /> Import your video <ArrowUpRight size={17} /></button>{hello?.last_project && <button className="text-button reopen" onClick={() => void openProject(hello.last_project!)}>Reopen last project <ArrowRight size={13} /></button>}<span className="empty-footnote">Open source · No uploads · No subscriptions</span></div>
            : <>
              {mode === 'original' ? <video ref={video} src={asset(project.proxy)} className="source-video" onTimeUpdate={() => { if (playing && video.current) { const next = Math.floor(video.current.currentTime * fps); if (next >= project.out_frame) setPlaying(false); setFrame(clamp(next, 0, project.media.frame_count - 1)); } }} onEnded={() => setPlaying(false)} />
                : preview && <img className="frame-image" src={asset(preview.path)} draggable={false} alt={`Frame ${preview.frame + 1}, ${mode} preview`} />}
              <svg className="prompt-layer" width={viewerSize.width} height={viewerSize.height} aria-hidden="true"><g transform={`translate(${rect.x},${rect.y})`}>
                {displayedBox && <rect x={displayedBox[0] * rect.width} y={displayedBox[1] * rect.height} width={(displayedBox[2] - displayedBox[0]) * rect.width} height={(displayedBox[3] - displayedBox[1]) * rect.height} fill="none" stroke="#d1f58e" strokeWidth="1.5" strokeDasharray="5 4" />}
                {[...currentPrompt.points, ...stroke].map(([x,y,label], index) => <g key={index} transform={`translate(${x * rect.width},${y * rect.height})`}><circle r="4" fill={label ? '#d1f58e' : '#f19d8b'} stroke="#172119" strokeWidth="1.5" /></g>)}
              </g></svg>
              <div className="canvas-label"><span className="tiny-dot" /> SUBJECT 01</div><div className="canvas-meta">{project.media.width} × {project.media.height}<span>{mode === 'original' ? 'Source playback' : 'Frame review'}</span></div>
              {preview && !preview.has_mask && mode !== 'original' && !busy && <div className="canvas-tip"><MousePointer2 size={14} /> Draw on this frame to select your subject</div>}
            </>}
          {busy && <div className="job-overlay"><LoaderCircle className="spin" size={22} /><strong>{progress?.stage ?? ({ import_video: 'Preparing your footage', set_prompts: 'Updating selection', export: 'Preparing export', download_model: 'Preparing download', track: 'Preparing tracking' }[busy.action] ?? 'Working')}</strong><div className={`progress-bar ${progress?.total ? '' : 'indeterminate'}`}><span style={{ width: `${percentage}%` }} /></div><span>{progress?.total ? `${percentage}% · ${progress.current.toLocaleString()} / ${progress.total.toLocaleString()}` : 'This may take a moment'}</span><button className="text-button" onPointerDown={event => event.stopPropagation()} onClick={() => void cancel(busy.id).catch(error)}>Cancel</button></div>}
        </div>

        <div className="timeline">
          <div className="transport"><div className="playback"><button title="Previous frame" disabled={!project || !!busy} onClick={() => { setPlaying(false); setFrame(value => Math.max(0, value - 1)); }}><ChevronLeft size={18} /></button><button className="play-button" title={playing ? 'Pause' : 'Play preview'} disabled={!project || !!busy} onClick={() => { if (project && frame >= project.out_frame) setFrame(project.in_frame); setPlaying(value => !value); }}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><button title="Next frame" disabled={!project || !!busy} onClick={() => { setPlaying(false); setFrame(value => Math.min(project!.media.frame_count - 1, value + 1)); }}><ChevronRight size={18} /></button><span className="timecode">{timecode(frame, fps)}<span> / {timecode(project ? project.media.frame_count - 1 : 0, fps)}</span></span></div><span className="frame-counter">FRAME {project ? frame + 1 : '—'} <span>/ {project?.media.frame_count ?? '—'}</span></span></div>
          <div className="scrubber"><div className="scrub-track">{project?.tracked_ranges.map(([start,end]) => <span className="tracked-span" key={start} style={{ left: `${start / project.media.frame_count * 100}%`, width: `${(end-start+1) / project.media.frame_count * 100}%` }} />)}{Object.keys(project?.prompts ?? {}).map(key => <span className="keyframe-marker" key={key} style={{ left: `${Number(key) / Math.max(1, project!.media.frame_count - 1) * 100}%` }} />)}</div><input aria-label="Video timeline" type="range" min="0" max={Math.max(1, (project?.media.frame_count ?? 1) - 1)} value={frame} disabled={!project || !!busy} onChange={event => { setPlaying(false); setFrame(Number(event.target.value)); }} /></div>
          <div className="track-row"><div className="range-actions"><button disabled={!project || !!busy || frame > project.out_frame} onClick={() => void updateSettings({ in_frame: frame })}>Set in</button><span>{project ? timecode(project.in_frame, fps) : '00:00:00:00'}</span><span className="range-divider">→</span><span>{project ? timecode(project.out_frame, fps) : '00:00:00:00'}</span><button disabled={!project || !!busy || frame < project.in_frame} onClick={() => void updateSettings({ out_frame: frame })}>Set out</button></div><div className="track-actions"><button title="Track backward" disabled={!canTrack} onClick={() => void track('backward')}><ArrowLeft size={16} /></button><button className="primary track-both" disabled={!canTrack} onClick={() => void track('both')}><ScanLine size={16} /> Track both ways</button><button title="Track forward" disabled={!canTrack} onClick={() => void track('forward')}><ArrowRight size={16} /></button></div></div>
        </div>
      </main>

      <aside className="right-panel panel">
        <section><div className="section-label"><span>03</span> REFINE EDGES</div><p className="section-copy">The finishing touches.</p>
          <label className="slider-field"><span>Feather <output>{edge.feather.toFixed(1)} <small>px</small></output></span><input type="range" min="0" max="20" step=".5" value={edge.feather} disabled={!project || !!busy} onChange={event => setEdge({ ...edge, feather: Number(event.target.value) })} onPointerUp={() => void updateSettings({ edge })} onKeyUp={() => void updateSettings({ edge })} /></label>
          <label className="slider-field"><span>Shrink / grow <output>{edge.grow > 0 ? '+' : ''}{edge.grow} <small>px</small></output></span><input type="range" min="-20" max="20" value={edge.grow} disabled={!project || !!busy} onChange={event => setEdge({ ...edge, grow: Number(event.target.value) })} onPointerUp={() => void updateSettings({ edge })} onKeyUp={() => void updateSettings({ edge })} /></label>
          <label className="toggle-label"><span>Invert selection</span><input type="checkbox" checked={edge.invert} disabled={!project || !!busy} onChange={event => { const next = { ...edge, invert: event.target.checked }; setEdge(next); void updateSettings({ edge: next }); }} /><span className="toggle" /></label>
          <p className="hint">Edge sizes use original video pixels. Hair, glass, and motion blur may need cleanup in your editor.</p>
        </section>
        <section><div className="section-label"><Cpu size={13} /> PROCESSING</div><label className="field">Model<select value={project?.model ?? 'tiny'} disabled={!project || !!busy} onChange={event => void updateSettings({ model: event.target.value })}><option value="tiny">Fast · SAM 2.1 Tiny</option><option value="base_plus">Quality · SAM 2.1 Base+</option></select></label>
          {selectedModel && !selectedModel.installed && <button className="download-model" disabled={!!busy} onClick={() => void downloadModel()}><ArrowDownToLine size={14} /><span>Download model<small>{Math.round(selectedModel.size / 1_000_000)} MB · one-time download</small></span></button>}
          {selectedModel?.installed && <button className="text-button" disabled={!!busy} onClick={() => void downloadModel()}><Check size={12} /> Model installed · Verify / repair</button>}
          <label className="field">Processor<select value={project?.device ?? 'auto'} disabled={!project || !!busy} onChange={event => void updateSettings({ device: event.target.value })}><option value="auto">Automatic</option><option value="cpu">CPU</option><option value="cuda" disabled={!hello?.capabilities.cuda_available}>NVIDIA GPU</option></select></label>
          <div className="processor-note"><span className="tiny-dot" />{hello?.capabilities.cuda_available ? hello.capabilities.cuda_device : 'CPU processing available'}</div>
          <p className="hint">CPU exports take longer. You can cancel at any time without losing your selections.</p>
        </section>
        <section className="export-section"><div className="section-label"><span>04</span> TAKE IT WITH YOU</div><label className="field">Export format<select value={format} onChange={event => setFormat(event.target.value as typeof format)} disabled={!!busy}><option value="prores">Transparent video · MOV</option><option value="mask_sequence">Mask sequence · PNG</option></select></label>
          <div className="export-details"><div><span>Codec</span><strong>{format === 'prores' ? 'ProRes 4444' : '16-bit grayscale'}</strong></div><div><span>Resolution</span><strong>{project ? `${project.media.width} × ${project.media.height}` : 'Source resolution'}</strong></div><div><span>{format === 'prores' ? 'Audio' : 'Timing'}</span><strong>{format === 'prores' ? project?.media.has_audio ? 'Source audio' : 'No audio' : 'Included as JSON'}</strong></div></div>
          <button className="primary export-button" disabled={!project || !!busy || completed !== selectedCount} onClick={() => void exportVideo()}><ArrowDownToLine size={17} /> Export {format === 'prores' ? 'cutout' : 'masks'}</button>
          <span className="export-hint">{project && completed < selectedCount ? `${completed} of ${selectedCount} frames ready` : 'Ready for DaVinci Resolve & more'}</span>
        </section>
        <div className="right-footer"><Layers2 size={17} /><p>A small tool for<br /><strong>your next big idea.</strong></p></div>
      </aside>
    </div>
    <footer className="statusbar"><span><span className="tiny-dot" />{busy ? progress?.stage ?? 'Working' : desktop ? hello ? 'Ready' : 'Starting processing runtime…' : 'Desktop interface preview'}<span className="status-separator">/</span>{project ? project.name : 'No project open'}</span><span>{project ? 'Changes saved locally' : 'Free & open source'}<span className="status-separator">/</span>v{appVersion}</span></footer>
    {notice && <div className={`notice ${notice.error ? 'error' : ''}`} role={notice.error ? 'alert' : 'status'}>{notice.error ? <CircleHelp size={19} /> : <Check size={19} />}<p>{notice.message}</p><button aria-label="Dismiss message" onClick={() => setNotice(null)}><X size={17} /></button></div>}
    {help && <div className="modal-backdrop" onClick={() => setHelp(false)}><div className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={event => event.stopPropagation()}><button className="modal-close icon-button" aria-label="Close help" onClick={() => setHelp(false)}><X size={20} /></button><span className="eyebrow">A QUICK START</span><h2 id="help-title">A subject. A few strokes.<br />A new possibility.</h2><ol><li><strong>Import</strong> a short SDR video. Choose a frame where your subject is clearly visible.</li><li><strong>Select</strong> with Keep strokes or a box. Remove strokes exclude unwanted areas.</li><li><strong>Track both ways.</strong> Add correction strokes on difficult frames, then retrack from a selection frame.</li><li><strong>Export</strong> a transparent MOV or a mask sequence at the original resolution.</li></ol><p>Masked playback is a frame-by-frame review and may run below real time. Use Original for normal video playback with audio.</p><div className="keyboard-help"><span><kbd>1</kbd> Keep</span><span><kbd>2</kbd> Remove</span><span><kbd>B</kbd> Box</span><span><kbd>← →</kbd> Step</span><span><kbd>Space</kbd> Play</span></div><p className="hint">In Resolve, set the MOV alpha mode to Straight if needed. Import PNG masks as a sequence at the frame rate in timing.json. A .cutout project references your original video; keep that file in place.</p></div></div>}
  </div>;
}
