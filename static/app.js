// StarkHub JavaScript
let currentTab = 'home';
let refreshInterval = null;

// Make sendChatMessage globally accessible
window.sendFloatingChat = function() {
    console.log('🔥 sendFloatingChat called directly');
    sendChatMessage('floatingChatMessages', 'floatingChatInput');
};

window.toggleChatWidget = function() {
    const widget = document.getElementById('floatingChatWidget');
    if (widget) {
        widget.classList.toggle('collapsed');
        const icon = document.querySelector('#chatWidgetToggle .chat-toggle-icon');
        if (icon) {
            icon.textContent = widget.classList.contains('collapsed') ? '+' : '−';
        }
    }
};

// Make brief functions globally accessible
window.buildRetrievalPack = buildRetrievalPack;
window.generateBrief = generateBrief;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing dashboard...');
    initTabs();
    initTimeDisplay();
    loadAllData();
    
    // Load Stark decision engine for home dashboard
    console.log('📊 Loading Stark decision engine...');
    loadStarkDecision();
    loadSynthesis();
    
    setupRefreshInterval();
    setupEventListeners();
    loadAnalysis();
    loadNewsSynthesis();
    
    // Test chat elements immediately
    setTimeout(() => {
        const input = document.getElementById('floatingChatInput');
        const btn = document.getElementById('floatingSendChatBtn');
        const messages = document.getElementById('floatingChatMessages');
        console.log('🔍 Chat elements check:', {
            input: !!input,
            btn: !!btn,
            messages: !!messages,
            sendFloatingChat: typeof window.sendFloatingChat
        });
        
        if (btn) {
            // Force attach onclick as backup
            btn.onclick = function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log('🔥 Button onclick fired');
                window.sendFloatingChat();
            };
        }
    }, 1000);
    
    console.log('✅ Dashboard initialized');
});

// Tab Navigation
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    currentTab = tabId;
    
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tabId}-tab`);
    });
    
    // Update chat widget visibility
    updateChatWidgetVisibility();
    
    // Load data for the tab if needed
    if (tabId === 'news') {
        loadFullNews();
        loadNewsSynthesis();
    } else if (tabId === 'analysis') {
        loadAnalysis();
    } else if (tabId === 'home') {
        loadStarkDecision();
        loadPulse();
        loadDashboardTasks();
        loadSynthesis();
    }
}

// Time Display
function initTimeDisplay() {
    updateTime();
    setInterval(updateTime, 1000);
}

function updateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { 
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    document.getElementById('timeDisplay').textContent = timeStr;
}

// Data Loading
async function loadAllData() {
    await Promise.all([
        loadHeadlines(),
        loadPulse(),
        loadTasks()
    ]);
    updateLastUpdate();
}

async function loadHeadlines() {
    try {
        const response = await fetch('/api/headlines');
        const headlines = await response.json();
        renderHeadlines(headlines.slice(0, 10), 'newsContent');
    } catch (error) {
        console.error('Error loading headlines:', error);
        document.getElementById('newsContent').innerHTML = '<div class="loading">Error loading headlines</div>';
    }
}

async function loadFullNews() {
    try {
        const response = await fetch('/api/headlines');
        const headlines = await response.json();
        renderFullNews(headlines);
    } catch (error) {
        console.error('Error loading news:', error);
        document.getElementById('fullNewsContent').innerHTML = '<div class="loading">Error loading news</div>';
    }
}

async function loadPulse() {
    const container = document.getElementById('pulseContent');
    container.innerHTML = '<div class="loading">Loading market data...</div>';
    
    try {
        const response = await fetch('/api/pulse');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const pulse = await response.json();
        renderPulse(pulse);
    } catch (error) {
        console.error('Error loading pulse:', error);
        container.innerHTML = '<div class="loading" style="color: var(--accent-red);">Error loading market data. Retrying...</div>';
        // Retry after 3 seconds
        setTimeout(loadPulse, 3000);
    }
}

async function loadTasks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        renderTasks(tasks);
        renderOpsTasks(tasks);
        renderDashboardTasks(tasks);
    } catch (error) {
        console.error('Error loading tasks:', error);
    }
}

async function loadDashboardTasks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        renderDashboardTasks(tasks);
    } catch (error) {
        console.error('Error loading dashboard tasks:', error);
    }
}

function renderDashboardTasks(tasks) {
    const container = document.getElementById('dashboardTasksContent');
    if (!container) return;
    
    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="loading">No tasks. Add one in TASKS tab.</div>';
        return;
    }
    
    container.innerHTML = tasks.slice(0, 5).map(t => `
        <div class="task-row" onclick="completeTask(${t.id})">
            <span class="task-id">#${t.id}</span>
            <span class="task-title">${escapeHtml(t.title)}</span>
        </div>
    `).join('');
}

// Rendering Functions
function renderHeadlines(headlines, containerId) {
    const container = document.getElementById(containerId);
    if (!headlines || headlines.length === 0) {
        container.innerHTML = '<div class="loading">No headlines available</div>';
        return;
    }
    
    container.innerHTML = headlines.map(h => {
        const date = new Date(h.published_ts * 1000);
        const timeStr = date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
        return `
            <div class="news-item" onclick="window.open('${h.link}', '_blank')">
                <div class="news-time">${timeStr}</div>
                <div class="news-title">${escapeHtml(h.title)}</div>
                <div class="news-source">${escapeHtml(h.source)}</div>
            </div>
        `;
    }).join('');
}

function renderFullNews(headlines) {
    const container = document.getElementById('fullNewsContent');
    if (!headlines || headlines.length === 0) {
        container.innerHTML = '<div class="loading">No news available</div>';
        return;
    }
    
    container.innerHTML = headlines.map(h => {
        const date = new Date(h.published_ts * 1000);
        const dateStr = date.toLocaleDateString('en-US', { 
            weekday: 'short',
            hour: '2-digit', 
            minute: '2-digit' 
        });
        return `
            <div class="news-item" onclick="window.open('${h.link}', '_blank')">
                <div class="news-time">${dateStr}</div>
                <div class="news-title">${escapeHtml(h.title)}</div>
                <div class="news-source">${escapeHtml(h.source)}</div>
                <div style="margin-top: 5px; font-size: 11px; color: var(--stark-text-dim);">${escapeHtml(h.link)}</div>
            </div>
        `;
    }).join('');
}

function renderPulse(pulse) {
    const container = document.getElementById('pulseContent');
    if (!pulse || pulse.length === 0) {
        container.innerHTML = '<div class="loading">No market data available</div>';
        return;
    }
    
    const validData = pulse.filter(p => p.value !== null && p.pct !== null);
    const invalidData = pulse.filter(p => p.value === null || p.pct === null);
    
    let html = '';
    
    // Show valid data first
    if (validData.length > 0) {
        html += validData.map(p => {
            const pctClass = p.pct >= 0 ? 'positive' : 'negative';
            const pctSign = p.pct >= 0 ? '+' : '';
            // Format numbers nicely
            let formattedValue = p.value.toFixed(2);
            if (p.value > 1000) {
                formattedValue = (p.value / 1000).toFixed(2) + 'K';
            }
            return `
                <div class="pulse-item">
                    <span class="pulse-label">${escapeHtml(p.label)}</span>
                    <span class="pulse-value ${pctClass}">
                        ${formattedValue} <span style="font-size: 12px; opacity: 0.8;">(${pctSign}${p.pct.toFixed(2)}%)</span>
                    </span>
                </div>
            `;
        }).join('');
    }
    
    // Show unavailable data at the bottom
    if (invalidData.length > 0) {
        html += invalidData.map(p => `
            <div class="pulse-item" style="opacity: 0.5;">
                <span class="pulse-label">${escapeHtml(p.label)}</span>
                <span class="pulse-value neutral" style="font-size: 12px;">Loading...</span>
            </div>
        `).join('');
    }
    
    if (html === '') {
        container.innerHTML = '<div class="loading">No market data available</div>';
    } else {
        container.innerHTML = html;
    }
}

function renderTasks(tasks) {
    const container = document.getElementById('tasksList');
    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="loading">No tasks. Add one above!</div>';
        return;
    }
    
    container.innerHTML = tasks.map(t => `
        <div class="task-row" onclick="completeTask(${t.id})">
            <span class="task-id">#${t.id}</span>
            <span class="task-title">${escapeHtml(t.title)}</span>
        </div>
    `).join('');
}

function renderOpsTasks(tasks) {
    const container = document.getElementById('opsContent');
    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div>No tasks. Add one in TASKS tab.</div>';
        return;
    }
    
    const topTasks = tasks.slice(0, 5);
    container.innerHTML = `
        <div style="font-weight: 600; margin-bottom: 10px; color: var(--stark-primary);">TODAY</div>
        ${topTasks.map(t => `
            <div class="task-item">
                <span style="color: var(--stark-primary);">#${t.id}</span> ${escapeHtml(t.title)}
            </div>
        `).join('')}
    `;
}

// Task Management
function setupEventListeners() {
    const taskInput = document.getElementById('taskInput');
    const addTaskBtn = document.getElementById('addTaskBtn');
    
    taskInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addTask();
        }
    });
    
    addTaskBtn.addEventListener('click', addTask);
    
    document.getElementById('refreshAllBtn').addEventListener('click', () => {
        loadAllData();
        loadStarkDecision();
    });
    
    document.getElementById('refreshNewsBtn').addEventListener('click', () => {
        loadFullNews();
    });
    
    document.getElementById('refreshAnalysisBtn').addEventListener('click', () => {
        loadAnalysis();
    });
    
    const refreshSynthesisBtn = document.getElementById('refreshSynthesisBtn');
    if (refreshSynthesisBtn) {
        refreshSynthesisBtn.addEventListener('click', () => {
            loadSynthesis();
        });
    }
    
    // Remove old refreshAnalysisHomeBtn - it doesn't exist anymore
    const refreshAnalysisHomeBtn = document.getElementById('refreshAnalysisHomeBtn');
    if (refreshAnalysisHomeBtn) {
        refreshAnalysisHomeBtn.addEventListener('click', () => {
            loadStarkDecision();
        });
    }
    
    document.getElementById('refreshHeadlinesBtn').addEventListener('click', () => {
        loadHeadlines();
    });
    
    // Stark Decision Engine refresh buttons
    const refreshRegimeBtn = document.getElementById('refreshRegimeBtn');
    if (refreshRegimeBtn) {
        refreshRegimeBtn.addEventListener('click', () => {
            console.log('🔄 Refresh regime clicked');
            loadStarkDecision();
        });
    }
    
    const refreshSignalsBtn = document.getElementById('refreshSignalsBtn');
    if (refreshSignalsBtn) {
        refreshSignalsBtn.addEventListener('click', () => {
            console.log('🔄 Refresh signals clicked');
            loadStarkDecision();
        });
    }
    
    const refreshPulseBtn = document.getElementById('refreshPulseBtn');
    if (refreshPulseBtn) {
        refreshPulseBtn.addEventListener('click', () => {
            console.log('🔄 Refresh pulse clicked');
            loadPulse();
        });
    }
    
    // Brief generation buttons
    const buildPackBtn = document.getElementById('buildPackBtn');
    const generateBriefBtn = document.getElementById('generateBriefBtn');
    
    if (buildPackBtn) {
        buildPackBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('📦 Build pack button clicked');
            buildRetrievalPack();
        });
    } else {
        console.warn('⚠️ buildPackBtn not found - will be available when brief tab is loaded');
    }
    
    if (generateBriefBtn) {
        generateBriefBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('📝 Generate brief button clicked');
            generateBrief();
        });
    } else {
        console.warn('⚠️ generateBriefBtn not found - will be available when brief tab is loaded');
    }
    
    // Chat functionality (both tab chat and floating widget)
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const floatingChatInput = document.getElementById('floatingChatInput');
    const floatingSendChatBtn = document.getElementById('floatingSendChatBtn');
    const chatWidgetToggle = document.getElementById('chatWidgetToggle');
    const chatWidgetBody = document.getElementById('chatWidgetBody');
    
    // Tab chat
    if (chatInput && sendChatBtn) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendChatMessage('chatMessages', 'chatInput');
            }
        });
        sendChatBtn.addEventListener('click', () => sendChatMessage('chatMessages', 'chatInput'));
    }
    
    // Floating chat widget - use event delegation for reliability
    console.log('🔍 Checking for floating chat elements...');
    console.log('floatingChatInput:', document.getElementById('floatingChatInput'));
    console.log('floatingSendChatBtn:', document.getElementById('floatingSendChatBtn'));
    
    // Use event delegation on document for floating chat
    document.addEventListener('click', (e) => {
        if (e.target && e.target.id === 'floatingSendChatBtn') {
            console.log('✅ Send button clicked via delegation');
            e.preventDefault();
            e.stopPropagation();
            sendChatMessage('floatingChatMessages', 'floatingChatInput');
        }
    });
    
    document.addEventListener('keypress', (e) => {
        if (e.target && e.target.id === 'floatingChatInput' && e.key === 'Enter') {
            console.log('✅ Enter pressed in floating chat via delegation');
            e.preventDefault();
            sendChatMessage('floatingChatMessages', 'floatingChatInput');
        }
    });
    
    // Also set up direct listeners if elements exist
    if (floatingChatInput && floatingSendChatBtn) {
        console.log('✅ Setting up direct floating chat listeners');
        
        const sendFloatingChat = () => {
            console.log('Sending floating chat message');
            sendChatMessage('floatingChatMessages', 'floatingChatInput');
        };
        
        floatingChatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                console.log('Enter pressed in floating chat (direct)');
                e.preventDefault();
                sendFloatingChat();
            }
        });
        
        floatingSendChatBtn.addEventListener('click', (e) => {
            console.log('Send button clicked in floating chat (direct)');
            e.preventDefault();
            e.stopPropagation();
            sendFloatingChat();
        });
    } else {
        console.warn('⚠️ Floating chat elements not found at setup time, using delegation only');
    }
    
    // Toggle chat widget
    const floatingWidget = document.getElementById('floatingChatWidget');
    if (chatWidgetToggle && floatingWidget) {
        console.log('✅ Setting up chat widget toggle');
        chatWidgetToggle.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('Toggle clicked, current state:', floatingWidget.classList.contains('collapsed'));
            floatingWidget.classList.toggle('collapsed');
            const icon = chatWidgetToggle.querySelector('.chat-toggle-icon');
            if (icon) {
                icon.textContent = floatingWidget.classList.contains('collapsed') ? '+' : '−';
            }
            console.log('New state:', floatingWidget.classList.contains('collapsed'));
        });
    } else {
        console.error('❌ Chat widget toggle elements not found:', {
            chatWidgetToggle: !!chatWidgetToggle,
            floatingWidget: !!floatingWidget
        });
    }
    
    // Show floating chat on dashboard, analysis, and news tabs
    updateChatWidgetVisibility();
}

function updateChatWidgetVisibility() {
    const floatingWidget = document.getElementById('floatingChatWidget');
    if (floatingWidget) {
        if (currentTab === 'home' || currentTab === 'analysis' || currentTab === 'news') {
            floatingWidget.style.display = 'flex';
        } else {
            floatingWidget.style.display = 'none';
        }
    }
}

async function loadSynthesis() {
    const container = document.getElementById('synthesisContent');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Synthesizing market intelligence...</div>';
    
    try {
        const response = await fetch('/api/synthesis');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        const synthesis = data.synthesis || 'No synthesis available.';
        
        // Format the synthesis with line breaks
        const formatted = synthesis.split('\n').map(line => {
            if (line.trim().match(/^\d+\./)) {
                // Numbered list item
                return `<div style="margin-top: 12px; margin-bottom: 8px; font-size: 14px; font-weight: 600; color: var(--stark-accent);">${escapeHtml(line)}</div>`;
            } else if (line.trim().match(/^[A-Z\s]+:$/)) {
                // Section header
                return `<div style="margin-top: 16px; margin-bottom: 8px; font-size: 13px; font-weight: 600; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px;">${escapeHtml(line)}</div>`;
            } else if (line.trim()) {
                // Regular content
                return `<div style="margin-bottom: 8px; font-size: 14px; line-height: 1.6; color: var(--stark-text);">${escapeHtml(line)}</div>`;
            }
            return '';
        }).join('');
        
        container.innerHTML = formatted;
    } catch (error) {
        console.error('Error loading synthesis:', error);
        container.innerHTML = `<div class="loading" style="color: var(--stark-danger);">Error loading synthesis: ${escapeHtml(error.message)}</div>`;
    }
}

async function sendChatMessage(messagesId = 'chatMessages', inputId = 'chatInput') {
    console.log('📤 sendChatMessage called with:', {messagesId, inputId});
    
    const chatInput = document.getElementById(inputId);
    const chatMessages = document.getElementById(messagesId);
    
    console.log('Elements found:', {
        chatInput: !!chatInput,
        chatMessages: !!chatMessages,
        chatInputValue: chatInput ? chatInput.value : 'N/A'
    });
    
    if (!chatInput || !chatMessages) {
        console.error('❌ Chat elements not found:', {messagesId, inputId});
        alert(`Chat elements not found: ${inputId} or ${messagesId}. Check console for details.`);
        return;
    }
    
    const question = chatInput.value.trim();
    if (!question) {
        console.log('⚠️ Empty question, not sending');
        return;
    }
    
    console.log('✅ Sending chat message:', question);
    
    // Add user message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    userMsg.innerHTML = `<div class="chat-text">${escapeHtml(question)}</div>`;
    chatMessages.appendChild(userMsg);
    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Show loading
    const loadingMsg = document.createElement('div');
    loadingMsg.className = 'chat-message system';
    loadingMsg.innerHTML = '<div class="chat-text">Thinking...</div>';
    chatMessages.appendChild(loadingMsg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    try {
        console.log('📡 Fetching /api/chat...');
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question: question})
        });
        
        console.log('📥 Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ HTTP Error:', response.status, errorText);
            throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
        }
        
        const data = await response.json();
        console.log('✅ Response data:', data);
        
        loadingMsg.remove();
        
        const botMsg = document.createElement('div');
        botMsg.className = 'chat-message bot';
        botMsg.innerHTML = `<div class="chat-text">${escapeHtml(data.response || data.error || 'No response')}</div>`;
        chatMessages.appendChild(botMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } catch (error) {
        console.error('❌ Chat error:', error);
        console.error('Error stack:', error.stack);
        loadingMsg.remove();
        const errorMsg = document.createElement('div');
        errorMsg.className = 'chat-message system';
        errorMsg.innerHTML = `<div class="chat-text" style="color: var(--stark-danger);">Error: ${escapeHtml(error.message)}</div>`;
        chatMessages.appendChild(errorMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

async function addTask() {
    const input = document.getElementById('taskInput');
    const title = input.value.trim();
    
    if (!title) return;
    
    try {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        
        if (response.ok) {
            input.value = '';
            loadTasks();
        }
    } catch (error) {
        console.error('Error adding task:', error);
        alert('Error adding task');
    }
}

async function completeTask(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}/done`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadTasks();
        }
    } catch (error) {
        console.error('Error completing task:', error);
    }
}

// Brief Generation
async function buildRetrievalPack() {
    const container = document.getElementById('briefContent');
    container.innerHTML = '<div class="loading">Building retrieval pack...</div>';
    
    try {
        const response = await fetch('/api/brief/pack');
        const pack = await response.json();
        
        let packText = `TIME: ${pack.time}\n\n`;
        packText += `MARKET PULSE:\n`;
        pack.pulse.forEach(p => {
            if (p.value !== null && p.pct !== null) {
                packText += `- ${p.label}: ${p.value.toFixed(2)} (${p.pct >= 0 ? '+' : ''}${p.pct.toFixed(2)}%)\n`;
            } else {
                packText += `- ${p.label}: N/A\n`;
            }
        });
        
        packText += `\nTOP HEADLINES (most recent):\n`;
        pack.headlines.forEach(h => {
            const date = new Date(h.published_ts * 1000);
            const dateStr = date.toLocaleString('en-US');
            packText += `- [${dateStr}] (${h.source}) ${h.title}\n`;
        });
        
        packText += `\nTASKS (open):\n`;
        pack.tasks.forEach(t => {
            packText += `- (#${t.id}) ${t.title}\n`;
        });
        
        container.textContent = packText;
    } catch (error) {
        console.error('Error building pack:', error);
        container.innerHTML = '<div class="loading">Error building retrieval pack</div>';
    }
}

async function generateBrief() {
    console.log('📝 generateBrief called');
    const container = document.getElementById('briefContent');
    if (!container) {
        console.error('briefContent container not found');
        alert('Brief content container not found');
        return;
    }
    container.innerHTML = '<div class="loading">Generating AI brief... This may take a moment.</div>';
    
    try {
        // First get the pack
        const packResponse = await fetch('/api/brief/pack');
        const pack = await packResponse.json();
        
        // Build pack text
        let packText = `TIME: ${pack.time}\n\n`;
        packText += `MARKET PULSE:\n`;
        pack.pulse.forEach(p => {
            if (p.value !== null && p.pct !== null) {
                packText += `- ${p.label}: ${p.value.toFixed(2)} (${p.pct >= 0 ? '+' : ''}${p.pct.toFixed(2)}%)\n`;
            } else {
                packText += `- ${p.label}: N/A\n`;
            }
        });
        packText += `\nTOP HEADLINES (most recent):\n`;
        pack.headlines.forEach(h => {
            const date = new Date(h.published_ts * 1000);
            const dateStr = date.toLocaleString('en-US');
            packText += `- [${dateStr}] (${h.source}) ${h.title}\n`;
        });
        packText += `\nTASKS (open):\n`;
        pack.tasks.forEach(t => {
            packText += `- (#${t.id}) ${t.title}\n`;
        });
        
        // Generate brief
        const briefResponse = await fetch('/api/brief/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pack: packText })
        });
        
        const result = await briefResponse.json();
        container.textContent = result.brief;
    } catch (error) {
        console.error('Error generating brief:', error);
        container.innerHTML = '<div class="loading">Error generating brief. Check console for details.</div>';
    }
}

// Stark Decision Engine
async function loadStarkDecision() {
    console.log('🔄 Loading Stark decision engine...');
    const whatChangedBanner = document.getElementById('whatChangedBanner');
    const regimeContent = document.getElementById('regimeContent');
    const winnersContent = document.getElementById('winnersContent');
    const losersContent = document.getElementById('losersContent');
    const opportunityContent = document.getElementById('opportunityContent');
    const horizonsContent = document.getElementById('horizonsContent');
    const breaksContent = document.getElementById('breaksContent');
    
    if (!regimeContent || !winnersContent || !losersContent) {
        console.error('❌ Missing DOM elements:', {
            regimeContent: !!regimeContent,
            winnersContent: !!winnersContent,
            losersContent: !!losersContent,
            opportunityContent: !!opportunityContent,
            horizonsContent: !!horizonsContent,
            breaksContent: !!breaksContent
        });
        return;
    }
    
    try {
        console.log('📡 Fetching /api/stark/decision...');
        const response = await fetch('/api/stark/decision');
        console.log('📥 Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ HTTP Error:', response.status, errorText);
            throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
        }
        
        const data = await response.json();
        console.log('✅ Data received:', data);
        
        if (data.error) {
            console.error('❌ API returned error:', data.error);
            renderStarkError(data.error);
            return;
        }
        
        console.log('🎨 Rendering components...');
        renderWhatChanged(data.whatChanged);
        renderRegime(data.regime);
        renderWinners(data.winners);
        renderLosers(data.losers);
        renderOpportunityZones(data.opportunityZones);
        renderTimeHorizons(data.timeHorizons);
        renderWhatBreaks(data.whatBreaks);
        
        // Render signals if available
        if (data.signals && Array.isArray(data.signals) && data.signals.length > 0) {
            renderSignals(data.signals);
        } else {
            // If no signals, show empty state
            const signalsContainer = document.getElementById('signalsContent');
            if (signalsContainer) {
                signalsContainer.innerHTML = '<div class="loading">No signals available</div>';
            }
        }
        
        // Render market sentiment
        if (data.marketSentiment) {
            renderMarketSentiment(data.marketSentiment);
        } else {
            // If no sentiment, show empty state
            const sentimentContainer = document.getElementById('sentimentContent');
            if (sentimentContainer) {
                sentimentContainer.innerHTML = '<div class="loading">No sentiment data</div>';
            }
        }
        
        // Also load tasks for dashboard
        loadDashboardTasks();
        
        console.log('✅ Stark decision engine loaded successfully');
    } catch (error) {
        console.error('❌ Error loading Stark decision:', error);
        console.error('Stack:', error.stack);
        renderStarkError(`Error: ${error.message}. Check console for details.`);
        setTimeout(loadStarkDecision, 5000); // Retry after 5 seconds
    }
}

// Removed renderVerdict - using regime instead

function renderWhatChanged(whatChanged) {
    const container = document.getElementById('whatChangedBanner');
    if (!container) return;
    if (!whatChanged || !Array.isArray(whatChanged) || whatChanged.length === 0) {
        container.innerHTML = '<div class="loading">Analyzing changes...</div>';
        return;
    }
    
    let html = '<div class="what-changed-title">WHAT CHANGED (LAST 60 MIN)</div>';
    html += '<div class="what-changed-items">';
    whatChanged.forEach(change => {
        html += `<div class="what-changed-item">• ${escapeHtml(change)}</div>`;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

function renderRegime(regime) {
    const container = document.getElementById('regimeContent');
    if (!container) return;
    if (!regime) {
        container.innerHTML = '<div class="loading">Analyzing regime...</div>';
        return;
    }
    
    // Regime is now a string, not an object
    const regimeText = typeof regime === 'string' ? regime : (regime.label || 'UNKNOWN');
    container.innerHTML = `<div style="font-size: 18px; font-weight: 600; color: var(--stark-accent); line-height: 1.6;">${escapeHtml(regimeText)}</div>`;
}

function renderWinners(winners) {
    const container = document.getElementById('winnersContent');
    if (!container) return;
    if (!winners || !Array.isArray(winners) || winners.length === 0) {
        container.innerHTML = '<div class="loading">Identifying winners...</div>';
        return;
    }
    
    let html = '';
    winners.forEach(winner => {
        html += `<div style="font-size: 15px; margin-bottom: 8px; padding-left: 8px; color: var(--stark-success);">✓ ${escapeHtml(winner)}</div>`;
    });
    container.innerHTML = html;
}

function renderLosers(losers) {
    const container = document.getElementById('losersContent');
    if (!container) return;
    if (!losers || !Array.isArray(losers) || losers.length === 0) {
        container.innerHTML = '<div class="loading">Identifying losers...</div>';
        return;
    }
    
    let html = '';
    losers.forEach(loser => {
        html += `<div style="font-size: 15px; margin-bottom: 8px; padding-left: 8px; color: var(--stark-danger);">✗ ${escapeHtml(loser)}</div>`;
    });
    container.innerHTML = html;
}

function renderOpportunityZones(opportunities) {
    const container = document.getElementById('opportunityContent');
    if (!container) return;
    if (!opportunities || !Array.isArray(opportunities) || opportunities.length === 0) {
        container.innerHTML = '<div class="loading">Identifying opportunities...</div>';
        return;
    }
    
    let html = '';
    opportunities.forEach(opp => {
        html += `<div style="font-size: 14px; margin-bottom: 8px; padding-left: 8px; color: var(--stark-accent);">• ${escapeHtml(opp)}</div>`;
    });
    container.innerHTML = html;
}

function renderTimeHorizons(horizons) {
    const container = document.getElementById('horizonsContent');
    if (!container) return;
    if (!horizons) {
        container.innerHTML = '<div class="loading">Analyzing horizons...</div>';
        return;
    }
    
    let html = '';
    
    if (horizons.shortTerm) {
        html += `<div style="margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 12px; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600;">${escapeHtml(horizons.shortTerm.horizon || 'SHORT TERM')}</div>`;
        html += `<div style="font-size: 14px; margin-bottom: 4px; color: var(--stark-text);">${escapeHtml(horizons.shortTerm.view || '')}</div>`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); margin-top: 6px;">Action: ${escapeHtml(horizons.shortTerm.action || '')}</div>`;
        html += `</div>`;
    }
    
    if (horizons.mediumTerm) {
        html += `<div style="margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 12px; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600;">${escapeHtml(horizons.mediumTerm.horizon || 'MEDIUM TERM')}</div>`;
        html += `<div style="font-size: 14px; margin-bottom: 4px; color: var(--stark-text);">${escapeHtml(horizons.mediumTerm.view || '')}</div>`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); margin-top: 6px;">Action: ${escapeHtml(horizons.mediumTerm.action || '')}</div>`;
        html += `</div>`;
    }
    
    if (horizons.longTerm) {
        html += `<div>`;
        html += `<div style="font-size: 12px; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600;">${escapeHtml(horizons.longTerm.horizon || 'LONG TERM')}</div>`;
        html += `<div style="font-size: 14px; margin-bottom: 4px; color: var(--stark-text);">${escapeHtml(horizons.longTerm.view || '')}</div>`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); margin-top: 6px;">Action: ${escapeHtml(horizons.longTerm.action || '')}</div>`;
        html += `</div>`;
    }
    
    container.innerHTML = html || '<div class="loading">No horizon data</div>';
}

function renderWhatBreaks(whatBreaks) {
    const container = document.getElementById('breaksContent');
    if (!container) return;
    if (!whatBreaks || !Array.isArray(whatBreaks) || whatBreaks.length === 0) {
        container.innerHTML = '<div class="loading">Identifying break conditions...</div>';
        return;
    }
    
    let html = '';
    whatBreaks.forEach(breakCondition => {
        html += `<div style="font-size: 15px; margin-bottom: 8px; padding-left: 8px; color: var(--stark-warning);">⚠ ${escapeHtml(breakCondition)}</div>`;
    });
    container.innerHTML = html;
}

function renderMarketSentiment(sentiment) {
    const container = document.getElementById('sentimentContent');
    if (!container) return;
    if (!sentiment) {
        container.innerHTML = '<div class="loading">Analyzing sentiment...</div>';
        return;
    }
    
    container.innerHTML = `<div style="font-size: 15px; line-height: 1.6; color: var(--stark-text);">${escapeHtml(sentiment)}</div>`;
}

function renderStance(stance, conditions) {
    const container = document.getElementById('stanceContent');
    if (!container) return;
    if (!stance) {
        container.innerHTML = '<div class="loading">Determining stance...</div>';
        return;
    }
    
    let html = `<div style="margin-bottom: 16px;">`;
    const stanceColor = stance.label && stance.label.includes('DEFENSIVE') ? 'var(--stark-warning)' : 
                       stance.label && stance.label.includes('RISK-ON') ? 'var(--stark-success)' : 'var(--stark-accent)';
    html += `<div style="font-size: 18px; font-weight: 600; color: ${stanceColor}; margin-bottom: 12px;">${escapeHtml(stance.label || 'NEUTRAL')}</div>`;
    html += `</div>`;
    
    if (stance.guidance && stance.guidance.length > 0) {
        stance.guidance.forEach(guidance => {
            html += `<div style="font-size: 15px; margin-bottom: 8px; padding-left: 8px;">• ${escapeHtml(guidance)}</div>`;
        });
    }
    
    // Add behavioral translation
    if (stance.behavioral) {
        html += `<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">${escapeHtml(stance.label)} MEANS:</div>`;
        
        if (stance.behavioral.do && stance.behavioral.do.length > 0) {
            stance.behavioral.do.forEach(action => {
                html += `<div style="font-size: 14px; margin-bottom: 6px; padding-left: 8px; color: var(--stark-success);">✓ ${escapeHtml(action)}</div>`;
            });
        }
        
        if (stance.behavioral.avoid && stance.behavioral.avoid.length > 0) {
            html += `<div style="margin-top: 12px; font-size: 13px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">AVOID:</div>`;
            stance.behavioral.avoid.forEach(action => {
                html += `<div style="font-size: 14px; margin-bottom: 6px; padding-left: 8px; color: var(--stark-danger);">✗ ${escapeHtml(action)}</div>`;
            });
        }
        
        html += `</div>`;
    }
    
    if (conditions && conditions.length > 0) {
        html += `<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Conditions to Watch:</div>`;
        conditions.forEach(condition => {
            html += `<div style="font-size: 15px; margin-bottom: 6px; padding-left: 8px;">• ${escapeHtml(condition)}</div>`;
        });
        html += `</div>`;
    }
    
    container.innerHTML = html;
}

function renderImportance(importance) {
    const container = document.getElementById('importanceContent');
    if (!container) return;
    if (!importance) {
        container.innerHTML = '<div class="loading">Ranking importance...</div>';
        return;
    }
    
    let html = '';
    
    if (importance.primary && importance.primary.length > 0) {
        html += `<div style="margin-bottom: 16px;">`;
        html += `<div style="font-size: 12px; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600;">PRIMARY DRIVER</div>`;
        importance.primary.forEach(item => {
            html += `<div style="font-size: 15px; margin-bottom: 6px; padding-left: 8px; color: var(--stark-accent);">• ${escapeHtml(item)}</div>`;
        });
        html += `</div>`;
    }
    
    if (importance.secondary && importance.secondary.length > 0) {
        html += `<div style="margin-bottom: 16px; padding-top: 12px; border-top: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 12px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">SECONDARY</div>`;
        importance.secondary.forEach(item => {
            html += `<div style="font-size: 14px; margin-bottom: 6px; padding-left: 8px;">• ${escapeHtml(item)}</div>`;
        });
        html += `</div>`;
    }
    
    if (importance.noise && importance.noise.length > 0) {
        html += `<div style="padding-top: 12px; border-top: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 12px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; opacity: 0.6;">NOISE</div>`;
        importance.noise.forEach(item => {
            html += `<div style="font-size: 13px; margin-bottom: 4px; padding-left: 8px; opacity: 0.5;">• ${escapeHtml(item)}</div>`;
        });
        html += `</div>`;
    }
    
    container.innerHTML = html || '<div class="loading">No importance data</div>';
}

function renderFocus(focus) {
    const container = document.getElementById('focusContent');
    if (!container) return;
    if (!focus) {
        container.innerHTML = '<div class="loading">Determining focus...</div>';
        return;
    }
    
    let html = '';
    
    if (focus.watch) {
        html += `<div style="margin-bottom: 16px;">`;
        html += `<div style="font-size: 13px; color: var(--stark-accent); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600;">WATCH</div>`;
        html += `<div style="font-size: 16px; font-weight: 600; color: var(--stark-text); line-height: 1.6;">${escapeHtml(focus.watch)}</div>`;
        html += `</div>`;
    }
    
    if (focus.ignore && focus.ignore.length > 0) {
        html += `<div style="padding-top: 12px; border-top: 1px solid var(--stark-border);">`;
        html += `<div style="font-size: 13px; color: var(--stark-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">IGNORE</div>`;
        focus.ignore.forEach(item => {
            html += `<div style="font-size: 14px; margin-bottom: 6px; padding-left: 8px; opacity: 0.6;">• ${escapeHtml(item)}</div>`;
        });
        html += `</div>`;
    }
    
    container.innerHTML = html || '<div class="loading">No focus data</div>';
}

function renderSignals(signals) {
    const container = document.getElementById('signalsContent');
    if (!container) return;
    if (!signals || signals.length === 0) {
        container.innerHTML = '<div class="loading">Processing signals...</div>';
        return;
    }
    
    container.innerHTML = signals.map(signal => `
        <div style="padding: 10px 0; border-bottom: 1px solid var(--stark-border);">
            <div style="font-size: 15px; line-height: 1.8;">• ${escapeHtml(signal)}</div>
        </div>
    `).join('');
}

function renderStarkError(error) {
    console.error('🚨 Rendering error:', error);
    const whatChangedBanner = document.getElementById('whatChangedBanner');
    const regimeContent = document.getElementById('regimeContent');
    const winnersContent = document.getElementById('winnersContent');
    const losersContent = document.getElementById('losersContent');
    const opportunityContent = document.getElementById('opportunityContent');
    const horizonsContent = document.getElementById('horizonsContent');
    const breaksContent = document.getElementById('breaksContent');
    
    const errorHtml = `<div style="color: var(--stark-danger); font-size: 16px; padding: 20px;">${escapeHtml(error)}<br><br>Check browser console (F12) for details.</div>`;
    
    if (whatChangedBanner) whatChangedBanner.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error</div>';
    if (regimeContent) regimeContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading regime</div>';
    if (winnersContent) winnersContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading winners</div>';
    if (losersContent) losersContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading losers</div>';
    if (opportunityContent) opportunityContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading opportunities</div>';
    if (horizonsContent) horizonsContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading horizons</div>';
    if (breaksContent) breaksContent.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading breaks</div>';
}

// Utility Functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function updateLastUpdate() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
    document.getElementById('lastUpdate').textContent = `Last update: ${timeStr}`;
}

// Market Analysis for Home Page
async function loadAnalysisHome() {
    // This is for the Analysis tab only, not the Dashboard
    const container = document.getElementById('analysisContent');
    if (!container) return; // Element doesn't exist on Dashboard tab
    
    container.innerHTML = '<div class="loading">Generating market analysis...</div>';
    
    try {
        const response = await fetch('/api/analysis');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        container.textContent = data.analysis || 'Analysis unavailable.';
    } catch (error) {
        console.error('Error loading analysis:', error);
        container.innerHTML = '<div class="loading" style="color: var(--stark-danger);">Error loading analysis. Retrying...</div>';
        setTimeout(loadAnalysisHome, 3000);
    }
}

// Market Analysis
async function loadAnalysis() {
    const container = document.getElementById('analysisContent');
    const sentimentContainer = document.getElementById('sentimentContent');
    
    container.innerHTML = '<div class="loading">Generating market analysis...</div>';
    sentimentContainer.innerHTML = '<div class="loading">Loading sentiment...</div>';
    
    try {
        const response = await fetch('/api/analysis');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        // Render analysis
        container.textContent = data.analysis || 'Analysis unavailable.';
        
        // Render sentiment
        const sentimentClass = data.sentiment || 'neutral';
        sentimentContainer.innerHTML = `
            <div class="sentiment-indicator ${sentimentClass}">${data.sentiment?.toUpperCase() || 'NEUTRAL'}</div>
            <div style="color: var(--stark-text-dim); font-size: 12px; text-align: center;">
                Market sentiment based on current data
            </div>
        `;
    } catch (error) {
        console.error('Error loading analysis:', error);
        container.innerHTML = '<div class="loading" style="color: var(--danger);">Error loading analysis. Retrying...</div>';
        setTimeout(loadAnalysis, 3000);
    }
}

// News Synthesis
async function loadNewsSynthesis() {
    const container = document.getElementById('synthesisContent');
    container.innerHTML = '<div class="loading">Synthesizing news...</div>';
    
    try {
        const response = await fetch('/api/news/synthesis');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        container.innerHTML = `
            <div style="white-space: pre-wrap; line-height: 1.8; font-size: 13px;">
                ${escapeHtml(data.synthesis || 'Synthesis unavailable.')}
            </div>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--stark-border);">
                <div style="font-size: 11px; color: var(--stark-text-dim);">
                    Sentiment: <span style="color: ${data.sentiment === 'positive' ? 'var(--success)' : data.sentiment === 'negative' ? 'var(--danger)' : 'var(--stark-text-dim)'}; font-weight: 600;">${data.sentiment?.toUpperCase() || 'NEUTRAL'}</span>
                </div>
                <div style="font-size: 11px; color: var(--stark-text-dim); margin-top: 4px;">
                    Based on ${data.headlines_count || 0} headlines
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading synthesis:', error);
        container.innerHTML = '<div class="loading" style="color: var(--danger);">Error synthesizing news. Retrying...</div>';
        setTimeout(loadNewsSynthesis, 3000);
    }
}

function setupRefreshInterval() {
    // Refresh data every 5 minutes
    refreshInterval = setInterval(() => {
        if (currentTab === 'home') {
            loadPulse();
            loadTasks();
            loadStarkDecision();
            loadSynthesis();
        } else if (currentTab === 'news') {
            loadFullNews();
            loadNewsSynthesis();
        } else if (currentTab === 'analysis') {
            loadAnalysis();
        }
        updateLastUpdate();
    }, 5 * 60 * 1000);
}

