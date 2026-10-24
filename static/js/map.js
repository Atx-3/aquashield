/**
 * AQUA SHIELD: High-Resolution Photorealistic Satellite Map Engine
 * Gujarat / Arabian Sea Surveillance Sector (Porbandar, Veraval, Somnath, Diu)
 *
 * Everything drawn on the map lives here. Built with Leaflet (the global `L` object,
 * loaded from a CDN in index.html), an open-source library for interactive maps.
 *
 * Leaflet basics used in this file:
 *   L.map(id)            create the map inside the <div id="...">
 *   L.tileLayer(url)     background imagery made of small square image "tiles"
 *   L.layerGroup()       a named folder of shapes; clearLayers() empties it
 *   L.polygon / polyline filled area / line from a list of [lat, lng] points
 *   L.marker + L.divIcon a point on the map whose look is custom HTML
 *   flyTo / flyToBounds  animate the camera to a point / to fit an area
 *
 * Colour code: red = spill & hindcast, amber = origin & correlation, cyan = forecast & ships.
 * On top of the map there is a transparent <canvas> where moving glowing dots
 * ("particles") are animated along paths to show direction of flow.
 */

class AquaShieldMapEngine {
    constructor(mapContainerId = 'map-viewport') {
        this.containerId = mapContainerId;
        this.map = null;
        
        // Layer Groups
        // One group per kind of drawing, so each can be cleared independently
        this.layers = {
            satelliteTiles: null,
            labelsTiles: null,
            currentSpill: L.layerGroup(),
            probableOrigin: L.layerGroup(),
            forecastPlume: L.layerGroup(),
            vesselWakes: L.layerGroup(),
            vessels: L.layerGroup(),
            trajectories: L.layerGroup(),
            correlationTrace: L.layerGroup(),
            demoTrack: L.layerGroup()
        };

        // Gujarat Coastal Focal Center (Arabian Sea between Porbandar & Veraval)
        // Default positions; replaced with real values after upload / hindcast
        this.centerLat = 21.1520;
        this.centerLng = 69.8540;
        this.originLat = 20.8450;
        this.originLng = 69.5210;

        // MMSI -> marker, for finding a ship's marker later
        this.vesselMarkers = {};
    }

    // Creates the map, adds background tiles and layers, starts the particle animation
    init() {
        // 1. Initialize Leaflet Map
        this.map = L.map(this.containerId, {
            center: [21.05, 69.95],
            zoom: 9,
            minZoom: 6,
            maxZoom: 16,
            zoomControl: false,
            attributionControl: false
        });

        // Instrument map camera calls to trace overrides
        // Debugging aid: each camera method is wrapped so every call is logged to the
        // browser console (with a stack trace) before running the original method.
        // .bind(this.map) keeps the original function attached to the map object.
        const origFlyTo = this.map.flyTo.bind(this.map);
        const origSetView = this.map.setView.bind(this.map);
        const origFitBounds = this.map.fitBounds.bind(this.map);
        const origFlyToBounds = this.map.flyToBounds.bind(this.map);
        const origPanTo = this.map.panTo ? this.map.panTo.bind(this.map) : null;

        this.map.flyTo = (target, zoom, options) => {
            console.log(`[AQUA SHIELD CAMERA CALL] method=flyTo target=${JSON.stringify(target)} zoom=${zoom}\nStack: ${new Error().stack}`);
            return origFlyTo(target, zoom, options);
        };

        this.map.setView = (center, zoom, options) => {
            console.log(`[AQUA SHIELD CAMERA CALL] method=setView center=${JSON.stringify(center)} zoom=${zoom}\nStack: ${new Error().stack}`);
            return origSetView(center, zoom, options);
        };

        this.map.fitBounds = (bounds, options) => {
            console.log(`[AQUA SHIELD CAMERA CALL] method=fitBounds bounds=${JSON.stringify(bounds)}\nStack: ${new Error().stack}`);
            return origFitBounds(bounds, options);
        };

        this.map.flyToBounds = (bounds, options) => {
            console.log(`[AQUA SHIELD CAMERA CALL] method=flyToBounds bounds=${JSON.stringify(bounds)}\nStack: ${new Error().stack}`);
            return origFlyToBounds(bounds, options);
        };

        if (origPanTo) {
            this.map.panTo = (target, options) => {
                console.log(`[AQUA SHIELD CAMERA CALL] method=panTo target=${JSON.stringify(target)}\nStack: ${new Error().stack}`);
                return origPanTo(target, options);
            };
        }

        // 2. Add Photorealistic Satellite Earth Basemap (ESRI World Imagery)
        // {z}/{y}/{x} in the URL = zoom level / tile row / tile column, filled in by Leaflet
        this.layers.satelliteTiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19
        }).addTo(this.map);

        // 3. Add Coastal Geography Labels
        this.layers.labelsTiles = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19,
            opacity: 0.85
        }).addTo(this.map);

        // 4. Attach Layer Groups & Canvas Particle Overlay Engine
        // (layers added later are drawn on top, so ships appear above the spill)
        this.layers.vesselWakes.addTo(this.map);
        this.layers.currentSpill.addTo(this.map);
        this.layers.probableOrigin.addTo(this.map);
        this.layers.forecastPlume.addTo(this.map);
        this.layers.trajectories.addTo(this.map);
        this.layers.correlationTrace.addTo(this.map);
        this.layers.vessels.addTo(this.map);
        this.layers.demoTrack.addTo(this.map);

        // Particle Overlay System
        this.activeParticlePaths = {}; // { 'hindcast': [...], 'forecast': [...], 'vessel': [...] }
        this.particleCanvas = null;
        this.particleCtx = null;
        this.animFrameId = null;
        this.initParticleOverlay();

        // 5. Connect Custom Map Controls
        this.bindMapControls();
    }

    // Creates a transparent <canvas> covering the whole map for the moving particles.
    // pointerEvents 'none' lets mouse clicks pass through to the map underneath.
    initParticleOverlay() {
        if (this.particleCanvas) return;
        const container = this.map.getContainer();
        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '450';
        container.appendChild(canvas);

        this.particleCanvas = canvas;
        this.particleCtx = canvas.getContext('2d');

        const resizeCanvas = () => {
            const size = this.map.getSize();
            canvas.width = size.x;
            canvas.height = size.y;
        };
        resizeCanvas();

        // Keep the canvas the same size as the map whenever the map moves or resizes
        this.map.on('resize move zoom animatereset moveend zoomend', resizeCanvas);
        this.startParticleAnimation();
    }

    // Animation loop for the particles. requestAnimationFrame() calls `animate` before
    // every screen refresh (~60 times per second). Each frame:
    //   1. clear the canvas
    //   2. for every active path (hindcast, forecast, vessel, correlation):
    //      convert its lat/lng points to screen pixels, measure its total length,
    //      and draw 6 evenly spaced dots that slide along it over time
    startParticleAnimation() {
        if (this.animFrameId) return;

        const numParticlesPerPath = 6;
        let startTime = performance.now();

        const animate = (now) => {
            const elapsedSec = (now - startTime) / 1000.0;
            const ctx = this.particleCtx;
            if (!ctx || !this.particleCanvas) return;

            ctx.clearRect(0, 0, this.particleCanvas.width, this.particleCanvas.height);

            // Loop through active particle paths
            Object.keys(this.activeParticlePaths).forEach(key => {
                const config = this.activeParticlePaths[key];
                if (!config || !config.latlngs || config.latlngs.length < 2) return;

                const latlngs = config.latlngs;
                const color = config.color || '#ff3b30';
                const speed = config.speed || 0.15; // cycles per sec

                // Compute polyline segment distances in pixels
                const pixels = latlngs.map(ll => this.map.latLngToContainerPoint(ll));
                let totalDist = 0;
                const dists = [0];
                for (let i = 0; i < pixels.length - 1; i++) {
                    const d = Math.hypot(pixels[i+1].x - pixels[i].x, pixels[i+1].y - pixels[i].y);
                    totalDist += d;
                    dists.push(totalDist);
                }

                if (totalDist < 1) return;

                // Render staggered particles along path
                // progress (0..1) = how far along the path this dot is; % 1.0 makes it loop.
                // phaseOffset spreads the 6 dots out so they don't overlap.
                for (let p = 0; p < numParticlesPerPath; p++) {
                    const phaseOffset = p / numParticlesPerPath;
                    const progress = (elapsedSec * speed + phaseOffset) % 1.0;
                    const targetDist = progress * totalDist;

                    // Find segment
                    let segIdx = 0;
                    while (segIdx < dists.length - 1 && dists[segIdx + 1] < targetDist) {
                        segIdx++;
                    }

                    const segStart = dists[segIdx];
                    const segEnd = dists[segIdx + 1];
                    const segLen = segEnd - segStart;
                    const ratio = segLen > 0 ? (targetDist - segStart) / segLen : 0;

                    // Linear interpolation: the point `ratio` of the way from p1 to p2
                    const p1 = pixels[segIdx];
                    const p2 = pixels[segIdx + 1] || p1;

                    const ptX = p1.x + ratio * (p2.x - p1.x);
                    const ptY = p1.y + ratio * (p2.y - p1.y);

                    // Particle glow & dot
                    ctx.save();
                    ctx.shadowColor = color;
                    ctx.shadowBlur = 8;
                    ctx.fillStyle = color;
                    ctx.globalAlpha = 0.85;

                    ctx.beginPath();
                    ctx.arc(ptX, ptY, 3.0, 0, 2 * Math.PI);
                    ctx.fill();

                    // Core bright center
                    ctx.shadowBlur = 0;
                    ctx.fillStyle = '#ffffff';
                    ctx.globalAlpha = 0.95;
                    ctx.beginPath();
                    ctx.arc(ptX, ptY, 1.2, 0, 2 * Math.PI);
                    ctx.fill();

                    ctx.restore();
                }
            });

            this.animFrameId = requestAnimationFrame(animate);
        };

        this.animFrameId = requestAnimationFrame(animate);
    }

    // Custom zoom in / zoom out / recenter buttons. The "layers" button only shows a
    // message; it doesn't actually toggle any layer.
    bindMapControls() {
        const btnZoomIn = document.getElementById('btn-map-zoom-in');
        const btnZoomOut = document.getElementById('btn-map-zoom-out');
        const btnRecenter = document.getElementById('btn-map-recenter');
        const btnLayers = document.getElementById('btn-map-layers');

        if (btnZoomIn) btnZoomIn.addEventListener('click', () => this.map.zoomIn());
        if (btnZoomOut) btnZoomOut.addEventListener('click', () => this.map.zoomOut());
        if (btnRecenter) btnRecenter.addEventListener('click', () => this.focusSpill());
        if (btnLayers) {
            btnLayers.addEventListener('click', () => {
                window.aquaShieldApp.showNotification("LAYER: Sentinel-1 SAR + HYCOM Current Flow overlay toggled.");
            });
        }
    }

    // Draws the detected spill: outline polygon + pulsing red dot with a hover card.
    // Uses the polygon from the backend if given; otherwise a pre-drawn "blob" shape
    // (fixed offsets) around the center. Clicking either opens the report.
    renderCurrentSpill(lat = this.centerLat, lng = this.centerLng, areaKm2 = 16.5, prob = 0.67, customCoords = null) {
        this.layers.currentSpill.clearLayers();
        this.centerLat = lat;
        this.centerLng = lng;

        let spillCoords = customCoords;
        if (!spillCoords || spillCoords.length === 0) {
            const offsets = [
                [-0.020, -0.160], [-0.010, -0.120], [0.015, -0.090], [0.025, -0.050],
                [0.010, -0.010], [0.020, 0.040], [0.005, 0.090], [-0.025, 0.130],
                [-0.055, 0.160], [-0.085, 0.180], [-0.110, 0.160], [-0.090, 0.110],
                [-0.060, 0.070], [-0.040, 0.020], [-0.060, -0.030], [-0.080, -0.080],
                [-0.070, -0.130], [-0.045, -0.160]
            ];
            spillCoords = offsets.map(o => [lat + o[0], lng + o[1]]);
        }

        // Dark red-purple damped oil slick polygon
        const slickPoly = L.polygon(spillCoords, {
            color: '#ff3b30',
            weight: 2.2,
            dashArray: '5, 5',
            fillColor: '#671424',
            fillOpacity: 0.68,
            className: 'pulsing-satellite-slick'
        }).addTo(this.layers.currentSpill);

        slickPoly.on('click', () => window.aquaShieldApp.report.openReport());

        const probPct = Math.round(prob * 100);

        // Center Pulsing Red Beacon Dot (Dot Only by Default)
        const beaconIcon = L.divIcon({
            className: 'spill-center-marker-node',
            html: `
                <div style="position: relative; pointer-events: auto;">
                    <div style="width: 14px; height: 14px; background: #ff3b30; border: 2.5px solid #ffffff; border-radius: 50%; box-shadow: 0 0 16px #ff3b30; animation: beacon-pulse 1.8s infinite ease-in-out; cursor: pointer;"></div>
                    
                    <!-- Hover Glass Box -->
                    <div class="spill-hover-card" style="display: none; position: absolute; bottom: 22px; left: -110px; width: 220px; background: rgba(18, 42, 66, 0.85); border: 1px solid rgba(255, 255, 255, 0.38); border-radius: 14px; padding: 8px 12px; box-shadow: 0 14px 36px rgba(0,0,0,0.6); backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px); cursor: pointer; z-index: 1000;">
                        <div style="display: flex; flex-direction: column; flex: 1;">
                            <div style="font-size: 11.5px; font-weight: 800; color: #ffffff; display: flex; justify-content: space-between; align-items: center;">
                                <span>Detected Spill</span>
                                <span style="color: #00d2ff; font-size: 12px;">›</span>
                            </div>
                            <div style="font-size: 10px; color: #cde0f5; margin-top: 2px; display: flex; justify-content: space-between;">
                                <span>Area: <b style="color: #ff3b30;">${areaKm2} km²</b></span>
                                <span>Mean Prob: <b>${probPct}%</b></span>
                            </div>
                            <div style="font-size: 9.5px; color: #ff9f0a; font-family: var(--font-mono); margin-top: 3px;">
                                ${lat.toFixed(4)}°N, ${lng.toFixed(4)}°E
                            </div>
                        </div>
                    </div>
                </div>
            `,
            iconSize: [14, 14]
        });

        const marker = L.marker([lat, lng], { icon: beaconIcon }).addTo(this.layers.currentSpill);

        // Show the info card while the mouse is over the dot, hide it when the mouse leaves
        marker.on('mouseover', (e) => {
            const el = e.target.getElement();
            if (el) {
                const card = el.querySelector('.spill-hover-card');
                if (card) card.style.display = 'block';
            }
        });
        marker.on('mouseout', (e) => {
            const el = e.target.getElement();
            if (el) {
                const card = el.querySelector('.spill-hover-card');
                if (card) card.style.display = 'none';
            }
        });
        marker.on('click', () => window.aquaShieldApp.report.openReport());
    }

    // Draws a tiny 38x38 spill icon on a <canvas> (dark square + red ellipse).
    // Not called anywhere at the moment.
    renderPinThumbnail() {
        const canvas = document.getElementById('spill-thumb-pin');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#06162d';
        ctx.fillRect(0, 0, 38, 38);

        ctx.fillStyle = '#4a0e19';
        ctx.beginPath();
        ctx.ellipse(19, 19, 14, 8, Math.PI / 4, 0, 2 * Math.PI);
        ctx.fill();

        ctx.strokeStyle = '#ff3b30';
        ctx.lineWidth = 1.2;
        ctx.stroke();
    }

    // STEP 4 drawing: the hindcast path (spill -> origin) as a dashed red line with
    // moving particles, a "TRACE -> ORIGIN" label halfway, and an amber spinning target
    // at the reconstructed origin (click it for coordinates).
    renderProbableOrigin(originLat, originLng, spillLat = this.centerLat, spillLng = this.centerLng, trajectorySteps = null) {
        this.layers.probableOrigin.clearLayers();
        if (!originLat || !originLng) return;
        
        this.originLat = originLat;
        this.originLng = originLng;

        // 1. Backtrack trajectory polyline using actual NetCDF RK4 steps: SPILL -> ORIGIN
        let backtrackCoords = [];
        if (trajectorySteps && trajectorySteps.length > 0) {
            backtrackCoords = trajectorySteps.map(pt => [pt.lat, pt.lng]);
        } else {
            backtrackCoords = [[spillLat, spillLng], [originLat, originLng]];
        }
        this.backtrackCoords = backtrackCoords;

        // Glowing red/orange trace with thin bright core
        L.polyline(backtrackCoords, {
            color: '#ff3b30',
            weight: 3.5,
            dashArray: '6, 6',
            opacity: 0.95
        }).addTo(this.layers.probableOrigin);

        // Attach particle animation: SPILL -> ORIGIN
        const particleLatLngs = backtrackCoords.map(c => L.latLng(c[0], c[1]));
        this.activeParticlePaths['hindcast'] = {
            latlngs: particleLatLngs,
            color: '#ff3b30',
            speed: 0.18
        };

        // Directional cue label midway
        const midIdx = Math.floor(backtrackCoords.length / 2);
        const midPt = backtrackCoords[midIdx] || backtrackCoords[0];
        const cueIcon = L.divIcon({
            className: 'hindcast-cue-label',
            html: `<div style="transform: translate(-50%, -50%); background: rgba(10,25,45,0.85); border: 1px solid #ff3b30; color: #ff3b30; font-size: 8.5px; font-weight: 800; font-family: var(--font-mono); padding: 2px 6px; border-radius: 4px; box-shadow: 0 0 10px rgba(255,59,48,0.5);">TRACE → ORIGIN</div>`,
            iconSize: [80, 16]
        });
        L.marker(midPt, { icon: cueIcon }).addTo(this.layers.probableOrigin);

        // Origin target crosshair marker (Distinct Amber/Orange #ff9f0a)
        const originIcon = L.divIcon({
            className: 'origin-marker-icon',
            html: `
                <div style="transform: translate(-50%, -50%); display: flex; align-items: center; justify-content: center; position: relative;">
                    <div style="width: 26px; height: 26px; border: 2px dashed #ff9f0a; border-radius: 50%; animation: emblem-spin 8s linear infinite; background: rgba(255,159,10,0.18); box-shadow: 0 0 14px #ff9f0a;"></div>
                    <div style="width: 8px; height: 8px; background: #ff9f0a; border-radius: 50%; position: absolute; box-shadow: 0 0 10px #ff9f0a;"></div>
                </div>
            `,
            iconSize: [26, 26]
        });

        const originMarker = L.marker([originLat, originLng], { icon: originIcon }).addTo(this.layers.probableOrigin);
        originMarker.bindPopup(`
            <div style="font-family: -apple-system, sans-serif; font-size: 12px; color: #ffffff; background: #0c1a2e; padding: 10px; border-radius: 12px; border: 1px solid #ff9f0a;">
                <b style="color: #ff9f0a;">PROBABLE SPILL ORIGIN (M4 HINDCAST)</b><br>
                <b>Coords:</b> ${originLat.toFixed(4)}° N, ${originLng.toFixed(4)}° E<br>
                <b>Uncertainty:</b> ±8.6 km (Lagrangian RK4 Ensemble)
            </div>
        `);
    }

    // STEP 7 drawing: the predicted spill area (cyan polygon), a line from the current
    // spill to the forecast end point with particles, and a "FORECAST +24h" marker.
    renderForecastPlume(forecastPolygon = null, endLat = this.centerLat, endLng = this.centerLng, horizonHours = 24) {
        this.layers.forecastPlume.clearLayers();
        if (!forecastPolygon || forecastPolygon.length === 0) return;

        this.forecastPolygon = forecastPolygon;
        const spillLat = this.centerLat;
        const spillLng = this.centerLng;

        // 1. Soft Cyan/Blue Forecast Plume Polygon (Uncertainty region)
        L.polygon(forecastPolygon, {
            color: '#00d2ff',
            weight: 1.8,
            dashArray: '5, 5',
            fillColor: '#00d2ff',
            fillOpacity: 0.20
        }).addTo(this.layers.forecastPlume);

        // 2. Cyan Trace: SPILL -> FORECAST ENDPOINT
        const forecastTraceCoords = [[spillLat, spillLng], [endLat, endLng]];
        L.polyline(forecastTraceCoords, {
            color: '#00d2ff',
            weight: 3.5,
            dashArray: '4, 4',
            opacity: 0.95
        }).addTo(this.layers.forecastPlume);

        // Attach particle animation: SPILL -> FORECAST
        const forecastParticleLatLngs = forecastTraceCoords.map(c => L.latLng(c[0], c[1]));
        this.activeParticlePaths['forecast'] = {
            latlngs: forecastParticleLatLngs,
            color: '#00d2ff',
            speed: 0.18
        };

        // 3. Endpoint Marker with dynamic label
        const fcIcon = L.divIcon({
            className: 'forecast-marker-icon',
            html: `
                <div style="transform: translate(-50%, -50%); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                    <div style="width: 14px; height: 14px; border: 2px solid #00d2ff; border-radius: 50%; background: #00d2ff; box-shadow: 0 0 14px #00d2ff;"></div>
                    <div style="background: rgba(10,25,45,0.85); border: 1px solid #00d2ff; color: #00d2ff; font-size: 8.5px; font-weight: 800; font-family: var(--font-mono); padding: 2px 6px; border-radius: 4px; margin-top: 4px; white-space: nowrap; box-shadow: 0 0 8px rgba(0,210,255,0.5);">
                        FORECAST +${horizonHours}h
                    </div>
                </div>
            `,
            iconSize: [100, 34]
        });

        L.marker([endLat, endLng], { icon: fcIcon }).addTo(this.layers.forecastPlume);
    }

    // STEP 5: get live ships from the backend, update the two counters in the panel,
    // draw the ships, and zoom out to fit them all (plus the spill) on screen.
    async loadVessels() {
        try {
            const res = await fetch('/api/find_nearby_vessels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filter_irrelevant: true })
            });
            const data = await res.json();
            
            const nearEl = document.getElementById('near-spill-count-val');
            if (nearEl) {
                nearEl.textContent = `${data.near_spill_35km_count || 0} vessels`;
            }

            const regionalEl = document.getElementById('regional-vessel-count-val');
            if (regionalEl) {
                regionalEl.textContent = `${data.regional_250km_count || data.count || 0} active`;
            }

            this.renderVessels(data.vessels || []);
            // Only fly to regional live vessel bounds if NO real historical AIS match is active
            if (!this.activeParticlePaths['vessel'] && data.vessels && data.vessels.length > 0) {
                const points = data.vessels.map(v => [v.latitude, v.longitude]);
                if (this.centerLat && this.centerLng) points.push([this.centerLat, this.centerLng]);
                const bounds = L.latLngBounds(points);
                this.map.flyToBounds(bounds, { padding: [50, 50], maxZoom: 8, duration: 1.2 });
            }
        } catch (e) {
            console.error("Failed to load vessels:", e);
        }
    }

    // Draws one ship icon per vessel, rotated to its course (COG). If selectedMmsi is given,
    // that ship is drawn bigger and red as the "#1 most probable source".
    // Hovering shows a tooltip; clicking calls app.inspectPelyrVessel() to load its track.
    // The `||` fallbacks accept slightly different field names from different data sources.
    renderVessels(vessels, selectedMmsi = null) {
        this.layers.vessels.clearLayers();
        this.layers.vesselWakes.clearLayers();
        this.vesselMarkers = {};
        this.rawVessels = vessels;

        vessels.forEach(v => {
            const vLat = v.latitude || (v.current_position ? v.current_position.lat : 0.0);
            const vLng = v.longitude || (v.current_position ? v.current_position.lng : 0.0);
            if (!vLat || !vLng) return;

            const mmsiVal = String(v.mmsi || v.id || "UNKNOWN");
            const nameVal = v.vessel_name || v.name || "Commercial Vessel";
            const sogVal = v.sog !== undefined ? v.sog : (v.speed_kn || 0.0);
            const cogVal = v.cog !== undefined ? v.cog : (v.course_deg || 0.0);
            const tsVal = v.timestamp || "LIVE";
            const distKm = v.distance_km !== undefined ? (typeof v.distance_km === 'number' ? v.distance_km.toFixed(1) : v.distance_km) : "N/A";

            const isSelected = selectedMmsi && String(selectedMmsi) === mmsiVal;
            const color = isSelected ? '#ff3b30' : '#00d2ff';
            const iconSize = isSelected ? [32, 32] : [24, 24];
            const zIndex = isSelected ? 2500 : 1000;

            // Ship icon = small SVG hull shape; rotate(cog deg) points it in the travel direction
            const vesselIcon = L.divIcon({
                className: isSelected ? 'satellite-vessel-marker selected-source-vessel' : 'satellite-vessel-marker',
                html: isSelected ? `
                    <div style="transform: translate(-50%, -50%) rotate(${cogVal}deg); cursor: pointer; filter: drop-shadow(0 0 12px #ff3b30); z-index: 2500; position: relative;">
                        <div style="position: absolute; top: -8px; left: -8px; width: 44px; height: 44px; border: 2px dashed #ff3b30; border-radius: 50%; animation: emblem-spin 10s linear infinite; background: rgba(255,59,48,0.2);"></div>
                        <svg width="30" height="30" viewBox="0 0 32 32">
                            <path d="M16 2 L23 10 L23 26 L16 30 L9 26 L9 10 Z" fill="#ff3b30" stroke="#ffffff" stroke-width="2.5" />
                            <rect x="13" y="14" width="6" height="8" rx="1" fill="#ffffff" />
                        </svg>
                    </div>
                ` : `
                    <div style="transform: translate(-50%, -50%) rotate(${cogVal}deg); cursor: pointer; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.9)); z-index: 1000;">
                        <svg width="24" height="24" viewBox="0 0 32 32">
                            <path d="M16 2 L22 10 L22 26 L16 30 L10 26 L10 10 Z" fill="#ffffff" stroke="${color}" stroke-width="2.5" />
                            <rect x="13" y="14" width="6" height="8" rx="1" fill="${color}" />
                        </svg>
                    </div>
                `,
                iconSize: iconSize
            });

            const marker = L.marker([vLat, vLng], { icon: vesselIcon, zIndexOffset: zIndex }).addTo(this.layers.vessels);

            // Hover Tooltip / Card
            const tooltipContent = isSelected ? `
                <div style="font-family: -apple-system, sans-serif; font-size: 11.5px; color: #ffffff; background: #0c1a2e; padding: 12px; border-radius: 12px; border: 1.5px solid #ff3b30; box-shadow: 0 14px 32px rgba(0,0,0,0.85); min-width: 220px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 5px; margin-bottom: 6px;">
                        <b style="color: #ff3b30; font-size: 12.5px;">${nameVal}</b>
                        <span style="font-weight: 800; color: #ff3b30; font-size: 9px; background: rgba(255,59,48,0.2); padding: 2px 6px; border-radius: 4px;">
                            MOST PROBABLE SOURCE (#1)
                        </span>
                    </div>
                    <b>MMSI:</b> ${mmsiVal}<br>
                    <b>Distance to Origin:</b> <b style="color: #ff9f0a;">${distKm} km</b><br>
                    <b>Speed (SOG):</b> ${sogVal} kn | <b>Course (COG):</b> ${cogVal}°<br>
                    <b>Evidence Type:</b> ${v.evidence_type || 'LIVE AIS OBSERVATION'}<br>
                    <b>Historical Track:</b> ${v.has_historical_track ? `${v.original_ais_points_count || 0} pts` : 'UNAVAILABLE'}<br>
                    <b>Ocean Compatibility:</b> HYCOM / COPERNICUS ADVECTION ALIGNED
                </div>
            ` : `
                <div style="font-family: -apple-system, sans-serif; font-size: 11px; color: #ffffff; background: #0c1a2e; padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(0,210,255,0.4); box-shadow: 0 8px 20px rgba(0,0,0,0.6);">
                    <b style="color: #00d2ff; font-size: 11.5px;">${nameVal}</b><br>
                    <b>MMSI:</b> ${mmsiVal}<br>
                    <b>Distance to Origin:</b> ${distKm} km<br>
                    <b>Speed:</b> ${sogVal} kn | <b>Course:</b> ${cogVal}°
                </div>
            `;

            marker.bindTooltip(tooltipContent, {
                permanent: false,
                direction: 'top',
                offset: [0, -12],
                opacity: 0.95
            });

            marker.on('click', () => {
                if (window.aquaShieldApp) {
                    window.aquaShieldApp.inspectPelyrVessel(v);
                }
            });

            this.vesselMarkers[mmsiVal] = marker;
        });
    }

    // Draws a vessel's track_history line (red if HIGH risk, otherwise cyan) and zooms to it
    // if it is near the spill (within ~1 degree). Not called anywhere at the moment.
    highlightVesselTrack(vessel) {
        this.layers.trajectories.clearLayers();
        if (!vessel || !vessel.track_history || vessel.track_history.length === 0) return;

        const trackCoords = vessel.track_history.map(pt => [pt.lat, pt.lng]);
        const isHigh = vessel.risk_level === 'HIGH';
        const color = isHigh ? '#ff3b30' : '#00d2ff';

        L.polyline(trackCoords, {
            color: color,
            weight: 3.5,
            opacity: 0.95
        }).addTo(this.layers.trajectories);

        const firstPt = trackCoords[0];
        const distFromSpill = Math.hypot(firstPt[0] - this.centerLat, firstPt[1] - this.centerLng);
        if (distFromSpill < 1.0) {
            const allBounds = L.latLngBounds([...trackCoords, [this.centerLat, this.centerLng]]).pad(0.25);
            this.map.flyToBounds(allBounds, { duration: 1.2 });
        } else {
            this.focusSpill();
        }
    }

    // Fly the camera to the spill at zoom level 10
    focusSpill() {
        this.map.flyTo([this.centerLat, this.centerLng], 10, { duration: 1.0 });
    }

    // Zoom so the whole hindcast path fits on screen (uses the given steps, the last
    // drawn path, or just origin + spill as fallback)
    showHindcast(trajectorySteps = null) {
        let pts = [];
        if (trajectorySteps && trajectorySteps.length > 0) {
            pts = trajectorySteps.map(pt => [pt.lat, pt.lng]);
        } else if (this.backtrackCoords && this.backtrackCoords.length > 0) {
            pts = this.backtrackCoords;
        } else {
            pts = [
                [this.originLat, this.originLng],
                [this.centerLat, this.centerLng]
            ];
        }
        const bounds = L.latLngBounds(pts);
        this.map.flyToBounds(bounds, { padding: [80, 80], maxZoom: 12, duration: 1.2 });
        console.log(`[AQUA SHIELD CAMERA FINAL] MODE=HINDCAST CENTER=${JSON.stringify(this.map.getCenter())} BOUNDS=${JSON.stringify(this.map.getBounds())}`);
    }

    // Zoom so the forecast polygon fits on screen
    showForecast(forecastPolygon = null) {
        const poly = forecastPolygon || this.forecastPolygon;
        if (poly && poly.length > 0) {
            const bounds = L.latLngBounds(poly.map(p => [p[0], p[1]]));
            this.map.flyToBounds(bounds, { padding: [80, 80], maxZoom: 10, duration: 1.2 });
            console.log(`[AQUA SHIELD CAMERA FINAL] MODE=FORECAST CENTER=${JSON.stringify(this.map.getCenter())} BOUNDS=${JSON.stringify(this.map.getBounds())}`);
        } else if (this.centerLat && this.centerLng) {
            this.map.flyTo([this.centerLat, this.centerLng], 10, { duration: 1.2 });
        }
    }

    // Draws a live ship's recent track from the Pelyr API: cyan line, green start dot,
    // cyan end dot, a small clickable dot for every AIS point, then zooms to fit.
    renderRealPelyrTrack(trackData, vesselInfo = null) {
        this.layers.demoTrack.clearLayers();
        if (!trackData || !trackData.track_points || trackData.track_points.length === 0) return;

        const pts = trackData.track_points;
        const coords = pts.map(pt => [pt.lat, pt.lng]);
        const latlngs = coords.map(pt => L.latLng(pt[0], pt[1]));

        // Cyan Polyline for Real Pelyr AIS Track
        const trackPolyline = L.polyline(latlngs, {
            color: '#00d2ff',
            weight: 3.5,
            opacity: 0.95
        }).addTo(this.layers.demoTrack);

        // Start & End markers
        const startPtObj = pts[0];
        const endPtObj = pts[pts.length - 1];
        const startPt = [startPtObj.lat, startPtObj.lng];
        const endPt = [endPtObj.lat, endPtObj.lng];

        const startIcon = L.divIcon({
            className: 'demo-start-marker',
            html: `<div style="width: 12px; height: 12px; background: #30d158; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 0 10px #30d158;" title="TRACK START: ${startPtObj.timestamp}"></div>`,
            iconSize: [12, 12]
        });

        const endIcon = L.divIcon({
            className: 'demo-end-marker',
            html: `<div style="width: 14px; height: 14px; background: #00d2ff; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 0 12px #00d2ff;" title="TRACK END: ${endPtObj.timestamp}"></div>`,
            iconSize: [14, 14]
        });

        const startMarker = L.marker(startPt, { icon: startIcon }).addTo(this.layers.demoTrack);
        startMarker.bindTooltip(`TRACK START: ${startPtObj.timestamp}`, { permanent: false, direction: 'top' });

        const endMarker = L.marker(endPt, { icon: endIcon }).addTo(this.layers.demoTrack);
        endMarker.bindTooltip(`TRACK END: ${endPtObj.timestamp}`, { permanent: false, direction: 'top' });

        // Add interactive popups for individual AIS track points
        pts.forEach((pt, i) => {
            const pointIcon = L.divIcon({
                className: 'track-point-dot',
                html: `<div style="width: 6px; height: 6px; background: #00d2ff; border-radius: 50%; cursor: pointer;"></div>`,
                iconSize: [6, 6]
            });
            const ptMarker = L.marker([pt.lat, pt.lng], { icon: pointIcon }).addTo(this.layers.demoTrack);
            ptMarker.bindPopup(`
                <div style="font-family: -apple-system, sans-serif; font-size: 11px; color: #ffffff; background: #0c1a2e; padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(0,210,255,0.4);">
                    <b style="color: #00d2ff;">AIS POSITION</b><br>
                    <b>Timestamp:</b> ${pt.timestamp || 'N/A'}<br>
                    <b>Latitude:</b> ${pt.lat.toFixed(4)}°N<br>
                    <b>Longitude:</b> ${pt.lng.toFixed(4)}°E<br>
                    <b>SOG:</b> ${pt.sog !== undefined ? pt.sog : 0.0} kn<br>
                    <b>COG:</b> ${pt.cog !== undefined ? pt.cog : 0.0}°<br>
                    <b>Heading:</b> ${pt.heading !== undefined ? pt.heading : 0.0}°
                </div>
            `);
        });

        const vName = vesselInfo ? vesselInfo.vessel_name : "Pelyr Vessel";
        const vMmsi = vesselInfo ? vesselInfo.mmsi : (trackData.mmsi || "N/A");
        const ptCount = pts.length;

        endMarker.bindPopup(`
            <div style="font-family: -apple-system, sans-serif; font-size: 11.5px; color: #ffffff; background: #0c1a2e; padding: 12px; border-radius: 12px; border: 1px solid rgba(0,210,255,0.5);">
                <b style="color: #00d2ff;">REAL PELYR AIS TRAJECTORY</b><br>
                <b>SOURCE:</b> PELYR HTTPS API<br>
                <b>VESSEL:</b> ${vName} (MMSI: ${vMmsi})<br>
                <b>TRACK POINTS:</b> ${ptCount} chronological<br>
                <div style="margin-top: 6px; font-size: 9.5px; color: #8ca3bf; border-top: 1px dashed rgba(255,255,255,0.2); padding-top: 4px;">
                    SOURCE: PELYR<br>
                    MODE: LIVE + HISTORICAL TRACK
                </div>
            </div>
        `);

        // Fly camera to bounds including spill centroid & trajectory points
        if (this.centerLat && this.centerLng) {
            const boundsCoords = [L.latLng(this.centerLat, this.centerLng), ...latlngs];
            this.map.flyToBounds(L.latLngBounds(boundsCoords), { padding: [60, 60], duration: 1.2 });
        } else {
            this.map.flyToBounds(L.latLngBounds(latlngs), { padding: [60, 60], duration: 1.2 });
        }
    }

    // For the bundled Sentinel-1 test scenes: draws the matched ship's recorded track in red,
    // particles flowing from the ship to the origin, a pulsing target at the AIS ping
    // closest in time to the satellite photo, and a labelled ship marker.
    // Not called anywhere in the current code.
    renderRealMatchedAISTrajectory(realAisMatch) {
        this.layers.demoTrack.clearLayers();
        if (!realAisMatch || !realAisMatch.matched) {
            delete this.activeParticlePaths['vessel'];
            return;
        }

        const pts = realAisMatch.trajectory_points || [];
        const vesselName = realAisMatch.vessel_name || "Historical Vessel";
        const mmsi = realAisMatch.vessel_mmsi || "N/A";
        const acqTime = realAisMatch.satellite_acquisition_utc || "N/A";
        const aisTime = realAisMatch.closest_ais_timestamp_utc || "N/A";
        const dtMin = realAisMatch.temporal_difference_minutes !== undefined ? realAisMatch.temporal_difference_minutes : 0.0;
        const dtSec = (dtMin * 60).toFixed(3);
        const ptCount = realAisMatch.ais_points_count || pts.length;
        const synthCount = realAisMatch.synthetic_points || 0;
        const closestLat = realAisMatch.closest_ais_lat;
        const closestLon = realAisMatch.closest_ais_lon;

        if (!pts || pts.length === 0) {
            console.warn("[AQUA SHIELD REAL AIS] Real AIS trajectory unavailable for matched vessel.");
            delete this.activeParticlePaths['vessel'];
            return;
        }

        const coords = pts.map(pt => [pt.latitude || pt.lat, pt.longitude || pt.lng]);
        const latlngs = coords.map(pt => L.latLng(pt[0], pt[1]));

        // 1. Red Polyline for HISTORICAL AIS VESSEL TRACK
        const trackPolyline = L.polyline(latlngs, {
            color: '#ff3b30',
            weight: 3.8,
            opacity: 0.95,
            dashArray: '6, 4'
        }).addTo(this.layers.demoTrack);

        // Append discharge origin to particle path so particle flow travels: VESSEL -> AIS TRAJECTORY -> PROBABLE ORIGIN
        const vesselParticleLatLngs = [...latlngs];
        if (this.originLat && this.originLng) {
            vesselParticleLatLngs.push(L.latLng(this.originLat, this.originLng));
        } else if (this.centerLat && this.centerLng) {
            vesselParticleLatLngs.push(L.latLng(this.centerLat, this.centerLng));
        }

        // Attach particle animation: VESSEL -> ORIGIN
        this.activeParticlePaths['vessel'] = {
            latlngs: vesselParticleLatLngs,
            color: '#ff3b30',
            speed: 0.16
        };

        // Render Start Marker
        const startPtObj = pts[0];
        const startMarker = L.marker([startPtObj.latitude || startPtObj.lat, startPtObj.longitude || startPtObj.lng], {
            icon: L.divIcon({
                className: 'matched-start-marker',
                html: `<div style="width: 12px; height: 12px; background: #30d158; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 0 10px #30d158;"></div>`,
                iconSize: [12, 12]
            })
        }).addTo(this.layers.demoTrack);
        startMarker.bindTooltip(`TRACK START: ${startPtObj.timestamp || 'N/A'}`, { permanent: false, direction: 'top' });

        // Highlight Closest AIS Observation with distinct Pulsing Target Icon
        if (closestLat !== undefined && closestLon !== undefined) {
            const closestMarker = L.marker([closestLat, closestLon], {
                icon: L.divIcon({
                    className: 'closest-ais-obs-marker',
                    html: `
                        <div style="transform: translate(-50%, -50%); position: relative; cursor: pointer;">
                            <div style="width: 28px; height: 28px; border: 2px solid #ff3b30; border-radius: 50%; background: rgba(255,59,48,0.25); animation: pulse 1.5s infinite;"></div>
                            <div style="width: 10px; height: 10px; background: #ff3b30; border: 2px solid #ffffff; border-radius: 50%; position: absolute; top: 9px; left: 9px; box-shadow: 0 0 12px #ff3b30;"></div>
                        </div>
                    `,
                    iconSize: [28, 28]
                }),
                zIndexOffset: 2000
            }).addTo(this.layers.demoTrack);

            closestMarker.bindPopup(`
                <div style="font-family: -apple-system, sans-serif; font-size: 11.5px; color: #ffffff; background: #0c1a2e; padding: 12px; border-radius: 12px; border: 1px solid #ff3b30; box-shadow: 0 12px 28px rgba(0,0,0,0.8);">
                    <b style="color: #ff3b30; font-size: 12px;">CLOSEST AIS OBSERVATION</b><br>
                    <b>VESSEL:</b> ${vesselName}<br>
                    <b>MMSI:</b> ${mmsi}<br>
                    <b>TIMESTAMP:</b> ${aisTime}<br>
                    <b>LAT/LON:</b> ${closestLat.toFixed(5)}°N, ${closestLon.toFixed(5)}°E<br>
                    <b>Δt FROM SATELLITE:</b> <b style="color: #30d158;">${dtSec} sec</b> (${dtMin.toFixed(6)} min)
                </div>
            `);
        }

        // Draw individual AIS track points
        pts.forEach((pt) => {
            const ptLat = pt.latitude || pt.lat;
            const ptLon = pt.longitude || pt.lng;
            const ptMarker = L.marker([ptLat, ptLon], {
                icon: L.divIcon({
                    className: 'matched-track-dot',
                    html: `<div style="width: 6px; height: 6px; background: #ff3b30; border-radius: 50%; cursor: pointer;"></div>`,
                    iconSize: [6, 6]
                })
            }).addTo(this.layers.demoTrack);

            ptMarker.bindPopup(`
                <div style="font-family: -apple-system, sans-serif; font-size: 11px; color: #ffffff; background: #0c1a2e; padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(255,59,48,0.5);">
                    <b style="color: #ff3b30;">ORIGINAL HISTORICAL AIS RECORD</b><br>
                    <b>Vessel:</b> ${vesselName} (${mmsi})<br>
                    <b>Timestamp:</b> ${pt.timestamp || 'N/A'}<br>
                    <b>Lat/Lon:</b> ${ptLat.toFixed(5)}°N, ${ptLon.toFixed(5)}°E<br>
                    <b>SOG:</b> ${pt.sog !== undefined ? pt.sog : 0.0} kn | <b>COG:</b> ${pt.cog !== undefined ? pt.cog : 0.0}°
                </div>
            `);
        });

        // Add Red Vessel Marker with Glowing Outline & Compact Label
        const endPtObj = pts[pts.length - 1];
        const currentVesselLat = closestLat !== undefined ? closestLat : (endPtObj.latitude || endPtObj.lat);
        const currentVesselLon = closestLon !== undefined ? closestLon : (endPtObj.longitude || endPtObj.lng);

        const vesselMarker = L.marker([currentVesselLat, currentVesselLon], {
            icon: L.divIcon({
                className: 'historical-matched-vessel-marker',
                html: `
                    <div style="transform: translate(-50%, -50%); cursor: pointer; display: flex; flex-direction: column; align-items: center; filter: drop-shadow(0 4px 14px rgba(255,59,48,0.9)); z-index: 1500;">
                        <!-- Red Glowing Vessel Ship Icon -->
                        <div style="width: 32px; height: 32px; border-radius: 50%; background: rgba(255,59,48,0.2); border: 2px solid #ff3b30; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 16px #ff3b30; animation: beacon-pulse 1.8s infinite ease-in-out;">
                            <svg width="22" height="22" viewBox="0 0 32 32">
                                <path d="M16 2 L23 10 L23 26 L16 30 L9 26 L9 10 Z" fill="#ff3b30" stroke="#ffffff" stroke-width="2" />
                                <rect x="13" y="14" width="6" height="8" rx="1" fill="#ffffff" />
                            </svg>
                        </div>
                        <!-- Compact Source Label -->
                        <div style="background: rgba(10,25,45,0.90); border: 1.5px solid #ff3b30; color: #ffffff; padding: 4px 8px; border-radius: 6px; margin-top: 4px; text-align: center; white-space: nowrap; box-shadow: 0 4px 14px rgba(0,0,0,0.6);">
                            <div style="font-size: 8px; font-weight: 800; color: #ff3b30; letter-spacing: 0.6px; text-transform: uppercase;">HIGH PROBABILITY SOURCE</div>
                            <div style="font-size: 11px; font-weight: 800; color: #ffffff;">${vesselName}</div>
                            <div style="font-size: 9px; font-family: var(--font-mono); color: #cde0f5;">MMSI: ${mmsi}</div>
                        </div>
                    </div>
                `,
                iconSize: [160, 75]
            }),
            zIndexOffset: 1500
        }).addTo(this.layers.demoTrack);

        vesselMarker.bindPopup(`
            <div style="font-family: -apple-system, sans-serif; font-size: 11.5px; color: #ffffff; background: #0c1a2e; padding: 14px; border-radius: 14px; border: 1.5px solid #ff3b30; box-shadow: 0 16px 36px rgba(0,0,0,0.9); min-width: 250px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 6px; margin-bottom: 8px;">
                    <b style="color: #ff3b30; font-size: 13px;">${vesselName}</b>
                    <span style="font-weight: 700; color: #ff3b30; font-size: 9.5px; background: rgba(255,59,48,0.15); padding: 2px 6px; border-radius: 6px;">
                        HIGH PROBABILITY SOURCE
                    </span>
                </div>
                <b>MMSI:</b> ${mmsi}<br>
                <b>SATELLITE ACQUISITION:</b> ${acqTime}<br>
                <b>CLOSEST AIS OBS:</b> ${aisTime}<br>
                <b>TEMPORAL DELTA (Δt):</b> <b style="color: #30d158;">${dtSec} sec</b> (${dtMin.toFixed(6)} min)<br>
                <b>TRACK RECORD:</b> ${ptCount} original AIS points<br>
                <b>SYNTHETIC POINTS:</b> <b style="color: #30d158;">${synthCount}</b><br>
                <div style="margin-top: 8px; font-size: 9.5px; color: #8ca3bf; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 6px;">
                    SOURCE: NOAA/USCG AUTHENTIC AIS PARQUET<br>
                    MATCHED REAL SATELLITE SCENE
                </div>
            </div>
        `);

        // Automatically Zoom Map to actual Satellite & AIS Area
        const allBounds = L.latLngBounds([L.latLng(this.centerLat, this.centerLng), ...latlngs]);
        this.map.flyToBounds(allBounds, { padding: [80, 80], maxZoom: 11, duration: 1.2 });
    }

    // STEP 6 drawing: an amber dashed line (with particles) from the #1 candidate ship to
    // the probable origin. If a recorded track exists it follows the track first, then
    // jumps to the origin. Ships are then re-drawn with #1 highlighted in red.
    renderCorrelationTrace(candidateData, realAisMatch = null) {
        this.layers.correlationTrace.clearLayers();
        if (!candidateData) {
            delete this.activeParticlePaths['correlation'];
            return;
        }

        const vesselName = candidateData.vessel_name || "MOST PROBABLE VESSEL";
        const mmsi = candidateData.mmsi || "N/A";
        const aisCoords = candidateData.ais_coordinates || {};
        const vesselLat = aisCoords.lat !== undefined ? aisCoords.lat : (realAisMatch ? (realAisMatch.closest_ais_lat || realAisMatch.ais_coordinates?.lat) : null);
        const vesselLng = aisCoords.lon !== undefined ? aisCoords.lon : (realAisMatch ? (realAisMatch.closest_ais_lon || realAisMatch.ais_coordinates?.lon) : null);

        const targetOriginLat = this.originLat || this.centerLat;
        const targetOriginLng = this.originLng || this.centerLng;

        if (!vesselLat || !vesselLng || !targetOriginLat || !targetOriginLng) {
            console.warn("[AQUA SHIELD CORRELATION TRACE] Missing vessel or origin coordinates for correlation trace.");
            delete this.activeParticlePaths['correlation'];
            return;
        }

        // 1. Determine geometry: Check if actual trajectory points exist between vessel and origin
        let correlationPath = [];
        let isGap = false;
        const hasHistory = candidateData.has_historical_track;

        const pts = (realAisMatch && hasHistory) ? (realAisMatch.trajectory_points || []) : [];
        if (pts.length >= 2) {
            correlationPath = pts.map(pt => [pt.latitude || pt.lat, pt.longitude || pt.lng]);
            const lastPt = correlationPath[correlationPath.length - 1];
            const distToOrigin = Math.hypot(lastPt[0] - targetOriginLat, lastPt[1] - targetOriginLng);
            if (distToOrigin > 0.001) {
                correlationPath.push([targetOriginLat, targetOriginLng]);
                isGap = true;
            }
        } else {
            correlationPath = [[vesselLat, vesselLng], [targetOriginLat, targetOriginLng]];
            isGap = true;
        }

        // 2. Draw Warm Amber/Orange Correlation Polyline (Amber/Gold #ff9f0a with soft glow)
        L.polyline(correlationPath, {
            color: '#ff9f0a',
            weight: 4.0,
            dashArray: '8, 6',
            opacity: 0.95,
            className: 'correlation-trace-polyline'
        }).addTo(this.layers.correlationTrace);

        // 3. Attach Animated Canvas Particles: VESSEL -> PROBABLE SPILL ORIGIN
        const corrLatLngs = correlationPath.map(c => L.latLng(c[0], c[1]));
        this.activeParticlePaths['correlation'] = {
            latlngs: corrLatLngs,
            color: '#ff9f0a',
            speed: 0.18
        };

        // 4. Update vessel layer: Re-render all surrounding vessels with #1 selected in red
        if (this.rawVessels && this.rawVessels.length > 0) {
            this.renderVessels(this.rawVessels, mmsi);
        }

        // 6. Camera: Fit bounds to include selected vessel, origin, and surrounding context without zooming in too tight
        const allPoints = [...corrLatLngs, L.latLng(targetOriginLat, targetOriginLng)];
        this.map.flyToBounds(L.latLngBounds(allPoints), { padding: [80, 80], maxZoom: 10, duration: 1.2 });
        console.log(`[AQUA SHIELD CAMERA CORRELATION] Fitted bounds preserving surrounding vessel context.`);
    }

    // Remove the correlation line/particles and un-highlight the #1 ship
    clearCorrelationTrace() {
        delete this.activeParticlePaths['correlation'];
        this.layers.correlationTrace.clearLayers();
        if (this.rawVessels && this.rawVessels.length > 0) {
            this.renderVessels(this.rawVessels, null);
        }
    }

    // Remove any drawn ship track and its particles
    clearRecordedDemoTrack() {
        delete this.activeParticlePaths['vessel'];
        this.layers.demoTrack.clearLayers();
    }
}

// Global instance
// Expose the class on `window` so app.js can do `new window.AquaShieldMap(...)`
window.AquaShieldMap = AquaShieldMapEngine;

