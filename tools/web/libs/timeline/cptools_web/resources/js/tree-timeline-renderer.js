/**
 * Tree-Timeline Renderer - Langfuse-inspired Layout
 * Combines hierarchical tree structure with timeline visualization
 * 
 * @version 2.0.0
 * @license MIT
 */

class TreeTimelineRenderer {
    constructor(options = {}) {
        this.options = {
            container: options.container || document.body,
            onNodeClick: options.onNodeClick || null,
            showDuration: options.showDuration !== false,
            collapsible: options.collapsible !== false,
            showGridLines: options.showGridLines !== false,
            performanceThresholds: options.performanceThresholds || {
                ttft_excellent: 500,
                ttft_good: 1000
            },
            ...options
        };

        this.data = null;
        this.expandedNodes = new Set();
        this.selectedNode = null;
        this.container = null;
        this.treePanel = null;
        this.timelinePanel = null;
        this.detailsPanel = null;
    }

    /**
     * Render a trace timeline
     * @param {Object} data - Trace data with hierarchical structure
     */
    render(data) {
        this.data = data;
        this.expandedNodes.clear();

        // Expand root by default
        if (data.id) {
            this.expandedNodes.add(data.id);
        }

        // Create container
        this.createContainer();

        // Render tree and timeline
        this.renderTree();
        this.renderTimeline();

        // Sync scrolling
        this.syncScroll();

        return this.container;
    }

    createContainer() {
        // Get or create container element
        let containerEl;
        if (typeof this.options.container === 'string') {
            containerEl = document.querySelector(this.options.container);
        } else {
            containerEl = this.options.container;
        }

        // Clear existing content
        containerEl.innerHTML = '';

        // Create main container
        this.container = document.createElement('div');
        this.container.className = 'tree-timeline-container';

        // Header
        const header = document.createElement('div');
        header.className = 'tree-timeline-header';
        header.innerHTML = `
            <div class="tree-timeline-title">${this.data.name || 'Trace Timeline'}</div>
            <div class="tree-timeline-tabs">
                <div class="tree-timeline-tab active">Timeline</div>
                <div class="tree-timeline-tab">Tree</div>
            </div>
        `;
        this.container.appendChild(header);

        // Content
        const content = document.createElement('div');
        content.className = 'tree-timeline-content';

        // Tree panel
        this.treePanel = document.createElement('div');
        this.treePanel.className = 'tree-panel';
        content.appendChild(this.treePanel);

        // Timeline panel
        this.timelinePanel = document.createElement('div');
        this.timelinePanel.className = 'timeline-panel';
        content.appendChild(this.timelinePanel);

        this.container.appendChild(content);

        // Details panel (initially hidden)
        this.detailsPanel = document.createElement('div');
        this.detailsPanel.className = 'event-details-panel hidden';
        this.detailsPanel.innerHTML = `
            <div class="details-header">
                <h3>Event Details</h3>
                <button class="details-close" onclick="this.closest('.event-details-panel').classList.add('hidden')">&times;</button>
            </div>
            <div class="details-content"></div>
        `;
        this.container.appendChild(this.detailsPanel);

        containerEl.appendChild(this.container);
    }

    renderTree() {
        this.treePanel.innerHTML = '';
        const nodes = this.flattenTree(this.data);

        nodes.forEach(node => {
            const nodeEl = this.createTreeNode(node);
            this.treePanel.appendChild(nodeEl);
        });
    }

    flattenTree(node, level = 0, result = []) {
        result.push({ ...node, level });

        if (node.children && node.children.length > 0 && this.expandedNodes.has(node.id)) {
            node.children.forEach(child => {
                this.flattenTree(child, level + 1, result);
            });
        }

        return result;
    }

    createTreeNode(node) {
        const div = document.createElement('div');
        div.className = 'tree-node';
        div.dataset.nodeId = node.id;

        if (this.selectedNode === node.id) {
            div.classList.add('selected');
        }

        // Indentation
        const indent = document.createElement('span');
        indent.className = 'tree-node-indent';
        indent.style.width = `${node.level * 20}px`;
        div.appendChild(indent);

        // Expand/collapse icon
        if (node.children && node.children.length > 0) {
            const icon = document.createElement('span');
            icon.className = 'tree-node-icon';
            if (!this.expandedNodes.has(node.id)) {
                icon.classList.add('collapsed');
            }
            icon.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M5 12h14"></path>
                </svg>
            `;
            icon.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleNode(node.id);
            });
            div.appendChild(icon);
        } else {
            const spacer = document.createElement('span');
            spacer.className = 'tree-node-icon';
            div.appendChild(spacer);
        }

        // Content
        const content = document.createElement('div');
        content.className = 'tree-node-content';

        // Type badge
        const badge = document.createElement('span');
        badge.className = `tree-node-badge ${node.type.toLowerCase()}`;
        badge.textContent = node.type;
        content.appendChild(badge);

        // Name
        const name = document.createElement('span');
        name.className = 'tree-node-name';
        name.textContent = node.name;
        name.title = node.name;
        content.appendChild(name);

        div.appendChild(content);

        // Click handler
        div.addEventListener('click', () => {
            this.selectNode(node.id);
            if (this.options.onNodeClick) {
                this.options.onNodeClick(node);
            }
        });

        return div;
    }

    renderTimeline() {
        this.timelinePanel.innerHTML = '';

        // Calculate duration
        const totalDuration = this.data.end_ms - this.data.start_ms;
        const startTime = this.data.start_ms;

        // Ruler
        const ruler = this.createRuler(totalDuration);
        this.timelinePanel.appendChild(ruler);

        // Performance markers (TTFT, etc.)
        if (this.data.data && this.data.data.ttft_ms !== undefined && this.data.data.ttft_ms !== null) {
            const marker = this.createPerformanceMarker(
                this.data.data.ttft_ms,
                totalDuration,
                'TTFT',
                this.options.performanceThresholds
            );
            this.timelinePanel.appendChild(marker);
        }

        // Timeline rows
        const nodes = this.flattenTree(this.data);
        nodes.forEach(node => {
            const row = this.createTimelineRow(node, startTime, totalDuration);
            this.timelinePanel.appendChild(row);
        });
    }

    createRuler(totalDuration) {
        const ruler = document.createElement('div');
        ruler.className = 'timeline-ruler';

        // Calculate adaptive tick intervals
        const { intervals, numTicks } = this.calculateAdaptiveIntervals(totalDuration);

        // Create time ticks and grid lines
        for (let i = 0; i < numTicks; i++) {
            const time = intervals[i];
            const position = (time / totalDuration) * 100;

            // Create tick
            const tick = document.createElement('div');
            tick.className = 'timeline-ruler-tick';
            tick.textContent = this.formatDuration(time);
            tick.style.left = `${position}%`;
            ruler.appendChild(tick);

            // Create grid line
            if (this.options.showGridLines && i > 0) {
                const gridLine = document.createElement('div');
                gridLine.className = 'timeline-grid-line';
                gridLine.style.left = `${position}%`;
                ruler.appendChild(gridLine);
            }
        }

        return ruler;
    }

    calculateAdaptiveIntervals(totalDuration) {
        // Adaptive scale algorithm
        let interval, numTicks;

        if (totalDuration < 1000) {
            // < 1s: 100ms or 200ms intervals
            interval = totalDuration < 500 ? 100 : 200;
            numTicks = Math.ceil(totalDuration / interval) + 1;
        } else if (totalDuration < 10000) {
            // 1-10s: 1s or 2s intervals
            interval = totalDuration < 5000 ? 1000 : 2000;
            numTicks = Math.ceil(totalDuration / interval) + 1;
        } else {
            // > 10s: 5s intervals
            interval = 5000;
            numTicks = Math.ceil(totalDuration / interval) + 1;
        }

        // Generate intervals array
        const intervals = [];
        for (let i = 0; i < numTicks; i++) {
            intervals.push(Math.min(i * interval, totalDuration));
        }

        return { intervals, numTicks };
    }

    createTimelineRow(node, startTime, totalDuration) {
        const row = document.createElement('div');
        row.className = 'timeline-row';
        row.dataset.nodeId = node.id;

        if (this.selectedNode === node.id) {
            row.classList.add('selected');
        }

        const container = document.createElement('div');
        container.className = 'timeline-bar-container';

        const bar = document.createElement('div');
        bar.className = `timeline-bar ${node.type.toLowerCase()}`;

        // Add custom class if provided
        if (node.customClass) {
            bar.classList.add(node.customClass);
        }

        // Calculate position and width
        const nodeStart = node.start_ms - startTime;
        const nodeDuration = node.end_ms - node.start_ms;
        const leftPercent = (nodeStart / totalDuration) * 100;
        const widthPercent = (nodeDuration / totalDuration) * 100;

        bar.style.left = `${leftPercent}%`;
        bar.style.width = `${widthPercent}%`;

        // Duration label
        if (this.options.showDuration) {
            const duration = document.createElement('span');
            duration.className = 'timeline-bar-duration';
            duration.textContent = this.formatDuration(nodeDuration);
            bar.appendChild(duration);
        }

        // Add correlation ID if provided
        if (node.correlationId) {
            bar.dataset.correlationId = node.correlationId;

            // Add hover listeners for highlighting
            bar.addEventListener('mouseenter', () => this.highlightRelated(node.correlationId));
            bar.addEventListener('mouseleave', () => this.unhighlightRelated(node.correlationId));
        }

        // Click handler - show details panel
        bar.addEventListener('click', (e) => {
            e.stopPropagation();
            this.selectNode(node.id);
            this.showEventDetails(node);
            if (this.options.onNodeClick) {
                this.options.onNodeClick(node);
            }
        });

        container.appendChild(bar);
        row.appendChild(container);

        return row;
    }

    toggleNode(nodeId) {
        if (this.expandedNodes.has(nodeId)) {
            this.expandedNodes.delete(nodeId);
        } else {
            this.expandedNodes.add(nodeId);
        }
        this.renderTree();
        this.renderTimeline();
        this.syncScroll();
    }

    selectNode(nodeId) {
        this.selectedNode = nodeId;

        // Update tree nodes
        this.treePanel.querySelectorAll('.tree-node').forEach(el => {
            if (el.dataset.nodeId === nodeId) {
                el.classList.add('selected');
            } else {
                el.classList.remove('selected');
            }
        });

        // Update timeline rows
        this.timelinePanel.querySelectorAll('.timeline-row').forEach(el => {
            if (el.dataset.nodeId === nodeId) {
                el.classList.add('selected');
            } else {
                el.classList.remove('selected');
            }
        });
    }

    highlightRelated(correlationId) {
        if (!correlationId) return;
        const bars = this.timelinePanel.querySelectorAll(`.timeline-bar[data-correlation-id="${correlationId}"]`);
        bars.forEach(bar => bar.classList.add('highlight'));
    }

    unhighlightRelated(correlationId) {
        if (!correlationId) return;
        const bars = this.timelinePanel.querySelectorAll(`.timeline-bar[data-correlation-id="${correlationId}"]`);
        bars.forEach(bar => bar.classList.remove('highlight'));
    }

    syncScroll() {
        // Only setup scroll listeners once
        if (this._scrollListenersAttached) return;
        this._scrollListenersAttached = true;

        // Track which panel is the "source" of the scroll
        let scrollSource = null;

        this._syncFromTree = () => {
            if (scrollSource === 'timeline') return;
            scrollSource = 'tree';
            this.timelinePanel.scrollTop = this.treePanel.scrollTop;
            // Use requestAnimationFrame to reset after the browser has finished processing
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    scrollSource = null;
                });
            });
        };

        this._syncFromTimeline = () => {
            if (scrollSource === 'tree') return;
            scrollSource = 'timeline';
            this.treePanel.scrollTop = this.timelinePanel.scrollTop;
            // Use requestAnimationFrame to reset after the browser has finished processing
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    scrollSource = null;
                });
            });
        };

        this.treePanel.addEventListener('scroll', this._syncFromTree);
        this.timelinePanel.addEventListener('scroll', this._syncFromTimeline);
    }

    formatDuration(ms) {
        if (ms < 1000) {
            return `${ms.toFixed(0)}ms`;
        } else {
            return `${(ms / 1000).toFixed(2)}s`;
        }
    }

    createPerformanceMarker(value_ms, totalDuration, label, thresholds) {
        const marker = document.createElement('div');
        marker.className = 'performance-marker';

        // Determine color based on thresholds
        let colorClass = 'red';
        if (value_ms < thresholds.ttft_excellent) {
            colorClass = 'green';
        } else if (value_ms < thresholds.ttft_good) {
            colorClass = 'yellow';
        }

        marker.classList.add(colorClass);

        const position = (value_ms / totalDuration) * 100;
        marker.style.left = `${position}%`;

        marker.innerHTML = `
            <div class="marker-line"></div>
            <div class="marker-label">${label}: ${this.formatDuration(value_ms)}</div>
        `;

        return marker;
    }

    showEventDetails(node) {
        if (!this.detailsPanel) return;

        const content = this.detailsPanel.querySelector('.details-content');
        if (!content) return;

        // Build details HTML
        let html = `
            <div class="detail-row">
                <span class="detail-label">Type:</span>
                <span class="detail-value">
                    <span class="tree-node-badge ${node.type.toLowerCase()}">${node.type}</span>
                </span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Name:</span>
                <span class="detail-value">${node.name}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Duration:</span>
                <span class="detail-value">${this.formatDuration(node.end_ms - node.start_ms)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Start Time:</span>
                <span class="detail-value">${this.formatDuration(node.start_ms)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">End Time:</span>
                <span class="detail-value">${this.formatDuration(node.end_ms)}</span>
            </div>
        `;

        // Add custom data fields
        if (node.data) {
            for (const [key, value] of Object.entries(node.data)) {
                if (value !== null && value !== undefined && value !== '') {
                    html += `
                        <div class="detail-row">
                            <span class="detail-label">${this.formatLabel(key)}:</span>
                            <span class="detail-value">${this.formatValue(value)}</span>
                        </div>
                    `;
                }
            }
        }

        content.innerHTML = html;
        this.detailsPanel.classList.remove('hidden');
    }

    formatLabel(key) {
        // Convert snake_case to Title Case
        return key.split('_').map(word =>
            word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ');
    }

    formatValue(value) {
        if (typeof value === 'object') {
            return `<pre>${JSON.stringify(value, null, 2)}</pre>`;
        }
        if (typeof value === 'string' && value.length > 100) {
            return `<div class="long-text">${value}</div>`;
        }
        return value;
    }

    /**
     * Update the trace data
     * @param {Object} newData - New trace data
     */
    update(newData) {
        this.render(newData);
    }

    /**
     * Expand all nodes
     */
    expandAll() {
        const addAllIds = (node) => {
            this.expandedNodes.add(node.id);
            if (node.children) {
                node.children.forEach(addAllIds);
            }
        };
        addAllIds(this.data);
        this.renderTree();
        this.renderTimeline();
        this.syncScroll();
    }

    /**
     * Collapse all nodes
     */
    collapseAll() {
        this.expandedNodes.clear();
        if (this.data.id) {
            this.expandedNodes.add(this.data.id);
        }
        this.renderTree();
        this.renderTimeline();
        this.syncScroll();
    }

    /**
     * Destroy the renderer
     */
    destroy() {
        // Remove scroll event listeners
        if (this._scrollListenersAttached) {
            this.treePanel?.removeEventListener('scroll', this._syncFromTree);
            this.timelinePanel?.removeEventListener('scroll', this._syncFromTimeline);
            this._scrollListenersAttached = false;
        }
        if (this.container) {
            this.container.remove();
        }
        this.data = null;
        this.expandedNodes.clear();
        this.selectedNode = null;
    }
}

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TreeTimelineRenderer;
}
if (typeof define === 'function' && define.amd) {
    define([], function () { return TreeTimelineRenderer; });
}
if (typeof window !== 'undefined') {
    window.TreeTimelineRenderer = TreeTimelineRenderer;
}
