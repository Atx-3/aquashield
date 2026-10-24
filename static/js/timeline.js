/**
 * AQUA SHIELD: Temporal Scrubber & Hydrodynamic Playback Engine
 *
 * A time slider with 9 positions from -24h (past) through "now" to +24h (future),
 * plus play / pause / step buttons. Choosing a position asks the backend for the
 * state at that time and moves the map camera to the hindcast (past) or forecast (future).
 *
 * NOTE: the HTML page currently has no timeline elements (no #timeline-track-nodes,
 * #temporal-current-label, #intel-spill-area), and the backend has no
 * /api/timeline_state route, so this module loads but has no visible effect.
 */

class AquaShieldTimelineController {
    constructor(mapEngine) {
        this.mapEngine = mapEngine;     // the map, so we can move its camera
        this.offsets = ['-24h', '-12h', '-6h', '-2h', 'now', '+2h', '+6h', '+12h', '+24h'];
        this.currentIndex = 4; // Default to 'now'
        this.isPlaying = false;
        this.playbackTimer = null;      // id returned by setInterval, needed to stop it
        this.playbackSpeedMs = 1800;    // 1.8 s per step while playing
    }

    init() {
        this.renderTimelineNodes();
        this.bindEvents();
        this.setOffset('now');
    }

    // Creates one clickable dot + label per time offset inside #timeline-track-nodes
    renderTimelineNodes() {
        const trackContainer = document.getElementById('timeline-track-nodes');
        if (!trackContainer) return;

        trackContainer.innerHTML = '';
        this.offsets.forEach((offset, idx) => {
            const isNow = offset === 'now';
            const isForecast = offset.startsWith('+');
            const isHindcast = offset.startsWith('-');

            // CSS classes decide the look: now-node, forecast-node, active
            const node = document.createElement('div');
            node.className = `timeline-node ${isNow ? 'now-node' : ''} ${isForecast ? 'forecast-node' : ''} ${idx === this.currentIndex ? 'active' : ''}`;
            node.dataset.offset = offset;
            node.dataset.index = idx;

            node.innerHTML = `
                <span class="node-label">${offset.toUpperCase()}</span>
                <div class="node-dot"></div>
            `;

            // Clicking a node stops playback and jumps to that time
            node.addEventListener('click', () => {
                this.pause();
                this.setIndex(idx);
            });

            trackContainer.appendChild(node);
        });
    }

    // Play/pause, previous, next, first and last buttons
    bindEvents() {
        const playBtn = document.getElementById('btn-play-pause');
        const prevBtn = document.getElementById('btn-step-prev');
        const nextBtn = document.getElementById('btn-step-next');
        const firstBtn = document.getElementById('btn-step-first');
        const lastBtn = document.getElementById('btn-step-last');

        if (playBtn) playBtn.addEventListener('click', () => this.togglePlay());
        if (prevBtn) prevBtn.addEventListener('click', () => { this.pause(); this.step(-1); });
        if (nextBtn) nextBtn.addEventListener('click', () => { this.pause(); this.step(1); });
        if (firstBtn) firstBtn.addEventListener('click', () => { this.pause(); this.setIndex(0); });
        if (lastBtn) lastBtn.addEventListener('click', () => { this.pause(); this.setIndex(this.offsets.length - 1); });
    }

    // Go to position number idx (ignores out-of-range values)
    setIndex(idx) {
        if (idx < 0 || idx >= this.offsets.length) return;
        this.currentIndex = idx;
        const offset = this.offsets[idx];
        this.setOffset(offset);
    }

    // Highlight the chosen node, update the time label, then fetch that time's state
    async setOffset(offset) {
        // Highlight active node in DOM
        const nodes = document.querySelectorAll('.timeline-node');
        nodes.forEach(n => {
            n.classList.toggle('active', n.dataset.offset === offset);
        });

        // Update NOW label / current time indicator
        const timeDisplay = document.getElementById('temporal-current-label');
        if (timeDisplay) {
            timeDisplay.textContent = offset === 'now' ? '14:32:18 UTC (NOW)' : `OFFSET: ${offset.toUpperCase()}`;
        }

        try {
            const res = await fetch(`/api/timeline_state/${offset}`);
            const data = await res.json();
            this.applyStateToHUD(data);
        } catch (e) {
            console.error("Timeline state error:", e);
        }
    }

    // Show the returned spill area and move the camera for past/future modes
    applyStateToHUD(state) {
        // Update Area and Status cards
        const areaEl = document.getElementById('intel-spill-area');
        if (areaEl) areaEl.textContent = `${state.slick_area_km2} km²`;

        // Adjust map camera or slick if hindcast/forecast
        if (state.mode === 'hindcast') {
            this.mapEngine.showHindcast();
        } else if (state.mode === 'forecast') {
            this.mapEngine.showForecast();
        }
    }

    // Move forward (+1) or backward (-1), clamped to the first/last position
    step(delta) {
        let newIdx = this.currentIndex + delta;
        if (newIdx < 0) newIdx = 0;
        if (newIdx >= this.offsets.length) newIdx = this.offsets.length - 1;
        this.setIndex(newIdx);
    }

    togglePlay() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    // Auto-advance one step every playbackSpeedMs; after the last step, wrap to the first
    play() {
        this.isPlaying = true;
        const playBtn = document.getElementById('btn-play-pause');
        if (playBtn) playBtn.innerHTML = '❚❚ PAUSE';

        this.playbackTimer = setInterval(() => {
            if (this.currentIndex >= this.offsets.length - 1) {
                this.setIndex(0); // Loop back to start
            } else {
                this.step(1);
            }
        }, this.playbackSpeedMs);
    }

    // Stop auto-advance
    pause() {
        this.isPlaying = false;
        const playBtn = document.getElementById('btn-play-pause');
        if (playBtn) playBtn.innerHTML = '▶ PLAY';
        if (this.playbackTimer) {
            clearInterval(this.playbackTimer);
            this.playbackTimer = null;
        }
    }
}

// Expose the class so app.js can create it
window.AquaShieldTimeline = AquaShieldTimelineController;
