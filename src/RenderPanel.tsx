import { ArrowDownToLine, Eye } from 'lucide-react';
import type { Project, RenderSettings } from './types';
import { outputSize, RESOLUTIONS } from './rendering';
import './rendering.css';

export function RenderPanel({ project, settings, busy, completed, selectedCount, onChange, onExport, onPreview, onHelp }: {
  project: Project | null; settings: RenderSettings; busy: boolean; completed: number; selectedCount: number;
  onChange: (changes: Partial<RenderSettings>) => void; onExport: () => void; onPreview: () => void; onHelp: () => void;
}) {
  const sequence = settings.format === 'png_sequence' || settings.format === 'mask_sequence';
  const masks = settings.format === 'mask_sequence';
  const dimensions = project ? outputSize(project.media.width, project.media.height, settings.resolution) : null;
  const upscaled = project && dimensions && (dimensions[0] > project.media.width || dimensions[1] > project.media.height);
  const oddMp4 = settings.format === 'mp4' && dimensions?.some(size => size % 2 !== 0);
  const disabled = !project || busy;
  const codec = { prores: 'ProRes 4444', mp4: 'H.264', png_sequence: 'Lossless PNG', mask_sequence: '16-bit grayscale' }[settings.format];
  return <section className="export-section">
    <div className="section-label"><span>04</span> RENDER & EXPORT</div>
    <label className="field">Export format<select aria-label="Export format" aria-describedby="render-format-help" value={settings.format} disabled={disabled} onChange={event => onChange({ format: event.target.value as RenderSettings['format'] })}>
      <option value="prores">Editing video · MOV</option><option value="mp4">Video · MP4</option>
      <option value="png_sequence">Image sequence · PNG</option><option value="mask_sequence">Mask sequence · PNG</option>
    </select><small id="render-format-help">{masks ? 'White keeps the subject; black removes it.' : settings.format === 'prores' ? 'Supports transparency. Best for further editing.' : settings.format === 'mp4' ? 'Smaller files for playback and sharing.' : 'Lossless frames with transparency or a color background.'}</small></label>
    {!masks && <>
      <label className="field">Background<select value={settings.background} disabled={disabled} onChange={event => onChange({ background: event.target.value as RenderSettings['background'] })}>
        <option value="transparent" disabled={settings.format === 'mp4'}>Transparent</option><option value="green">Green screen</option>
        <option value="blue">Blue screen</option><option value="black">Black</option><option value="white">White</option><option value="custom">Custom color</option>
      </select></label>
      {settings.background === 'custom' && <label className="field">Background color<div className="color-field"><input type="color" aria-label="Background color" value={settings.color} disabled={disabled} onChange={event => onChange({ color: event.target.value })} /><code>{settings.color.toUpperCase()}</code></div></label>}
      <button className="text-button render-preview-button" disabled={disabled} onClick={onPreview}><Eye size={13} /> Preview background</button>
    </>}
    <label className="field">Output resolution<select aria-label="Output resolution" aria-describedby="render-resolution-help" value={settings.resolution} disabled={disabled} onChange={event => onChange({ resolution: event.target.value as RenderSettings['resolution'] })}>
      {RESOLUTIONS.map(preset => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
    </select><small id="render-resolution-help">{settings.resolution === 'native' ? 'Uses the original video pixels.' : 'Fits the selected size, preserving aspect ratio and portrait orientation.'}</small></label>
    {upscaled && <p className="render-note">This enlarges your video. It does not add new detail.</p>}
    {!sequence && <>
      <label className="field">Render quality<select value={settings.quality} disabled={disabled} onChange={event => onChange({ quality: event.target.value as RenderSettings['quality'] })}>
        <option value="standard">Standard · smaller file</option><option value="high">High · recommended</option><option value="maximum">Maximum · larger file</option>
      </select></label>
      <label className="toggle-label render-audio"><span>Include source audio</span><input type="checkbox" checked={settings.audio && !!project?.media.has_audio} disabled={disabled || !project?.media.has_audio} onChange={event => onChange({ audio: event.target.checked })} /><span className="toggle" /></label>
    </>}
    <div className="export-details">
      <div><span>Codec</span><strong>{codec}</strong></div>
      <div><span>Output size</span><strong>{dimensions ? `${dimensions[0]} × ${dimensions[1]}` : 'Source resolution'}</strong></div>
      <div><span>Frame rate</span><strong>{project ? `${(project.media.fps_num / project.media.fps_den).toFixed(3).replace(/\.?0+$/, '')} fps` : 'Project frame rate'}</strong></div>
      <div><span>{sequence ? 'Timing' : 'Audio'}</span><strong>{sequence ? 'Included as JSON' : settings.audio && project?.media.has_audio ? 'Source audio' : 'No audio'}</strong></div>
    </div>
    {oddMp4 && <p className="render-note" role="status">MP4 needs even dimensions. Choose a size preset, or MOV/PNG to keep exact native pixels.</p>}
    <button className="primary export-button" disabled={disabled || completed !== selectedCount || !!oddMp4} onClick={onExport}><ArrowDownToLine size={17} /> Export {masks ? 'masks' : settings.background === 'transparent' ? 'cutout' : 'video'}</button>
    <span className="export-hint">{project && completed < selectedCount ? `${completed} of ${selectedCount} frames ready` : 'Render settings reuse your tracked masks'}</span>
    <button className="text-button render-help" onClick={onHelp}>Rendering guide</button>
  </section>;
}
