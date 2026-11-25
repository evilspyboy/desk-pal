/**
 * Desk-Pal Themes Studio
 * UI Controller for saving, duplicating, switching, exporting, and importing
 * visual themes (scenes, characters, animations, props, palette, card styling).
 */

(function () {
  let themesCache = [];
  let activeThemeId = "cozy_study";

  window.openThemeStudio = function () {
    const modal = document.getElementById("themeStudioModal");
    if (!modal) return;
    modal.style.display = "flex";
    closeThemeSaveEditor();
    refreshThemeList();
  };

  window.closeThemeStudio = function () {
    const modal = document.getElementById("themeStudioModal");
    if (modal) modal.style.display = "none";
    closeThemeSaveEditor();
  };

  window.refreshThemeList = async function () {
    const container = document.getElementById("themesListContainer");
    const topSelector = document.getElementById("themeSelector");
    const countBadge = document.getElementById("themeCountBadge");

    try {
      const res = await fetch("/api/themes");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      themesCache = data.themes || [];
      activeThemeId = data.active_theme || (themesCache[0] && themesCache[0].id) || "cozy_study";

      if (countBadge) countBadge.textContent = themesCache.length;

      // Update Top Bar dropdown
      if (topSelector) {
        topSelector.innerHTML = "";
        themesCache.forEach((t) => {
          const opt = document.createElement("option");
          opt.value = t.id;
          opt.textContent = `${t.name} (${t.active_scene})`;
          if (t.id === activeThemeId) opt.selected = true;
          topSelector.appendChild(opt);
        });
      }

      if (!container) return;
      if (themesCache.length === 0) {
        container.innerHTML = `
          <div style="background:#191627; border:1px dashed var(--border); border-radius:12px; padding:32px; text-align:center;">
            <div style="font-size:2.4rem; margin-bottom:8px;">🎨</div>
            <div style="font-weight:600; font-size:1.1rem; color:#fff;">No Themes Found</div>
            <div style="color:var(--text-dim); font-size:0.85rem; margin-top:4px;">Save your current visual setup to create your first theme.</div>
          </div>
        `;
        return;
      }

      container.innerHTML = "";
      themesCache.forEach((theme) => {
        const isActive = (theme.id === activeThemeId);
        const card = document.createElement("div");
        card.className = "theme-card";
        card.style.cssText = `
          background: ${isActive ? "rgba(139, 92, 246, 0.12)" : "#161320"};
          border: 1px solid ${isActive ? "#8b5cf6" : "#362e45"};
          box-shadow: ${isActive ? "0 0 16px rgba(139, 92, 246, 0.25)" : "none"};
          border-radius: 12px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          transition: transform 0.15s ease, border-color 0.15s ease;
        `;

        // Color swatches preview
        const pal = theme.palette || {};
        const swatchesHtml = [
          pal.background ? `rgb(${pal.background.join(",")})` : "#181425",
          pal.surface ? `rgb(${pal.surface.join(",")})` : "#262b44",
          pal.border ? `rgb(${pal.border.join(",")})` : "#5a6988",
          pal.accent ? `rgb(${pal.accent.join(",")})` : "#f0a050",
          pal.green ? `rgb(${pal.green.join(",")})` : "#6abe30",
          pal.blue ? `rgb(${pal.blue.join(",")})` : "#4b69cc",
        ]
          .map(
            (c) =>
              `<div style="width:20px; height:20px; border-radius:50%; background:${c}; border:1px solid rgba(255,255,255,0.2);" title="${c}"></div>`
          )
          .join("");

        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-weight:700; font-size:1.15rem; color:#fff;">${escapeHtml(theme.name)}</span>
                ${
                  isActive
                    ? '<span style="font-size:0.7rem; background:#8b5cf6; color:#fff; font-weight:700; padding:2px 8px; border-radius:12px;">ACTIVE</span>'
                    : ""
                }
                ${
                  theme.is_builtin
                    ? '<span style="font-size:0.7rem; background:#374151; color:#9ca3af; padding:2px 6px; border-radius:10px;">Built-in</span>'
                    : '<span style="font-size:0.7rem; background:#065f46; color:#34d399; padding:2px 6px; border-radius:10px;">Custom</span>'
                }
              </div>
              <div style="font-size:0.78rem; color:var(--text-dim); margin-top:3px; font-family:monospace;">ID: ${escapeHtml(theme.id)}</div>
            </div>
            <div style="display:flex; gap:4px; align-items:center;">
              ${swatchesHtml}
            </div>
          </div>

          <div style="font-size:0.86rem; color:#d1d5db; line-height:1.4;">
            ${escapeHtml(theme.description || "A complete visual theme for Desk-Pal.")}
          </div>

          <div style="display:flex; gap:16px; font-size:0.78rem; color:var(--text-dim); background:rgba(0,0,0,0.25); padding:8px 12px; border-radius:8px;">
            <div>🏞️ Scene: <b style="color:#fff;">${escapeHtml(theme.active_scene)}</b></div>
            <div>👤 Character: <b style="color:#fff;">${escapeHtml(theme.active_character)}</b></div>
            <div>🎨 Card Radius: <b style="color:#fff;">${(theme.card_style && theme.card_style.border_radius) || 14}px</b></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:auto; padding-top:4px;">
            <div style="display:flex; gap:8px;">
              ${
                !isActive
                  ? `<button class="btn btn-primary" onclick="switchTheme('${escapeHtml(theme.id)}')" style="font-size:0.8rem; padding:5px 12px; background:#8b5cf6; border-color:#8b5cf6;">🚀 Apply Theme</button>`
                  : `<button class="btn" disabled style="font-size:0.8rem; padding:5px 12px; opacity:0.6;">✓ Currently Live</button>`
              }
              <button class="btn" onclick="openDuplicateModal('${escapeHtml(theme.id)}', '${escapeHtml(theme.name)}')" style="font-size:0.8rem; padding:5px 10px;">📋 Duplicate</button>
              <button class="btn" onclick="exportTheme('${escapeHtml(theme.id)}')" style="font-size:0.8rem; padding:5px 10px;" title="Download zip package">💾 Export</button>
            </div>
            <div>
              ${
                !theme.is_builtin && !isActive
                  ? `<button class="btn btn-danger" onclick="deleteTheme('${escapeHtml(theme.id)}')" style="font-size:0.8rem; padding:5px 8px;" title="Delete custom theme">🗑️</button>`
                  : ""
              }
            </div>
          </div>
        `;

        container.appendChild(card);
      });
    } catch (err) {
      console.error("Error loading themes:", err);
      if (container) {
        container.innerHTML = `<div style="color:#ef4444; padding:16px;">Failed to load themes: ${escapeHtml(err.message)}</div>`;
      }
    }
  };

  window.switchTheme = async function (themeId) {
    if (!themeId) return;
    const statusEl = document.getElementById("statusMsg") || document.getElementById("themeStudioStatus");
    if (statusEl) statusEl.textContent = `Applying theme '${themeId}'...`;

    try {
      const res = await fetch("/api/themes/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme_id: themeId }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      activeThemeId = data.theme || themeId;

      if (statusEl) {
        statusEl.textContent = `Theme switched to '${data.theme}' successfully!`;
        setTimeout(() => {
          if (statusEl.textContent.includes("Theme switched")) statusEl.textContent = "";
        }, 4000);
      }

      // Re-fetch themes and refresh web studio scene
      refreshThemeList();
      if (typeof fetchConfig === "function") {
        fetchConfig();
      } else if (typeof switchEditorScene === "function" && data.active_scene) {
        switchEditorScene(data.active_scene);
      }
    } catch (err) {
      alert("Failed to switch theme: " + err.message);
      if (statusEl) statusEl.textContent = "Theme switch error: " + err.message;
    }
  };

  window.openSaveCurrentThemeModal = function () {
    const editor = document.getElementById("themeSaveEditorView");
    if (!editor) return;
    const nameInput = document.getElementById("newThemeName");
    const idInput = document.getElementById("newThemeId");
    const descInput = document.getElementById("newThemeDesc");
    const radiusInput = document.getElementById("newThemeRadius");

    if (nameInput) nameInput.value = "";
    if (idInput) idInput.value = "";
    if (descInput) descInput.value = "";
    if (radiusInput) radiusInput.value = "14";

    editor.style.display = "block";
    editor.scrollIntoView({ behavior: "smooth" });
  };

  window.closeThemeSaveEditor = function () {
    const editor = document.getElementById("themeSaveEditorView");
    if (editor) editor.style.display = "none";
  };

  window.autoSlugThemeId = function () {
    const nameInput = document.getElementById("newThemeName");
    const idInput = document.getElementById("newThemeId");
    if (!nameInput || !idInput) return;
    if (!idInput.dataset.manualEdited) {
      idInput.value = nameInput.value
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 32);
    }
  };

  window.onThemeIdManualEdit = function () {
    const idInput = document.getElementById("newThemeId");
    if (idInput) idInput.dataset.manualEdited = "true";
  };

  window.submitSaveCurrentTheme = async function () {
    const name = (document.getElementById("newThemeName")?.value || "").trim();
    const id = (document.getElementById("newThemeId")?.value || "").trim();
    const desc = (document.getElementById("newThemeDesc")?.value || "").trim();
    const radius = parseInt(document.getElementById("newThemeRadius")?.value || "14", 10);

    if (!id || id.length < 2) {
      alert("Please provide a valid Theme ID (lowercase letters, numbers, underscores).");
      return;
    }

    try {
      const res = await fetch("/api/themes/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          name: name || id,
          description: desc,
          card_style: {
            border_radius: isNaN(radius) ? 14 : radius,
            accent_border: true,
          },
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      closeThemeSaveEditor();
      await refreshThemeList();
      alert(`Theme '${name || id}' created successfully!`);
    } catch (err) {
      alert("Failed to save theme: " + err.message);
    }
  };

  window.openDuplicateModal = function (sourceId, sourceName) {
    const newId = prompt(
      `Enter new unique Theme ID to duplicate '${sourceName}':`,
      `${sourceId}_copy`
    );
    if (!newId) return;

    const newName = prompt(`Enter display name for duplicated theme:`, `${sourceName} (Copy)`);
    if (!newName) return;

    duplicateTheme(sourceId, newId.trim(), newName.trim());
  };

  window.duplicateTheme = async function (sourceId, newId, newName) {
    try {
      const res = await fetch("/api/themes/duplicate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId,
          new_id: newId,
          new_name: newName,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      await refreshThemeList();
      alert(`Theme duplicated into '${newName}' successfully!`);
    } catch (err) {
      alert("Failed to duplicate theme: " + err.message);
    }
  };

  window.deleteTheme = async function (themeId) {
    if (!confirm(`Are you sure you want to permanently delete custom theme '${themeId}'?`)) return;

    try {
      const res = await fetch("/api/themes/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme_id: themeId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      await refreshThemeList();
    } catch (err) {
      alert("Failed to delete theme: " + err.message);
    }
  };

  window.exportTheme = function (themeId) {
    window.location.href = `/api/themes/export?theme=${encodeURIComponent(themeId)}`;
  };

  window.importThemeFile = async function (fileInput) {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("theme_archive", file);

    try {
      const buf = await file.arrayBuffer();
      const res = await fetch("/api/themes/import", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: buf,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      fileInput.value = "";
      await refreshThemeList();
      alert("Theme imported successfully!");
    } catch (err) {
      alert("Failed to import theme: " + err.message);
    }
  };

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial load when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      refreshThemeList();
    });
  } else {
    refreshThemeList();
  }
})();
