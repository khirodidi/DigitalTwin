// =============================================================================
// frontend/src/components/BlueprintUpload.jsx
//
// Shared blueprint uploader used by the Setup screen and the Configuration
// page. Uses XMLHttpRequest rather than fetch() so it can report real upload
// progress and enforce a hard timeout — a plain fetch() has no timeout, so a
// stalled request leaves the UI showing "Uploading…" forever.
//
// Failure modes surfaced explicitly:
//   • network unreachable  • request timed out
//   • 413 payload too large (nginx client_max_body_size)
//   • 500 directory not writable
// =============================================================================

import { useState, useRef } from "react";

const API     = process.env.REACT_APP_API_URL || "http://localhost:8000";
const TIMEOUT = 60000;                       // 60 s hard cap
const MAX_MB  = 10;

export default function BlueprintUpload({ value, onChange, compact = false }) {
  const [progress, setProgress] = useState(null);   // null | 0-100
  const [err,      setErr]      = useState(null);
  const [drag,     setDrag]     = useState(false);
  const fileRef = useRef();
  const xhrRef  = useRef();

  const src = value
    ? (value.startsWith("http") ? value : `${API}${value}`)
    : null;

  function upload(file) {
    if (!file) return;
    setErr(null);

    if (!file.type.startsWith("image/")) {
      setErr(`"${file.name}" is not an image file`); return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setErr(`File is ${(file.size / 1e6).toFixed(1)} MB — maximum is ${MAX_MB} MB`);
      return;
    }
    if (file.size === 0) { setErr("That file is empty"); return; }

    const fd  = new FormData();
    fd.append("file", file);

    const xhr = new XMLHttpRequest();
    xhrRef.current = xhr;
    xhr.open("POST", `${API}/api/config/factory/blueprint`);
    xhr.timeout = TIMEOUT;

    xhr.upload.onprogress = e => {
      if (e.lengthComputable) {
        setProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      setProgress(null);
      xhrRef.current = null;
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const d = JSON.parse(xhr.responseText);
          onChange && onChange(d.blueprint_url);
        } catch {
          setErr("Server returned an unexpected response");
        }
      } else if (xhr.status === 413) {
        setErr("Rejected by the web server as too large. " +
               "Try a smaller image, or raise client_max_body_size in nginx.conf.");
      } else if (xhr.status === 0) {
        setErr(`Cannot reach the backend at ${API}. Is it running?`);
      } else {
        let msg = xhr.responseText || `HTTP ${xhr.status}`;
        try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
        setErr(msg);
      }
    };

    xhr.onerror = () => {
      setProgress(null); xhrRef.current = null;
      setErr(`Network error reaching ${API}. Check the backend and CORS settings.`);
    };

    xhr.ontimeout = () => {
      setProgress(null); xhrRef.current = null;
      setErr(`Upload timed out after ${TIMEOUT / 1000}s. ` +
             `The backend may be unreachable or the file too large.`);
    };

    setProgress(0);
    xhr.send(fd);
  }

  function cancel() {
    xhrRef.current?.abort();
    xhrRef.current = null;
    setProgress(null);
    setErr("Upload cancelled");
  }

  async function remove() {
    if (!window.confirm("Remove the current blueprint image?")) return;
    try {
      await fetch(`${API}/api/config/factory/blueprint`, { method: "DELETE" });
      onChange && onChange("");
    } catch (e) {
      setErr("Could not remove: " + e.message);
    }
  }

  async function diagnose() {
    try {
      const d = await fetch(`${API}/api/config/factory/blueprint/status`)
                      .then(r => r.json());
      alert(
        `Blueprint storage diagnostics\n\n` +
        `Directory : ${d.directory}\n` +
        `Writable  : ${d.writable ? "yes" : "NO — " + (d.error || "unknown")}\n` +
        `Files     : ${d.files?.length || 0}\n` +
        `Max size  : ${(d.max_bytes / 1e6).toFixed(0)} MB\n` +
        `Allowed   : ${(d.allowed || []).join(", ")}\n\n` +
        `API URL   : ${API}`
      );
    } catch (e) {
      alert(`Cannot reach the backend at ${API}\n\n${e.message}\n\n` +
            `Check that the backend container is running and that\n` +
            `REACT_APP_API_URL points at it.`);
    }
  }

  const busy = progress !== null;

  const btn = (c = "#6366f1") => ({
    padding: "4px 11px", fontSize: 10, fontWeight: 600, fontFamily: "monospace",
    border: `1px solid ${c}`, borderRadius: 6, background: `${c}22`,
    color: c, cursor: "pointer",
  });

  return (
    <div>
      <div
        onDragOver={e => { e.preventDefault(); if (!busy) setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => {
          e.preventDefault(); setDrag(false);
          if (!busy) upload(e.dataTransfer.files?.[0]);
        }}
        onClick={() => !busy && fileRef.current?.click()}
        style={{
          border: `2px dashed ${drag ? "#6366f1" : value ? "#22c55e55" : "#334155"}`,
          borderRadius: 10,
          padding: src ? 12 : (compact ? 24 : 38),
          textAlign: "center",
          cursor: busy ? "wait" : "pointer",
          background: drag ? "#6366f111" : "#050c1a",
          transition: "all .15s",
        }}>
        <input ref={fileRef} type="file" accept="image/*"
          style={{ display: "none" }}
          onChange={e => { upload(e.target.files?.[0]); e.target.value = ""; }} />

        {busy ? (
          <div>
            <div style={{ fontSize: 12, color: "#a5b4fc", marginBottom: 10,
              fontFamily: "monospace" }}>
              Uploading… {progress}%
            </div>
            <div style={{ height: 6, background: "#1e293b", borderRadius: 3,
              overflow: "hidden", marginBottom: 12 }}>
              <div style={{ height: "100%", width: `${progress}%`,
                background: "#6366f1", transition: "width .2s" }} />
            </div>
            <button onClick={e => { e.stopPropagation(); cancel(); }}
              style={btn("#ef4444")}>Cancel</button>
          </div>
        ) : src ? (
          <>
            <img src={src} alt="Factory blueprint"
              onError={() => setErr("Image saved but cannot be displayed — " +
                                    "check that /static is reachable")}
              style={{ maxWidth: "100%", maxHeight: compact ? 200 : 260,
                borderRadius: 6, border: "1px solid #1e293b" }} />
            <div style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>
              Click or drop another image to replace
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: compact ? 24 : 30, marginBottom: 8 }}>📐</div>
            <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 5 }}>
              {drag ? "Drop the floor plan here"
                    : "Click to choose, or drag an image here"}
            </div>
            <div style={{ fontSize: 10, color: "#475569" }}>
              PNG · JPG · GIF · WEBP · SVG — max {MAX_MB} MB
            </div>
          </>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginTop: 10,
        alignItems: "center", flexWrap: "wrap" }}>
        {src && !busy && (
          <>
            <button style={btn("#6366f1")}
              onClick={() => fileRef.current?.click()}>Replace</button>
            <button style={btn("#ef4444")} onClick={remove}>Remove</button>
          </>
        )}
        <button style={{ ...btn("#64748b"), marginLeft: "auto" }}
          onClick={diagnose} title="Check storage and connectivity">
          Diagnose
        </button>
      </div>

      {/* Error */}
      {err && (
        <div style={{ marginTop: 10, padding: "10px 13px", borderRadius: 8,
          background: "#7f1d1d33", border: "1px solid #ef4444",
          color: "#fca5a5", fontSize: 11, lineHeight: 1.6 }}>
          <b>Upload failed.</b> {err}
          <button style={{ ...btn("#6b7280"), marginLeft: 10 }}
            onClick={() => setErr(null)}>Dismiss</button>
        </div>
      )}
    </div>
  );
}
