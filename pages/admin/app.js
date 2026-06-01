/**
 * 修仙修炼插件 - 管理页面 JavaScript
 * 使用 AstrBot Plugin Page Bridge 与后端通信
 */

const bridge = window.AstrBotPluginPage;

// ==================== 全局状态 ====================
let allPlayers = {};          // { players: { group_id: { user_id: {...} } } }
let filteredPlayers = [];     // [{ group_id, user_id, ...data }]
let currentPage = 1;
const PAGE_SIZE = 15;

// ==================== DOM 元素缓存 ====================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
  // 标签页
  tabBtns: () => $$('.tab-btn'),
  tabPlayers: () => $('#tab-players'),
  tabWhitelist: () => $('#tab-whitelist'),

  // 玩家管理
  searchInput: () => $('#searchInput'),
  groupFilter: () => $('#groupFilter'),
  refreshBtn: () => $('#refreshBtn'),
  playersTbody: () => $('#playersTbody'),
  pagination: () => $('#pagination'),

  // 白名单
  newGroupInput: () => $('#newGroupInput'),
  addGroupBtn: () => $('#addGroupBtn'),
  refreshWlBtn: () => $('#refreshWlBtn'),
  whitelistList: () => $('#whitelistList'),

  // Toast
  toast: () => $('#toast'),
};

// ==================== 初始化 ====================
async function init() {
  const ctx = await bridge.ready();
  console.log('[修炼管理] Bridge ready:', ctx);

  // 绑定事件
  bindEvents();
  // 加载数据
  await loadPlayers();
  await loadWhitelist();
}

// ==================== 事件绑定 ====================
function bindEvents() {
  // 标签页切换
  els.tabBtns().forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // 搜索
  els.searchInput().addEventListener('input', debounce(applyFilters, 300));
  els.groupFilter().addEventListener('change', applyFilters);

  // 刷新
  els.refreshBtn().addEventListener('click', loadPlayers);
  els.refreshWlBtn().addEventListener('click', loadWhitelist);

  // 白名单操作
  els.addGroupBtn().addEventListener('click', addWhitelistGroup);
  els.newGroupInput().addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addWhitelistGroup();
  });
}

function switchTab(tabName) {
  els.tabBtns().forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
  els.tabPlayers().classList.toggle('active', tabName === 'players');
  els.tabWhitelist().classList.toggle('active', tabName === 'whitelist');
}

// ==================== 数据加载 ====================
async function loadPlayers() {
  try {
    const data = await bridge.apiGet('players');
    allPlayers = data.players || {};
    populateGroupFilter();
    applyFilters();
  } catch (err) {
    console.error('[修炼管理] 加载玩家数据失败:', err);
    showToast('加载玩家数据失败: ' + err.message, 'error');
  }
}

async function loadWhitelist() {
  try {
    const data = await bridge.apiGet('whitelist/get');
    renderWhitelist(data.whitelist || []);
  } catch (err) {
    console.error('[修炼管理] 加载白名单失败:', err);
    showToast('加载白名单失败: ' + err.message, 'error');
  }
}

// ==================== 群筛选下拉框 ====================
function populateGroupFilter() {
  const groups = new Set();
  for (const gid of Object.keys(allPlayers)) {
    if (Object.keys(allPlayers[gid]).length > 0) {
      groups.add(gid);
    }
  }
  const select = els.groupFilter();
  const currentVal = select.value;
  select.innerHTML = '<option value="">全部群聊</option>';
  [...groups].sort().forEach(gid => {
    const opt = document.createElement('option');
    opt.value = gid;
    opt.textContent = `群 ${gid}`;
    select.appendChild(opt);
  });
  select.value = currentVal;
}

// ==================== 过滤与分页 ====================
function applyFilters() {
  const searchTerm = els.searchInput().value.toLowerCase().trim();
  const groupFilter = els.groupFilter().value;

  const flat = [];
  for (const gid of Object.keys(allPlayers)) {
    if (groupFilter && gid !== groupFilter) continue;
    for (const uid of Object.keys(allPlayers[gid])) {
      const p = allPlayers[gid][uid];
      if (searchTerm) {
        const name = (p.name || '').toLowerCase();
        const uidStr = uid.toLowerCase();
        if (!name.includes(searchTerm) && !uidStr.includes(searchTerm)) continue;
      }
      flat.push({ group_id: gid, user_id: uid, ...p });
    }
  }

  // 按修为降序
  flat.sort((a, b) => (b.cultivation || 0) - (a.cultivation || 0));
  filteredPlayers = flat;
  currentPage = 1;
  renderTable();
  renderPagination();
}

// ==================== 表格渲染 ====================
function renderTable() {
  const tbody = els.playersTbody();
  const start = (currentPage - 1) * PAGE_SIZE;
  const page = filteredPlayers.slice(start, start + PAGE_SIZE);

  if (page.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" class="loading-cell">暂无数据</td></tr>';
    return;
  }

  tbody.innerHTML = page.map((p, idx) => {
    const globalIdx = start + idx;
    const bp = Array.isArray(p.backpack) ? p.backpack.join(', ') : (p.backpack || '');
    return `
      <tr>
        <td><code>${esc(p.group_id)}</code></td>
        <td><code>${esc(p.user_id)}</code></td>
        <td><span class="editable" data-field="name" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${esc(p.name || '未命名')}</span></td>
        <td><span class="editable" data-field="cultivation" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.cultivation ?? 0}</span></td>
        <td><span class="editable" data-field="attack" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.attack ?? 0}</span></td>
        <td><span class="editable" data-field="defense" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.defense ?? 0}</span></td>
        <td><span class="editable" data-field="speed" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.speed ?? 0}</span></td>
        <td><span class="editable" data-field="mind" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.mind ?? 0}</span></td>
        <td><span class="editable" data-field="spirit_stones" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">${p.spirit_stones ?? 0}</span></td>
        <td><span class="backpack-cell" data-field="backpack" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}" title="${esc(bp)}">${esc(bp) || '空'}</span></td>
        <td class="actions-cell">
          <button class="btn btn-sm btn-primary edit-bp-btn" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">🎒</button>
          <button class="btn btn-sm btn-danger del-btn" data-gid="${esc(p.group_id)}" data-uid="${esc(p.user_id)}">🗑</button>
        </td>
      </tr>`;
  }).join('');

  // 绑定可编辑单元格事件
  tbody.querySelectorAll('.editable').forEach(cell => {
    cell.addEventListener('click', () => startInlineEdit(cell));
  });

  // 绑定背包编辑按钮
  tbody.querySelectorAll('.edit-bp-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openBackpackEditor(btn.dataset.gid, btn.dataset.uid);
    });
  });

  // 绑定删除按钮
  tbody.querySelectorAll('.del-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      deletePlayer(btn.dataset.gid, btn.dataset.uid);
    });
  });
}

// ==================== 分页渲染 ====================
function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(filteredPlayers.length / PAGE_SIZE));
  const container = els.pagination();

  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = '';
  html += `<button ${currentPage === 1 ? 'disabled' : ''} data-page="prev">◀ 上一页</button>`;

  const maxButtons = 7;
  let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage + 1 < maxButtons) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }

  html += `<button ${currentPage === totalPages ? 'disabled' : ''} data-page="next">下一页 ▶</button>`;
  html += `<span class="page-info">共 ${filteredPlayers.length} 条 / ${totalPages} 页</span>`;

  container.innerHTML = html;

  container.querySelectorAll('button[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      const page = btn.dataset.page;
      if (page === 'prev') currentPage = Math.max(1, currentPage - 1);
      else if (page === 'next') currentPage = Math.min(totalPages, currentPage + 1);
      else currentPage = parseInt(page);
      renderTable();
      renderPagination();
    });
  });
}

// ==================== 行内编辑 ====================
function startInlineEdit(cell) {
  if (cell.classList.contains('editing')) return;

  const field = cell.dataset.field;
  const gid = cell.dataset.gid;
  const uid = cell.dataset.uid;
  const currentValue = cell.textContent.trim();

  cell.classList.add('editing');

  if (field === 'name') {
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'edit-input';
    input.value = currentValue === '未命名' ? '' : currentValue;
    input.style.width = '100px';
    cell.textContent = '';
    cell.appendChild(input);
    input.focus();
    input.select();

    const finish = async (save) => {
      if (save) {
        const newVal = input.value.trim();
        if (newVal && newVal !== (currentValue === '未命名' ? '' : currentValue)) {
          await updatePlayerField(gid, uid, field, newVal);
        }
      }
      cell.classList.remove('editing');
      cell.textContent = input.value.trim() || '未命名';
      // sync local cache
      syncLocalCache(gid, uid, field, input.value.trim() || '未命名');
    };

    input.addEventListener('blur', () => finish(true));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') finish(true);
      if (e.key === 'Escape') finish(false);
    });
  } else {
    // 数值字段
    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'edit-input';
    input.value = currentValue;
    input.style.width = '70px';
    cell.textContent = '';
    cell.appendChild(input);
    input.focus();
    input.select();

    const finish = async (save) => {
      if (save) {
        const newVal = parseInt(input.value) || 0;
        if (newVal !== parseInt(currentValue) || 0) {
          await updatePlayerField(gid, uid, field, newVal);
        }
      }
      cell.classList.remove('editing');
      cell.textContent = input.value || '0';
      syncLocalCache(gid, uid, field, parseInt(input.value) || 0);
    };

    input.addEventListener('blur', () => finish(true));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') finish(true);
      if (e.key === 'Escape') finish(false);
    });
  }
}

function syncLocalCache(gid, uid, field, value) {
  if (allPlayers[gid] && allPlayers[gid][uid]) {
    allPlayers[gid][uid][field] = value;
  }
}

// ==================== 背包编辑器弹窗 ====================
function openBackpackEditor(gid, uid) {
  const player = allPlayers[gid]?.[uid];
  if (!player) return;

  const bp = Array.isArray(player.backpack) ? player.backpack : [];
  const bpText = bp.join('\n');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box">
      <h3>🎒 编辑背包 - ${esc(player.name || uid)}</h3>
      <p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">每行一个物品</p>
      <textarea id="bpTextarea" rows="8">${esc(bpText)}</textarea>
      <div class="modal-actions">
        <button class="btn btn-secondary" id="bpCancel">取消</button>
        <button class="btn btn-primary" id="bpSave">💾 保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const textarea = overlay.querySelector('#bpTextarea');
  textarea.focus();

  overlay.querySelector('#bpCancel').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#bpSave').addEventListener('click', async () => {
    const items = textarea.value.split('\n').map(s => s.trim()).filter(Boolean);
    await updatePlayerField(gid, uid, 'backpack', items);
    overlay.remove();
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
}

// ==================== 更新玩家字段 ====================
async function updatePlayerField(gid, uid, field, value) {
  try {
    const result = await bridge.apiPost('player/update', {
      group_id: gid,
      user_id: uid,
      field: field,
      value: value,
    });
    if (result.ok) {
      syncLocalCache(gid, uid, field, value);
      showToast('✅ 修改成功', 'success');
      // 刷新显示
      applyFilters();
    } else {
      showToast('❌ 修改失败: ' + (result.msg || '未知错误'), 'error');
    }
  } catch (err) {
    showToast('❌ 请求失败: ' + err.message, 'error');
  }
}

// ==================== 删除玩家 ====================
async function deletePlayer(gid, uid) {
  const player = allPlayers[gid]?.[uid];
  const name = player?.name || uid;
  if (!confirm(`确定要删除玩家「${name}」(ID: ${uid}) 的所有数据吗？此操作不可撤销。`)) return;

  try {
    const result = await bridge.apiPost('player/delete', {
      group_id: gid,
      user_id: uid,
    });
    if (result.ok) {
      showToast(`✅ 已删除玩家「${name}」`, 'success');
      await loadPlayers();
    } else {
      showToast('❌ 删除失败: ' + (result.msg || '未知错误'), 'error');
    }
  } catch (err) {
    showToast('❌ 请求失败: ' + err.message, 'error');
  }
}

// ==================== 白名单渲染 ====================
function renderWhitelist(whitelist) {
  const container = els.whitelistList();
  if (!whitelist || whitelist.length === 0) {
    container.innerHTML = '<p class="empty-hint">📋 白名单为空，请在下方添加群号。\n\n提示：也可以在 WebUI 插件设置中直接配置 group_whitelist。</p>';
    return;
  }

  container.innerHTML = whitelist.map(gid => `
    <div class="whitelist-item">
      <div>
        <span class="group-id">${esc(String(gid))}</span>
        <span class="group-label">群聊</span>
      </div>
      <button class="btn btn-sm btn-danger wl-remove-btn" data-gid="${esc(String(gid))}">🗑 移除</button>
    </div>
  `).join('');

  container.querySelectorAll('.wl-remove-btn').forEach(btn => {
    btn.addEventListener('click', () => removeWhitelistGroup(btn.dataset.gid));
  });
}

async function addWhitelistGroup() {
  const input = els.newGroupInput();
  const gid = input.value.trim();
  if (!gid) {
    showToast('请输入群号', 'warning');
    return;
  }

  try {
    // 获取当前白名单
    const data = await bridge.apiGet('whitelist/get');
    const wl = data.whitelist || [];
    if (wl.map(String).includes(gid)) {
      showToast('该群已在白名单中', 'warning');
      return;
    }
    wl.push(gid);
    const result = await bridge.apiPost('whitelist/update', { whitelist: wl });
    if (result.ok) {
      showToast(`✅ 已添加群 ${gid}`, 'success');
      input.value = '';
      renderWhitelist(result.whitelist || wl);
    } else {
      showToast('❌ 添加失败: ' + (result.msg || '未知错误'), 'error');
    }
  } catch (err) {
    showToast('❌ 请求失败: ' + err.message, 'error');
  }
}

async function removeWhitelistGroup(gid) {
  if (!confirm(`确定将群 ${gid} 移出白名单吗？`)) return;

  try {
    const data = await bridge.apiGet('whitelist/get');
    const wl = (data.whitelist || []).filter(g => String(g) !== String(gid));
    const result = await bridge.apiPost('whitelist/update', { whitelist: wl });
    if (result.ok) {
      showToast(`✅ 已移除群 ${gid}`, 'success');
      renderWhitelist(result.whitelist || wl);
    } else {
      showToast('❌ 移除失败: ' + (result.msg || '未知错误'), 'error');
    }
  } catch (err) {
    showToast('❌ 请求失败: ' + err.message, 'error');
  }
}

// ==================== Toast ====================
let toastTimer = null;
function showToast(msg, type = 'success') {
  const toast = els.toast();
  if (toastTimer) clearTimeout(toastTimer);
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  toastTimer = setTimeout(() => {
    toast.classList.remove('show');
  }, 2500);
}

// ==================== 工具函数 ====================
function esc(str) {
  if (str === null || str === undefined) return '';
  const s = String(str);
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return s.replace(/[&<>"']/g, c => map[c]);
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ==================== 启动 ====================
init();
