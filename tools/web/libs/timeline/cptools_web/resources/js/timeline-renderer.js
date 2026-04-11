/**
 * Timeline Renderer - Modern Visualization Library
 * A lightweight, framework-agnostic timeline visualization component
 * 
 * @version 1.0.0
 * @license MIT
 */

class TimelineRenderer {
    constructor(options = {}) {
        this.options = {
            container: options.container || document.body,
            showTooltip: options.showTooltip !== false,
            enableZoom: options.enableZoom !== false,
            enableClick: options.enableClick !== false,
            onSegmentClick: options.onSegmentClick || null,
            onMarkerClick: options.onMarkerClick || null,
            tooltipFormatter: options.tooltipFormatter || null,
            ...options
        };

        this.timelines = [];
        this.tooltip = null;
        this.init();
    }

    init() {
        // Create tooltip if enabled
        if (this.options.showTooltip) {
            this.createTooltip();
        }
    }

    createTooltip() {
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'timeline-tooltip';
        this.tooltip.innerHTML = `
            <div class="timeline-tooltip-title"></div>
            <div class="timeline-tooltip-content"></div>
        `;
        document.body.appendChild(this.tooltip);
    }

    /**
     * Render a timeline
     * @param {Object} data - Timeline data object
     * @returns {HTMLElement} - Timeline container element
     */
    render(data) {
        const container = this.createTimelineContainer(data);
        
        if (typeof this.options.container === 'string') {
            document.querySelector(this.options.container).appendChild(container);
        } else {
            this.options.container.appendChild(container);
        }

        this.timelines.push({ id: data.id, element: container, data });
        return container;
    }

    /**
     * Render multiple timelines
     * @param {Array} dataArray - Array of timeline data objects
     */
    renderMultiple(dataArray) {
        return dataArray.map(data => this.render(data));
    }

    createTimelineContainer(timeline) {
        const container = document.createElement('div');
        container.className = 'timeline-container';
        container.id = timeline.id;
        container.dataset.timelineId = timeline.id;

        // Header
        const header = this.createHeader(timeline);
        container.appendChild(header);

        // Tracks
        const wrapper = document.createElement('div');
        wrapper.className = 'timeline-wrapper';

        timeline.tracks.forEach((track, trackIndex) => {
            const trackElement = this.createTrack(track, trackIndex, timeline);
            wrapper.appendChild(trackElement);
        });

        container.appendChild(wrapper);
        return container;
    }

    createHeader(timeline) {
        const header = document.createElement('div');
        header.className = 'timeline-header';

        const title = document.createElement('div');
        title.className = 'timeline-title';
        title.textContent = timeline.title || 'Timeline';
        header.appendChild(title);

        if (timeline.duration_ms) {
            const duration = document.createElement('div');
            duration.className = 'timeline-duration';
            duration.textContent = `Duration: ${(timeline.duration_ms / 1000).toFixed(2)}s`;
            header.appendChild(duration);
        }

        return header;
    }

    createTrack(track, trackIndex, timeline) {
        const trackDiv = document.createElement('div');
        trackDiv.className = 'timeline-track';
        trackDiv.dataset.trackIndex = trackIndex;

        // Label
        const label = document.createElement('span');
        label.className = 'timeline-track-label';
        label.textContent = track.name || `Track ${trackIndex + 1}`;
        trackDiv.appendChild(label);

        // Bar
        const bar = document.createElement('div');
        bar.className = 'timeline-track-bar';
        bar.dataset.trackId = track.id || `track-${trackIndex}`;

        // Segments
        if (track.segments && track.segments.length > 0) {
            track.segments.forEach(segment => {
                const segmentElement = this.createSegment(segment, track, trackIndex, timeline);
                bar.appendChild(segmentElement);
            });
        }

        // Markers
        if (track.markers && track.markers.length > 0) {
            track.markers.forEach(marker => {
                const markerElement = this.createMarker(marker, track, timeline);
                bar.appendChild(markerElement);
            });
        }

        trackDiv.appendChild(bar);
        return trackDiv;
    }

    createSegment(segment, track, trackIndex, timeline) {
        const segDiv = document.createElement('div');
        segDiv.className = 'timeline-segment';
        
        // Position and size
        const leftPct = (segment.start_ms / timeline.duration_ms) * 100;
        const widthPct = ((segment.end_ms - segment.start_ms) / timeline.duration_ms) * 100;
        segDiv.style.left = `${leftPct}%`;
        segDiv.style.width = `${widthPct}%`;

        // Track index for styling
        segDiv.dataset.trackIndex = trackIndex;

        // Custom class
        if (segment.className) {
            segDiv.classList.add(segment.className);
        }

        // Label
        const label = document.createElement('span');
        label.className = 'timeline-segment-label';
        label.textContent = segment.label || '';
        segDiv.appendChild(label);

        // Data attributes
        segDiv.dataset.start = (segment.start_ms / 1000).toFixed(3);
        segDiv.dataset.end = (segment.end_ms / 1000).toFixed(3);
        segDiv.dataset.duration = ((segment.end_ms - segment.start_ms) / 1000).toFixed(3);
        
        // Store custom data
        if (segment.data) {
            Object.entries(segment.data).forEach(([key, value]) => {
                segDiv.dataset[key] = value;
            });
        }

        // Event handlers
        if (this.options.enableClick) {
            segDiv.addEventListener('click', (e) => this.handleSegmentClick(e, segment, track, timeline));
        }

        if (this.options.showTooltip) {
            segDiv.addEventListener('mouseenter', (e) => this.showTooltip(e, segment, track));
            segDiv.addEventListener('mouseleave', () => this.hideTooltip());
        }

        return segDiv;
    }

    createMarker(marker, track, timeline) {
        const markerDiv = document.createElement('div');
        markerDiv.className = 'timeline-marker';
        
        const leftPct = (marker.position_ms / timeline.duration_ms) * 100;
        markerDiv.style.left = `${leftPct}%`;
        markerDiv.dataset.label = marker.label || '';
        markerDiv.dataset.position = (marker.position_ms / 1000).toFixed(3);

        // Store custom data
        if (marker.data) {
            Object.entries(marker.data).forEach(([key, value]) => {
                markerDiv.dataset[key] = value;
            });
        }

        // Event handlers
        if (this.options.enableClick) {
            markerDiv.addEventListener('click', (e) => this.handleMarkerClick(e, marker, track, timeline));
        }

        return markerDiv;
    }

    handleSegmentClick(event, segment, track, timeline) {
        // Visual feedback
        event.target.style.transform = 'translateY(-3px) scale(1.05)';
        setTimeout(() => {
            event.target.style.transform = '';
        }, 200);

        // Custom callback
        if (this.options.onSegmentClick) {
            this.options.onSegmentClick(segment, track, timeline, event);
        }
    }

    handleMarkerClick(event, marker, track, timeline) {
        if (this.options.onMarkerClick) {
            this.options.onMarkerClick(marker, track, timeline, event);
        }
    }

    showTooltip(event, segment, track) {
        if (!this.tooltip) return;

        const title = this.tooltip.querySelector('.timeline-tooltip-title');
        const content = this.tooltip.querySelector('.timeline-tooltip-content');

        // Use custom formatter if provided
        if (this.options.tooltipFormatter) {
            const formatted = this.options.tooltipFormatter(segment, track);
            title.textContent = formatted.title;
            content.innerHTML = formatted.content;
        } else {
            // Default formatting
            title.textContent = `${track.name} - ${segment.label}`;
            
            let html = '';
            html += `<div class="timeline-tooltip-item"><span class="timeline-tooltip-label">Start:</span><span class="timeline-tooltip-value">${(segment.start_ms / 1000).toFixed(3)}s</span></div>`;
            html += `<div class="timeline-tooltip-item"><span class="timeline-tooltip-label">End:</span><span class="timeline-tooltip-value">${(segment.end_ms / 1000).toFixed(3)}s</span></div>`;
            html += `<div class="timeline-tooltip-item"><span class="timeline-tooltip-label">Duration:</span><span class="timeline-tooltip-value">${((segment.end_ms - segment.start_ms) / 1000).toFixed(3)}s</span></div>`;
            
            if (segment.data) {
                Object.entries(segment.data).forEach(([key, value]) => {
                    html += `<div class="timeline-tooltip-item"><span class="timeline-tooltip-label">${key}:</span><span class="timeline-tooltip-value">${value}</span></div>`;
                });
            }

            content.innerHTML = html;
        }

        this.tooltip.classList.add('show');
        
        // Position tooltip
        const rect = event.target.getBoundingClientRect();
        this.tooltip.style.left = `${rect.left + rect.width / 2}px`;
        this.tooltip.style.top = `${rect.top - this.tooltip.offsetHeight - 10}px`;
    }

    hideTooltip() {
        if (this.tooltip) {
            this.tooltip.classList.remove('show');
        }
    }

    /**
     * Update timeline data
     * @param {string} timelineId - Timeline ID
     * @param {Object} newData - New timeline data
     */
    update(timelineId, newData) {
        const timeline = this.timelines.find(t => t.id === timelineId);
        if (!timeline) return;

        const newContainer = this.createTimelineContainer(newData);
        timeline.element.replaceWith(newContainer);
        timeline.element = newContainer;
        timeline.data = newData;
    }

    /**
     * Remove a timeline
     * @param {string} timelineId - Timeline ID
     */
    remove(timelineId) {
        const index = this.timelines.findIndex(t => t.id === timelineId);
        if (index === -1) return;

        this.timelines[index].element.remove();
        this.timelines.splice(index, 1);
    }

    /**
     * Clear all timelines
     */
    clear() {
        this.timelines.forEach(t => t.element.remove());
        this.timelines = [];
    }

    /**
     * Get timeline data
     * @param {string} timelineId - Timeline ID
     * @returns {Object} - Timeline data
     */
    getData(timelineId) {
        const timeline = this.timelines.find(t => t.id === timelineId);
        return timeline ? timeline.data : null;
    }

    /**
     * Export timeline data as JSON
     * @param {string} timelineId - Timeline ID (optional, exports all if not provided)
     * @returns {string} - JSON string
     */
    exportJSON(timelineId) {
        if (timelineId) {
            const data = this.getData(timelineId);
            return JSON.stringify(data, null, 2);
        }
        return JSON.stringify(this.timelines.map(t => t.data), null, 2);
    }

    /**
     * Destroy the renderer and clean up
     */
    destroy() {
        this.clear();
        if (this.tooltip) {
            this.tooltip.remove();
            this.tooltip = null;
        }
    }
}

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TimelineRenderer;
}
if (typeof define === 'function' && define.amd) {
    define([], function() { return TimelineRenderer; });
}
if (typeof window !== 'undefined') {
    window.TimelineRenderer = TimelineRenderer;
}
