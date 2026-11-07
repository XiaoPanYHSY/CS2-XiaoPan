// 配置对象
const config = {
    radarSize: { width: 300, height: 300 },
    canvas: {
        playerSize: 8,
        lineWidth: 2,
        viewLineLength: 50,
        colors: {
            ct: '#5b97ff',
            t: '#ffa458',
            healthHigh: '#81c784',
            healthMed: '#ffb74d',
            healthLow: '#e57373'
        }
    }
};

// 全局变量
let currentMapName = 'de_dust2';
let loadedMapMeta = null;
let players = {};
let rotation = 0;
let currentLoadedMapName = '';
let pendingMessages = [];
let isLoadingMap = false;
let onlyShowEnemies = false;
let selfPlayerId = null;
let mapMeta = null;
let renderScheduled = false;
let canvasContext = null;
let objectPool = {
    playerMarkers: [],
    nameTags: []
};

// DOM 元素
const radarContainer = document.querySelector('.radar-container');
const playersList = document.getElementById('players-list');
const radarMap = document.getElementById('radar-map');
const radarSvg = document.getElementById('radar-svg');
const radarCanvas = document.createElement('canvas');
radarCanvas.id = 'radar-canvas';
radarContainer.appendChild(radarCanvas);

// WebSocket 连接
const ws = new WebSocket(`ws://${window.location.host}/ws`);

// 事件监听器设置
document.getElementById('hide-menu-btn').onclick = () => {
    const menu = document.getElementById('menu-buttons');
    const hideBtn = document.getElementById('hide-menu-btn');
    const siblings = Array.from(menu.children).filter(el => el !== hideBtn);
    const isHidden = siblings.every(el => el.style.display === 'none');

    if (isHidden) {
        siblings.forEach(el => el.style.display = '');
        hideBtn.textContent = '隐藏菜单';
    } else {
        siblings.forEach(el => el.style.display = 'none');
        hideBtn.textContent = '显示菜单';
    }
};

document.getElementById('toggle-enemies-btn').onclick = () => {
    onlyShowEnemies = !onlyShowEnemies;
    document.getElementById('toggle-enemies-btn').textContent = onlyShowEnemies ? '显示全部' : '只显示敌人';
    renderPlayers();
};

document.getElementById('choose-self-btn').onclick = () => {
    const panel = document.getElementById('self-select-panel');
    const select = document.getElementById('player-select');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';

    select.innerHTML = '<option value="">请选择玩家</option>';
    Object.values(players).forEach(player => {
        const option = document.createElement('option');
        option.value = player.id;
        option.textContent = player.name || `玩家 ${player.id}`;
        select.appendChild(option);
    });
};

document.getElementById('rotate-left').onclick = () => {
    rotation = (rotation + 270) % 360;
    updateRadarRotation();
    renderPlayers();
};

document.getElementById('rotate-right').onclick = () => {
    rotation = (rotation + 90) % 360;
    updateRadarRotation();
    renderPlayers();
};

// 功能函数
function confirmSelfPlayer() {
    const selectedId = document.getElementById('player-select').value;
    if (selectedId) {
        selfPlayerId = selectedId;
        renderPlayers();
    }
}

async function loadMap(mapName) {
    if (!mapName || typeof mapName !== 'string' || mapName.trim() === '') {
        console.warn('⚠️ 收到无效地图名，忽略:', mapName);
        return false;
    }

    try {
        isLoadingMap = true;
        currentMapName = mapName;
        console.log(`🌍 正在加载地图: ${currentMapName}`);
        radarMap.src = `/map/${currentMapName}/radar.png`;

        const res = await fetch(`/map/${currentMapName}/meta.json`);
        if (!res.ok) throw new Error('地图元数据加载失败');
        mapMeta = await res.json();

        rotation = 0;
        updateRadarRotation();
        console.log(`✅ 地图元数据加载成功: ${currentMapName}`);
        return true;
    } catch (err) {
        console.error(`❌ 加载地图失败: ${mapName}`, err);
        mapMeta = null;
        return false;
    } finally {
        isLoadingMap = false;
        if (pendingMessages.length > 0) {
            pendingMessages = [];
        }
    }
}

function scheduleRender() {
    if (!renderScheduled) {
        renderScheduled = true;
        requestAnimationFrame(() => {
            renderPlayers();
            renderScheduled = false;
        });
    }
}

function handleRadarUpdate(data) {
    players = {};
    for (const entity of data.entities) {
        players[entity.id] = entity;
    }
    scheduleRender();

    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
    document.getElementById('player-count').textContent = Object.keys(players).length;
}

function updateRadarRotation() {
    radarMap.style.transform = `rotate(${rotation}deg)`;
    mathCache.clear(); // 清除三角函数缓存
}

function createFlameLine(x1, y1, x2, y2) {
    const ns = "http://www.w3.org/2000/svg";
    const line = document.createElementNS(ns, "line");

    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    line.setAttribute("stroke", "url(#flameGradient)");
    line.setAttribute("stroke-width", "4");
    line.setAttribute("filter", "url(#flameGlow)");
    line.setAttribute("stroke-linecap", "round");

    const animate = document.createElementNS(ns, "animate");
    animate.setAttribute("attributeName", "stroke-width");
    animate.setAttribute("values", "3;5;3");
    animate.setAttribute("dur", "1s");
    animate.setAttribute("repeatCount", "indefinite");

    line.appendChild(animate);
    return line;
}

function initCanvas() {
    canvasContext = radarCanvas.getContext('2d');
    radarCanvas.width = config.radarSize.width;
    radarCanvas.height = config.radarSize.height;
    radarCanvas.style.position = 'absolute';
    radarCanvas.style.top = '0';
    radarCanvas.style.left = '0';
    radarCanvas.style.pointerEvents = 'none';
}

function clearCanvas() {
    canvasContext.clearRect(0, 0, radarCanvas.width, radarCanvas.height);
}

function drawPlayer(player, pos) {
    if (!canvasContext) return;

    const ctx = canvasContext;
    const size = config.canvas.playerSize;

    // 绘制玩家标记
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, size, 0, Math.PI * 2);
    ctx.fillStyle = player.team === 2 ? config.canvas.colors.t : config.canvas.colors.ct;
    ctx.fill();

    // 绘制方向线
    if (player.angles && player.angles.length >= 2) {
        const totalRotation = rotation;
        const yaw = player.angles[1];
        const rad = ((yaw - totalRotation) * Math.PI) / -180;
        const lineLength = config.canvas.viewLineLength;
        const endX = pos.x + Math.cos(rad) * lineLength;
        const endY = pos.y + Math.sin(rad) * lineLength;

        ctx.beginPath();
        ctx.moveTo(pos.x, pos.y);
        ctx.lineTo(endX, endY);
        ctx.strokeStyle = player.team === 2 ? config.canvas.colors.t : config.canvas.colors.ct;
        ctx.lineWidth = config.canvas.lineWidth;
        ctx.stroke();
    }

    // 绘制玩家名称和血量
    ctx.font = '12px Arial';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(player.name || 'Unknown', pos.x + 10, pos.y);

    const healthColor =
        player.health >= 75 ? config.canvas.colors.healthHigh :
            player.health >= 35 ? config.canvas.colors.healthMed :
                config.canvas.colors.healthLow;

    ctx.fillStyle = healthColor;
    ctx.fillText(`HP: ${player.health}`, pos.x + 10, pos.y + 15);
}

function renderPlayers() {
    if (!mapMeta || !canvasContext) return;

    clearCanvas();

    Object.values(players).forEach(player => {
        if (!player.position || player.health <= 0) return;

        if (
            onlyShowEnemies &&
            String(player.id) !== String(selfPlayerId) &&
            selfPlayerId &&
            players[selfPlayerId] &&
            player.team === players[selfPlayerId].team
        ) {
            return;
        }

        const pos = worldToRadar(player.position[0], player.position[1]);
        drawPlayer(player, pos);
    });
}

function worldToRadar(x, y) {
    if (!mapMeta) return { x: 0, y: 0 };

    let mapX = x - mapMeta.offset.x;
    let mapY = y - mapMeta.offset.y;

    let radarX = mapX / mapMeta.scale;
    let radarY = mapY / mapMeta.scale;

    radarY *= -1;

    const centerX = radarMap.clientWidth / 2;
    const centerY = radarMap.clientHeight / 2;

    const rad = rotation * Math.PI / -180;
    const cos = mathCache.getCos(rad);
    const sin = mathCache.getSin(rad);

    const relX = radarX - centerX;
    const relY = radarY - centerY;

    const rotatedX = relX * cos - (-relY) * sin;
    const rotatedY = relX * sin + (-relY) * cos;

    const finalX = rotatedX + centerX;
    const finalY = centerY - rotatedY;

    return {
        x: Math.max(0, Math.min(radarMap.clientWidth, finalX)),
        y: Math.max(0, Math.min(radarMap.clientHeight, finalY))
    };
}

function resizeRadar() {
    const container = radarContainer;
    const img = radarMap;
    const containerRatio = container.clientWidth / container.clientHeight;
    const imgRatio = img.naturalWidth / img.naturalHeight;

    if (containerRatio > imgRatio) {
        img.style.width = 'auto';
        img.style.height = '100%';
    } else {
        img.style.width = '100%';
        img.style.height = 'auto';
    }

    config.radarSize.width = img.clientWidth;
    config.radarSize.height = img.clientHeight;

    // 更新Canvas尺寸
    if (radarCanvas) {
        radarCanvas.width = config.radarSize.width;
        radarCanvas.height = config.radarSize.height;
    }

    if (Object.keys(players).length > 0) renderPlayers();
}

// WebSocket 消息处理优化
const wsHandler = {
    pingInterval: null,
    messageQueue: [],
    isProcessing: false,

    init() {
        this.setupPing();
        this.processMessageQueue();
    },

    setupPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
        }
        this.pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 5000);
    },

    cleanup() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
        this.messageQueue = [];
        this.isProcessing = false;
    },

    async processMessageQueue() {
        if (this.isProcessing || this.messageQueue.length === 0) return;

        this.isProcessing = true;
        while (this.messageQueue.length > 0) {
            const msg = this.messageQueue.shift();
            try {
                await this.handleMessage(msg);
            } catch (err) {
                console.error("⚠️ 消息处理出错:", err);
            }
        }
        this.isProcessing = false;
    },

    async handleMessage(data) {
        if (data.type === 'radar_update_all') {
            if (data.mapName && data.mapName !== currentMapName) {
                console.log(`🗺️ 地图变更：${currentMapName} → ${data.mapName}`);
                currentMapName = data.mapName;
                await loadMap(currentMapName);
            } else if (!currentMapName && data.mapName) {
                console.log(`🗺️ 初次加载地图: ${data.mapName}`);
                currentMapName = data.mapName;
                await loadMap(currentMapName);
            }

            if (isLoadingMap) {
                pendingMessages.push(data);
            } else {
                handleRadarUpdate(data);
            }
        }
    },

    addMessage(msg) {
        try {
            if (msg === "ping") return;
            const data = JSON.parse(msg);
            this.messageQueue.push(data);
            this.processMessageQueue();
        } catch (err) {
            console.error("⚠️ WebSocket 消息解析出错:", err);
        }
    }
};

// 优化计算性能
const mathCache = {
    sin: {},
    cos: {},

    getSin(angle) {
        if (!(angle in this.sin)) {
            this.sin[angle] = Math.sin(angle);
        }
        return this.sin[angle];
    },

    getCos(angle) {
        if (!(angle in this.cos)) {
            this.cos[angle] = Math.cos(angle);
        }
        return this.cos[angle];
    },

    clear() {
        this.sin = {};
        this.cos = {};
    }
};

// WebSocket 事件处理
ws.onopen = () => {
    document.getElementById('connection-status').textContent = '🟢 已连接';
    wsHandler.init();
};

ws.onclose = () => {
    document.getElementById('connection-status').textContent = '已断开';
    wsHandler.cleanup();
    setTimeout(() => location.reload(), 1000);
};

ws.onerror = (e) => {
    console.error('WebSocket 错误:', e);
    wsHandler.cleanup();
};

ws.onmessage = (event) => {
    wsHandler.addMessage(event.data);
};

// 窗口事件
window.onload = () => {
    radarMap.onload = () => {
        resizeRadar();
        initCanvas();
    };
    if (radarMap.complete) {
        resizeRadar();
        initCanvas();
    }
    loadMap(currentMapName);
    updateRadarRotation();
};

window.onresize = resizeRadar; 