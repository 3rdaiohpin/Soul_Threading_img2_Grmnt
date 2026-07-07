import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "@/App.css";
import {
  ArrowSquareOut,
  CircleNotch,
  CloudArrowUp,
  Download,
  MagnifyingGlass,
  Play,
  ShieldCheck,
  Sparkle,
  Warning,
  WarningOctagon,
} from "@phosphor-icons/react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const LEVEL_CLASS = { INFO: "term-INFO", OK: "term-OK", WARN: "term-WARN", ERROR: "term-ERROR" };

function useOneShotFetch(url) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    if (!url) return () => { alive = false; };
    axios.get(url).then((r) => { if (alive) setData(r.data); }).catch(() => {});
    return () => { alive = false; };
  }, [url]);
  return data;
}

function Header({ modelStatus }) {
  const active = modelStatus?.active_backend || "…";
  const smart = modelStatus?.smart_available;
  return (
    <header className="border-b border-[var(--st-border)] flex items-center justify-between px-4 py-2.5" data-testid="app-header">
      <div className="flex items-center gap-3">
        <div className="w-6 h-6 bg-[var(--st-amber)] flex items-center justify-center">
          <Sparkle size={14} weight="fill" className="text-black" />
        </div>
        <div className="flex flex-col leading-none">
          <div className="text-[13px] font-semibold tracking-wide">SOUL·THREADING</div>
          <div className="mono text-[10px] text-[var(--st-text-mut)]">smart_ai_img2garment_mapper // v1.0.0</div>
        </div>
      </div>
      <div className="flex items-center gap-4 mono text-[11px]">
        <div className="flex items-center gap-2" data-testid="active-backend-chip">
          <span className={`w-1.5 h-1.5 ${smart ? "bg-[var(--st-green)]" : "bg-[var(--st-amber)]"}`}></span>
          <span className="text-[var(--st-text-2)]">backend</span>
          <span className="text-[var(--st-text)]">{active}</span>
        </div>
        <a href="https://huggingface.co/spaces" target="_blank" rel="noreferrer" className="text-[var(--st-text-2)] hover:text-[var(--st-amber)] inline-flex items-center gap-1" data-testid="hf-link">
          hf spaces <ArrowSquareOut size={12} />
        </a>
      </div>
    </header>
  );
}

function Panel({ title, subtitle, children, actions, testId, className = "", padded = true }) {
  return (
    <section className={`st-panel flex flex-col ${className}`} data-testid={testId} style={{ height: "100%" }}>
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--st-border)] flex-shrink-0">
        <div className="flex flex-col leading-tight">
          <div className="st-label">{title}</div>
          {subtitle && <div className="mono text-[10px] text-[var(--st-text-mut)] mt-0.5">{subtitle}</div>}
        </div>
        {actions}
      </div>
      <div className={`${padded ? "p-3" : ""} flex-1 min-h-0 relative`}>{children}</div>
    </section>
  );
}

function UploadPanel({ onUploaded, current }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const upload = async (file) => {
    setErr(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await axios.post(`${API}/upload-artwork`, fd);
      const url = URL.createObjectURL(file);
      onUploaded({ ...r.data, preview_url: url, name: file.name });
    } catch (e) {
      setErr(e?.response?.data?.detail || "upload failed");
    } finally { setBusy(false); }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) upload(f);
  };

  return (
    <Panel title="01 · Source Artwork" subtitle={current ? `${current.name} · ${(current.bytes/1024).toFixed(1)} KB` : "drop image / png · jpg · webp"} testId="panel-upload">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`checker w-full aspect-square cursor-pointer border ${dragging ? "border-[var(--st-amber)]" : "border-[var(--st-border)]"} flex flex-col items-center justify-center relative`}
        data-testid="upload-dropzone"
      >
        {current?.preview_url ? (
          <img src={current.preview_url} alt="artwork" className="w-full h-full object-contain" data-testid="artwork-preview" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-[var(--st-text-2)]">
            <CloudArrowUp size={32} weight="thin" />
            <div className="mono text-[11px]">drop or click to select artwork</div>
          </div>
        )}
        {busy && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <CircleNotch size={22} className="animate-spin text-[var(--st-amber)]" />
          </div>
        )}
      </div>
      <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" data-testid="upload-input"
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      {err && <div className="mt-2 text-[11px] text-[var(--st-red)] mono" data-testid="upload-error">{err}</div>}
    </Panel>
  );
}

function AnalyzePanel({ artwork, analysis, onAnalyze, useSmartHint, setUseSmartHint, busy }) {
  const a = analysis?.analysis;
  return (
    <Panel
      title="02 · Analyze Artwork"
      subtitle="Subject · Face · Text · Colors · Saliency"
      testId="panel-analyze"
      actions={
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--st-text-2)] cursor-pointer" data-testid="toggle-smart-hint">
            <input type="checkbox" className="accent-[var(--st-amber)]" checked={useSmartHint} onChange={(e) => setUseSmartHint(e.target.checked)} />
            <span className="mono">smart_hint</span>
          </label>
          <button className="st-btn st-btn-primary" onClick={onAnalyze} disabled={!artwork || busy} data-testid="btn-analyze">
            {busy ? <CircleNotch size={12} className="animate-spin" /> : <MagnifyingGlass size={12} />}
            analyze
          </button>
        </div>
      }
    >
      {!analysis ? (
        <div className="h-full flex items-center justify-center text-[var(--st-text-mut)] mono text-[11px]">
          upload artwork then run analyze
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 h-full">
          <div className="st-panel-2 flex flex-col">
            <div className="st-label px-2 py-1 border-b border-[var(--st-border)] flex items-center justify-between">
              <span>saliency heatmap</span>
              <span className="mono normal-case text-[var(--st-text-mut)]">{a.canvas_px.width}×{a.canvas_px.height}</span>
            </div>
            <div className="flex-1 min-h-0 checker relative">
              <img src={a.heatmap_png_b64} alt="heatmap" className="absolute inset-0 w-full h-full object-contain" data-testid="analysis-heatmap"/>
            </div>
          </div>
          <div className="st-panel-2 flex flex-col">
            <div className="st-label px-2 py-1 border-b border-[var(--st-border)]">detections</div>
            <div className="p-2 flex flex-col gap-1.5 mono text-[11px] flex-1 min-h-0">
              <div className="flex justify-between"><span className="text-[var(--st-text-2)]">archetype</span><span className="text-[var(--st-amber)] font-semibold" data-testid="analysis-archetype">{analysis.archetype.archetype}</span></div>
              <div className="flex justify-between"><span className="text-[var(--st-text-2)]">faces</span><span>{a.faces.length}</span></div>
              <div className="flex justify-between"><span className="text-[var(--st-text-2)]">text_regions</span><span>{a.text_regions.length}</span></div>
              <div className="flex justify-between"><span className="text-[var(--st-text-2)]">subject_bbox</span><span>{a.primary_subject.w}×{a.primary_subject.h}</span></div>
              <div className="flex justify-between"><span className="text-[var(--st-text-2)]">smart_hint</span><span className="truncate max-w-[110px]">{analysis.smart_hint?.archetype || analysis.smart_hint?.error || "—"}</span></div>
              <div className="mt-2 border-t border-[var(--st-border)] pt-2">
                <div className="st-label mb-1">dominant colors</div>
                <div className="flex gap-1 flex-wrap" data-testid="analysis-colors">
                  {a.dominant_colors.map((c) => (
                    <div key={c.hex} className="flex flex-col items-center">
                      <div className="w-6 h-6 border border-[var(--st-border)]" style={{ background: c.hex }} title={c.hex}></div>
                      <div className="mono text-[9px] mt-0.5 text-[var(--st-text-mut)]">{Math.round(c.share*100)}%</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-2 border-t border-[var(--st-border)] pt-2">
                <div className="st-label mb-1">archetype scores</div>
                {Object.entries(analysis.archetype.scores).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center gap-2">
                    <span className="text-[var(--st-text-2)] truncate">{k}</span>
                    <div className="flex-1 h-1 bg-[var(--st-border)]"><div className="h-1 bg-[var(--st-amber)]" style={{ width: `${Math.min(100, v)}%` }}></div></div>
                    <span className="w-8 text-right">{v.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function GarmentGrid({ garments, scored, selected, onSelect }) {
  const scoreMap = useMemo(() => {
    const m = {};
    (scored || []).forEach((s) => { m[s.product_id] = s; });
    return m;
  }, [scored]);

  return (
    <Panel title="03 · Garment Library" subtitle={`${garments?.length || 0} templates · scroll to see all · fit-scored against archetype`} testId="panel-garments" padded={false}>
      <div className="relative w-full h-full">
        <div className="absolute inset-0 overflow-y-scroll scrollarea" data-testid="garment-scroller">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-[var(--st-border)]">
            {(garments || []).map((g) => {
              const s = scoreMap[g.product_id];
              const isSel = selected === g.product_id;
              return (
                <button
                  key={g.product_id}
                  onClick={() => onSelect(g.product_id)}
                  data-testid={`garment-tile-${g.product_id}`}
                  className={`text-left p-2.5 bg-[var(--st-surface)] hover:bg-[var(--st-surface-2)] transition-colors ${isSel ? "outline outline-2 outline-[var(--st-amber)] -outline-offset-2" : ""}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-[11px] font-semibold leading-tight">{g.display_name.replace(/-Design-Template/gi, "").replace(/-/g, " ")}</div>
                    {s && (
                      <div className="mono text-[10px] px-1.5 py-0.5 border border-[var(--st-border)]" style={{ color: s.composite_score >= 75 ? "var(--st-green)" : s.composite_score >= 60 ? "var(--st-amber)" : "var(--st-text-2)" }}>
                        {s.composite_score.toFixed(0)}
                      </div>
                    )}
                  </div>
                  <div className="mono text-[9px] text-[var(--st-text-mut)] mt-1 uppercase tracking-wide">{g.garment_type.replace(/_/g, " ")}</div>
                  <div className="mono text-[9px] text-[var(--st-text-2)] mt-1 flex gap-1 flex-wrap">
                    <span className="border border-[var(--st-border)] px-1">{g.piece_count} pcs</span>
                    {g.has_front && <span className="border border-[var(--st-border)] px-1">front</span>}
                    {g.has_back && <span className="border border-[var(--st-border)] px-1">back</span>}
                    {g.has_pocket && <span className="border border-[var(--st-border)] px-1 text-[var(--st-cyan)]">pkt</span>}
                    {g.has_hood && <span className="border border-[var(--st-border)] px-1">hood</span>}
                    {g.has_sleeves && <span className="border border-[var(--st-border)] px-1">slv</span>}
                  </div>
                  {s?.preferred_for_archetype && (
                    <div className="mono text-[9px] text-[var(--st-amber)] mt-1">★ recommended</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function MasterPreview({ job }) {
  const [kind, setKind] = useState("composed");
  if (!job) {
    return (
      <Panel title="04 · Master Composition" subtitle="deterministic Pillow · guides + safe zones" testId="panel-master">
        <div className="h-full flex items-center justify-center text-[var(--st-text-mut)] mono text-[11px]">
          select a garment and run map
        </div>
      </Panel>
    );
  }
  const panels = job.composed_panels || [];
  return (
    <Panel
      title="04 · Master Composition"
      subtitle={`${job.product_name} · ${job.archetype.archetype}`}
      testId="panel-master"
      actions={
        <div className="flex items-center gap-1 border border-[var(--st-border)]">
          <button data-testid="tab-composed" className={`px-2 py-1 text-[10px] mono ${kind === "composed" ? "bg-[var(--st-amber)] text-black" : "text-[var(--st-text-2)]"}`} onClick={() => setKind("composed")}>composed</button>
          <button data-testid="tab-guides" className={`px-2 py-1 text-[10px] mono ${kind === "guides" ? "bg-[var(--st-amber)] text-black" : "text-[var(--st-text-2)]"}`} onClick={() => setKind("guides")}>guides</button>
        </div>
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 h-full overflow-y-auto scrollarea">
        {panels.map((p) => (
          <div key={p} className="st-panel-2 flex flex-col" data-testid={`master-panel-${p}`}>
            <div className="flex items-center justify-between px-2 py-1 border-b border-[var(--st-border)]">
              <div className="mono text-[10px] uppercase">{p.replace(/_/g, " ")}</div>
              <div className="mono text-[9px] text-[var(--st-text-mut)]">{kind}</div>
            </div>
            <div className="flex-1 min-h-[140px] checker relative">
              <img src={`${API}/jobs/${job.job_id}/panel/${p}?kind=${kind}`} alt={p} className="absolute inset-0 w-full h-full object-contain" />
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function QualityGauge({ job }) {
  if (!job) return (
    <Panel title="05 · Quality Gate" subtitle="validator + retry controller" testId="panel-quality">
      <div className="h-full flex items-center justify-center text-[var(--st-text-mut)] mono text-[11px]">no run yet</div>
    </Panel>
  );
  const q = job.quality_report;
  const overall = q.overall;
  const pass = q.passed;
  return (
    <Panel title="05 · Quality Gate" subtitle={`overall ${overall} / 100 · ${pass ? "PASS" : "FAIL"}`} testId="panel-quality">
      <div className="flex flex-col gap-3 h-full">
        <div className="flex items-center gap-3">
          <div className="relative w-20 h-20 shrink-0" data-testid="quality-overall">
            <svg viewBox="0 0 36 36" className="w-full h-full">
              <path d="M18 2 a 16 16 0 0 1 0 32 a 16 16 0 0 1 0 -32" fill="none" stroke="var(--st-border)" strokeWidth="3"/>
              <path d="M18 2 a 16 16 0 0 1 0 32 a 16 16 0 0 1 0 -32" fill="none" stroke={pass ? "var(--st-green)" : "var(--st-red)"} strokeWidth="3" strokeDasharray={`${overall}, 100`} strokeLinecap="butt"/>
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center leading-tight">
              <div className="mono text-lg font-bold">{Math.round(overall)}</div>
              <div className="mono text-[9px] text-[var(--st-text-mut)]">score</div>
            </div>
          </div>
          <div className="flex-1 space-y-1 mono text-[11px]">
            {Object.entries(q.scores).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center gap-2">
                <span className="text-[var(--st-text-2)] truncate">{k}</span>
                <div className="flex-1 h-1 bg-[var(--st-border)]"><div className="h-1" style={{ width: `${Math.min(100, v*10)}%`, background: v >= 8 ? "var(--st-green)" : v >= 5 ? "var(--st-amber)" : "var(--st-red)" }}></div></div>
                <span className="w-8 text-right">{v.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-1">
          <div className="st-label mb-1">hard fails</div>
          {q.hard_fails.length === 0 ? (
            <div className="mono text-[11px] text-[var(--st-green)] flex items-center gap-1"><ShieldCheck size={12}/> none</div>
          ) : (
            <div className="flex flex-wrap gap-1">
              {q.hard_fails.map((f) => (
                <span key={f} className="mono text-[10px] px-1.5 py-0.5 border border-[var(--st-red)] text-[var(--st-red)]"><WarningOctagon size={10} className="inline mr-1"/>{f}</span>
              ))}
            </div>
          )}
        </div>
        <div>
          <div className="st-label mb-1">retry controller</div>
          {job.retry?.needed ? (
            <div className="mono text-[11px] text-[var(--st-amber)] flex items-center gap-1"><Warning size={12}/> adjustments applied: {job.retry.adjustments?.join(", ")}</div>
          ) : (
            <div className="mono text-[11px] text-[var(--st-text-2)]">no retry needed</div>
          )}
        </div>
      </div>
    </Panel>
  );
}

function ProcessLog({ logs }) {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "instant" }); }, [logs?.length]);
  return (
    <Panel title="06 · Process Log" subtitle="pipeline stages" testId="panel-log" padded={false}>
      <div className="bg-black h-full overflow-y-auto scrollarea mono text-[11px] px-3 py-2" data-testid="process-log">
        {(logs || []).length === 0 ? (
          <div className="text-[var(--st-text-mut)]">terminal ready<span className="blink">_</span></div>
        ) : logs.map((e) => (
          <div key={`${e.ts}-${e.stage}-${e.message}`} className={`term-line ${LEVEL_CLASS[e.level] || ""}`}>
            <span className="text-[var(--st-text-mut)]">[{e.ts}]</span>{" "}
            <span className="font-semibold">{e.level}</span>{" "}
            <span className="text-[var(--st-text-mut)]">{e.stage.padEnd(12,' ')}</span>{" · "}
            {e.message}
          </div>
        ))}
        <div ref={bottomRef}/>
      </div>
    </Panel>
  );
}

function ActionBar({ onMap, canMap, busy, job, selected }) {
  const downloadUrl = job ? `${API}/jobs/${job.job_id}/download` : "#";
  return (
    <div className="border-t border-[var(--st-border)] px-4 py-2 flex items-center justify-between bg-[var(--st-surface)]" style={{ paddingRight: "220px", position: "relative", zIndex: 60 }}>
      <div className="mono text-[11px] text-[var(--st-text-2)] truncate max-w-[45%]" data-testid="selection-summary">
        {selected ? <>target: <span className="text-[var(--st-text)]">{selected}</span></> : "no garment selected"}
        {job && <> · job <span className="text-[var(--st-amber)]">{job.job_id}</span> · panels <span className="text-[var(--st-text)]">{(job.composed_panels||[]).length}</span></>}
      </div>
      <div className="flex items-center gap-2">
        {job && (
          <a className="st-btn st-btn-primary" href={downloadUrl} data-testid="btn-download">
            <Download size={12}/> download zip
          </a>
        )}
        <button className="st-btn" onClick={onMap} disabled={!canMap || busy} data-testid="btn-map">
          {busy ? <CircleNotch size={12} className="animate-spin"/> : <Play size={12} weight="fill"/>}
          run mapping
        </button>
      </div>
    </div>
  );
}

function ModelSidebar({ status }) {
  if (!status) return null;
  return (
    <Panel title="AI Model Manager" subtitle="analysis backend status" testId="panel-model" padded={false} className="h-full">
      <div className="p-2.5 border-b border-[var(--st-border)] mono text-[11px]" data-testid="model-active">
        <div className="flex justify-between"><span className="text-[var(--st-text-2)]">active</span><span className="text-[var(--st-amber)]">{status.active_backend}</span></div>
        <div className="flex justify-between"><span className="text-[var(--st-text-2)]">smart_available</span><span>{String(status.smart_available)}</span></div>
        <div className="flex justify-between"><span className="text-[var(--st-text-2)]">torch</span><span>{String(status.torch_installed)}</span></div>
      </div>
      <div className="p-2 space-y-1 overflow-y-auto scrollarea flex-1 min-h-0">
        {status.detectors.map((d) => (
          <div key={d.name} className="flex items-start gap-2 text-[10px] mono">
            <span className={`mt-1 w-1.5 h-1.5 shrink-0 ${d.available ? "bg-[var(--st-green)]" : "bg-[var(--st-border)]"}`}></span>
            <div className="flex-1 min-w-0">
              <div className="text-[var(--st-text)] truncate">{d.name}</div>
              <div className="text-[var(--st-text-mut)] text-[9px] truncate">{d.type} · {d.note}</div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default function App() {
  const [artwork, setArtwork] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [garments, setGarments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [job, setJob] = useState(null);
  const [useSmartHint, setUseSmartHint] = useState(false);
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [mapBusy, setMapBusy] = useState(false);

  const modelStatus = useOneShotFetch(`${API}/model-status`);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/garments`).then((r) => { if (alive) setGarments(r.data.items); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const doAnalyze = async () => {
    if (!artwork) return;
    setAnalyzeBusy(true);
    setJob(null);
    try {
      const fd = new FormData();
      fd.append("artwork_id", artwork.artwork_id);
      fd.append("use_smart_hint", String(useSmartHint));
      const r = await axios.post(`${API}/analyze`, fd);
      setAnalysis(r.data);
      // auto-select top recommended
      if (r.data.recommended_garments?.[0]) setSelected(r.data.recommended_garments[0].product_id);
    } catch (e) { console.error(e); }
    setAnalyzeBusy(false);
  };

  const doMap = async () => {
    if (!artwork || !selected) return;
    setMapBusy(true);
    try {
      const r = await axios.post(`${API}/map`, {
        artwork_id: artwork.artwork_id,
        product_id: selected,
        use_smart_hint: useSmartHint,
      });
      setJob(r.data);
    } catch (e) { console.error(e); }
    setMapBusy(false);
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[var(--st-bg)] text-[var(--st-text)] overflow-hidden">
      <Header modelStatus={modelStatus} />
      <div className="flex-1 min-h-0 grid grid-cols-12 gap-px bg-[var(--st-border)]" data-testid="workspace-grid">
        {/* LEFT COLUMN */}
        <div className="col-span-3 flex flex-col gap-px bg-[var(--st-border)] min-h-0">
          <div className="flex-shrink-0 bg-[var(--st-bg)]">
            <UploadPanel current={artwork} onUploaded={(a) => { setArtwork(a); setAnalysis(null); setJob(null); }} />
          </div>
          <div className="flex-1 min-h-0 bg-[var(--st-bg)]">
            <ModelSidebar status={modelStatus} />
          </div>
        </div>
        {/* CENTER COLUMN */}
        <div className="col-span-6 flex flex-col gap-px bg-[var(--st-border)] min-h-0">
          <div className="flex-shrink-0 h-[280px] bg-[var(--st-bg)]">
            <AnalyzePanel
              artwork={artwork}
              analysis={analysis}
              onAnalyze={doAnalyze}
              busy={analyzeBusy}
              useSmartHint={useSmartHint}
              setUseSmartHint={setUseSmartHint}
            />
          </div>
          <div className="flex-1 min-h-0 bg-[var(--st-bg)]">
            <MasterPreview job={job} />
          </div>
        </div>
        {/* RIGHT COLUMN */}
        <div className="col-span-3 flex flex-col gap-px bg-[var(--st-border)] min-h-0 overflow-hidden">
          <div className="flex-1 min-h-[340px] bg-[var(--st-bg)] relative">
            <GarmentGrid garments={garments} scored={analysis?.all_scored} selected={selected} onSelect={setSelected} />
          </div>
          <div className="flex-shrink-0 h-[260px] bg-[var(--st-bg)]">
            <QualityGauge job={job} />
          </div>
          <div className="flex-shrink-0 h-[180px] bg-[var(--st-bg)]">
            <ProcessLog logs={job?.process_log} />
          </div>
        </div>
      </div>
      <ActionBar onMap={doMap} canMap={!!artwork && !!selected} busy={mapBusy} job={job} selected={selected} />
    </div>
  );
}
