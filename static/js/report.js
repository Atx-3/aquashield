/**
 * AQUA SHIELD: Forensic Investigation Dossier & Report Viewer
 * Apple Executive Light Theme Dossier Renderer
 *
 * STEP 8 on the front end. When the report is opened:
 *   1. show the pop-up ("modal") with a loading spinner,
 *   2. ask the backend to build the dossier (POST /api/generate_report),
 *   3. turn the JSON into HTML with one big template string (renderDossier).
 * ${...} inside the backtick strings inserts values; `a || 'N/A'` shows 'N/A' when a
 * value is missing, and `?.` avoids errors when a nested object doesn't exist.
 * The Print button uses the browser's own print dialog (window.print()), which can
 * also "Save as PDF".
 */

class AquaShieldReportModule {
    constructor() {
        this.modal = null;
        this.reportData = null;
    }

    init() {
        this.modal = document.getElementById('report-modal');
        this.bindEvents();
    }

    // Hook up the view / close / print buttons
    bindEvents() {
        const viewBtn = document.getElementById('btn-view-report');
        const closeBtn = document.getElementById('btn-close-report');
        const printBtn = document.getElementById('btn-print-report');

        if (viewBtn) viewBtn.addEventListener('click', () => this.openReport());
        if (closeBtn) closeBtn.addEventListener('click', () => this.closeReport());
        if (printBtn) printBtn.addEventListener('click', () => window.print());

        // Clicking the dark background around the report (not the report itself) closes it
        if (this.modal) {
            this.modal.addEventListener('click', (e) => {
                if (e.target === this.modal) this.closeReport();
            });
        }
    }

    // Show the modal (CSS class "open" makes it visible), then load and render the report
    async openReport() {
        if (!this.modal) return;
        this.modal.classList.add('open');

        const contentEl = document.getElementById('report-modal-body');
        if (contentEl) {
            contentEl.innerHTML = `
                <div style="text-align: center; padding: 48px; color: #0071e3; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
                    <div style="font-size: 28px; margin-bottom: 12px; animation: emblem-spin 2s linear infinite; display: inline-block;">◌</div><br>
                    <span style="font-weight: 600; letter-spacing: 0.5px;">COMPILING MARITIME FORENSIC DOSSIER...</span>
                </div>
            `;
        }

        try {
            const res = await fetch('/api/generate_report', { method: 'POST' });
            this.reportData = await res.json();
            this.renderDossier(this.reportData);
        } catch (e) {
            console.error("Report fetch error:", e);
            if (contentEl) {
                contentEl.innerHTML = `<div style="color: #ff3b30; text-align: center; padding: 24px; font-weight: 600;">Error generating report: ${e.message}</div>`;
            }
        }
    }

    closeReport() {
        if (this.modal) this.modal.classList.remove('open');
    }

    // Builds the report HTML: header, 1 summary, 2 detection, 3 hindcast/forecast,
    // 4 candidate vessel, 5 recommended actions.
    renderDossier(dossier) {
        const container = document.getElementById('report-modal-body');
        if (!container || !dossier) return;

        // Pull out each section of the backend's dossier (empty object {} if missing).
        // NOTE: the backend puts the shape values (area, perimeter...) directly in
        // spill_detection, not under "spill_geometry", and sends no "radar_features",
        // so `geom` and `radar` end up empty and those rows show N/A / NOT EXECUTED.
        const spill = dossier.sections?.spill_detection || {};
        const geom = spill.spill_geometry || {};
        const weather = spill.weathering_and_age || {};
        const hindcast = dossier.sections?.hindcast_origin || {};
        const forecast = dossier.sections?.forecast_dispersion || {};
        const culprit = dossier.sections?.culprit_attribution || {};
        const primary = culprit.primary_suspect || {};
        const radar = spill.radar_features || {};

        container.innerHTML = `
            <div style="background: #ffffff; border: 1px solid rgba(0,0,0,0.08); border-radius: 16px; padding: 22px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); margin-bottom: 20px;">
                
                <!-- Dossier Header -->
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(0,0,0,0.08); padding-bottom: 14px; margin-bottom: 16px;">
                    <div>
                        <h2 style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 18px; font-weight: 800; color: #1d1d1f; letter-spacing: 0.5px; margin: 0 0 4px 0;">
                            MARITIME POLLUTION FORENSIC DOSSIER
                        </h2>
                        <span style="font-family: var(--font-mono); font-size: 11px; color: #86868b;">
                            CASE ID: ${dossier.case_id || 'N/A'} • ${dossier.jurisdiction || 'Indian EEZ Offshore'}
                        </span>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-family: var(--font-mono); font-size: 10px; background: rgba(255,59,48,0.1); color: #ff3b30; border: 1px solid rgba(255,59,48,0.3); padding: 4px 10px; font-weight: 700; border-radius: 20px;">
                            ${dossier.classification_level || 'RESTRICTED EVIDENCE'}
                        </span>
                        <div style="font-family: var(--font-mono); font-size: 10px; color: #86868b; margin-top: 5px;">
                            ${dossier.report_timestamp || ''}
                        </div>
                    </div>
                </div>

                <!-- Section 1: Executive Summary -->
                <div class="report-section">
                    <div class="report-section-title">1. EXECUTIVE SUMMARY & ATTRIBUTION VERDICT</div>
                    <p style="font-size: 13px; line-height: 1.6; color: #1d1d1f; background: rgba(0, 113, 227, 0.05); padding: 14px; border-radius: 12px; border-left: 4px solid #0071e3; margin: 0;">
                        ${dossier.executive_summary || 'N/A'}
                    </p>
                </div>

                <!-- Section 2 & 3: Detection & Hindcast Grid -->
                <div class="report-section" style="display: grid; grid-template-columns: 1fr 1fr; gap: 18px;">
                    <div style="background: rgba(0,0,0,0.02); padding: 14px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.04);">
                        <div class="report-section-title">2. SATELLITE SAR/EO DETECTION & GEOMETRY</div>
                        <table style="width: 100%; font-size: 11px; color: #1d1d1f; border-collapse: collapse;">
                            <tr><td style="color: #86868b; padding: 4px 0;">Sensor:</td><td style="font-weight: 600;">${spill.satellite_sensor || 'Sentinel-1B C-band SAR'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Detected Location:</td><td style="font-family: var(--font-mono);">${spill.center_coordinates?.formatted || 'NOT EXECUTED'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Area / Perimeter:</td><td style="font-weight: 600;">${geom.area_km2 !== undefined ? geom.area_km2 + ' km²' : 'NOT EXECUTED'} / ${geom.perimeter_km ? geom.perimeter_km + ' km' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Major / Minor Axis:</td><td>${geom.major_axis_km ? geom.major_axis_km + ' km' : 'N/A'} × ${geom.minor_axis_km ? geom.minor_axis_km + ' km' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Eccentricity / Compactness:</td><td>${geom.eccentricity ?? 'N/A'} / ${geom.compactness_index ?? 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Estimated Slick Age:</td><td style="color: #b45309; font-weight: 700;">${weather.estimated_age_hours ? weather.estimated_age_hours + ' hrs' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Evaporative Loss / Emulsion:</td><td>${weather.evaporation_loss_pct ? weather.evaporation_loss_pct + '%' : 'N/A'} / ${weather.water_emulsification_pct ? weather.water_emulsification_pct + '%' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Damping Ratio / Contrast:</td><td>${radar.damping_ratio ? radar.damping_ratio + ' dB' : 'N/A'} / ${radar.backscatter_contrast_db ? radar.backscatter_contrast_db + ' dB' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Confidence Score:</td><td style="color: #1a7f37; font-weight: 700;">${spill.confidence_percentage || 'N/A'}</td></tr>
                        </table>
                    </div>

                    <div style="background: rgba(0,0,0,0.02); padding: 14px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.04);">
                        <div class="report-section-title">3. HYDRODYNAMIC HINDCAST ORIGIN</div>
                        <table style="width: 100%; font-size: 11px; color: #1d1d1f; border-collapse: collapse;">
                            <tr><td style="color: #86868b; padding: 4px 0;">Reconstructed Origin:</td><td style="color: #b45309; font-weight: 700; font-family: var(--font-mono);">${hindcast.origin_coordinates?.formatted || 'NOT EXECUTED'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Discharge Time Window:</td><td style="font-weight: 600;">${hindcast.time_window || 'NOT EXECUTED'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Uncertainty Radius:</td><td>${hindcast.uncertainty_radius_km && hindcast.uncertainty_radius_km !== 'N/A' ? '±' + hindcast.uncertainty_radius_km + ' km' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Ocean Current:</td><td>${hindcast.hydrodynamic_factors?.ocean_current_vector || 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Surface Wind Leeway:</td><td>${hindcast.hydrodynamic_factors?.surface_wind_vector || 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">Backdrift Distance:</td><td>${hindcast.hydrodynamic_factors?.total_backdrift_distance_km ? hindcast.hydrodynamic_factors.total_backdrift_distance_km + ' km' : 'N/A'}</td></tr>
                            <tr><td style="color: #86868b; padding: 4px 0;">24h Forecast Plume Area:</td><td style="color: #1a7f37; font-weight: 700;">${forecast.projected_area_km2 !== undefined && forecast.projected_area_km2 !== 'NOT EXECUTED' ? forecast.projected_area_km2 + ' km²' : 'NOT EXECUTED'}</td></tr>
                            <!-- Landfall ETA is a fixed text (Alibag, near Mumbai), shown whenever a forecast ran -->
                            <tr><td style="color: #86868b; padding: 4px 0;">Shoreline Landfall ETA:</td><td style="color: #ff3b30; font-weight: 600;">${forecast.status === 'EXECUTED' ? 'Alibag Coastal Zone (~36 hrs)' : 'NOT EXECUTED'}</td></tr>
                        </table>
                    </div>
                </div>

                <!-- Section 4: Culprit Profile & Candidate Matrix -->
                <div class="report-section">
                    <div class="report-section-title">4. AIS TRAJECTORY CORRELATION & PRIMARY CULPRIT ATTRIBUTION</div>
                    <!-- condition ? A : B  -> show the candidate box if any vessel was ranked, otherwise an "insufficient evidence" box -->

                    ${(culprit.candidate_ranking && culprit.candidate_ranking.length > 0) ? `
                    <div style="background: rgba(255,59,48,0.06); border: 1px solid rgba(255,59,48,0.25); padding: 14px; border-radius: 12px; margin-bottom: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-size: 14px; font-weight: 800; color: #ff3b30;">
                                LEADING SOURCE CANDIDATE: ${primary.name || 'UNKNOWN'} (${primary.id || ''})
                            </span>
                            <span style="background: #ff3b30; color: #ffffff; font-family: var(--font-mono); font-weight: 700; font-size: 11px; padding: 3px 10px; border-radius: 20px;">
                                SCORE: ${primary.risk_score || 0}%
                            </span>
                        </div>
                        <div style="font-size: 11px; color: #1d1d1f; display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                            <div><b>Distance to Origin/Spill:</b> ${primary.distance_km ?? 'N/A'} km</div>
                            <div><b>Speed (SOG):</b> ${primary.speed_kn ?? 'N/A'} kn</div>
                        </div>
                    </div>
                    ` : `
                    <div style="background: rgba(0, 113, 227, 0.05); border: 1px solid rgba(0, 113, 227, 0.2); padding: 14px; border-radius: 12px; margin-bottom: 14px; color: #1d1d1f; font-size: 12px;">
                        <b>HISTORICAL AIS ATTRIBUTION STATUS:</b> INSUFFICIENT EVIDENCE<br>
                        <span style="color: #86868b; font-size: 11px;">No historical AIS parquet tracks matching incident window. Live AIS candidates evaluated by distance.</span>
                    </div>
                    `}
                </div>

                <!-- Section 5: Enforcement Recommendations -->
                <div class="report-section" style="border-bottom: none; margin-bottom: 0; padding-bottom: 0;">
                    <div class="report-section-title">5. RECOMMENDED STATUTORY & MARITIME ENFORCEMENT ACTIONS</div>
                    <ul style="padding-left: 20px; font-size: 12px; color: #1d1d1f; line-height: 1.6;">
                        <!-- one <li> bullet per recommendation from the backend -->
                        ${(dossier.enforcement_recommendations || []).map(r => `<li>${r}</li>`).join('')}
                    </ul>
                </div>
            </div>
        `;
    }
}

// Expose the class so app.js can create it
window.AquaShieldReport = AquaShieldReportModule;
