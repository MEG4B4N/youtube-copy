const app = document.getElementById('app');
const toastEl = document.getElementById('toast');
let currentUser = null;
let toastTimer = null;
let commonHandlersAttached = false;

const STORAGE_KEYS = {
  history: 'streamhub:history',
  watchLater: 'streamhub:watch-later',
  downloads: 'streamhub:downloads',
};

function esc(value='') { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function duration(seconds=0) { if (!seconds) return ''; const s=Math.floor(seconds); return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`; }
function ago(date) { const d=new Date(date); const days=Math.floor((Date.now()-d.getTime())/86400000); if(days<1)return 'сегодня'; if(days<30)return `${days} дн. назад`; if(days<365)return `${Math.floor(days/30)} мес. назад`; return `${Math.floor(days/365)} г. назад`; }
function toast(message) { toastEl.textContent=message; toastEl.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>toastEl.classList.remove('show'),2700); }
async function api(path, options={}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData) && typeof options.body !== 'string') { headers.set('Content-Type','application/json'); options.body=JSON.stringify(options.body); }
  const response = await fetch(path,{...options,headers,credentials:'same-origin'});
  const type=response.headers.get('content-type')||'';
  const data=type.includes('application/json')?await response.json():null;
  if(!response.ok) throw new Error(data?.detail || `Ошибка ${response.status}`);
  return data;
}
function avatar(name, small=false){return `<div class="avatar ${small?'small':''}">${esc((name||'?').slice(0,1).toUpperCase())}</div>`;}
function icon(name) {
  const paths = {
    bookmark: '<path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-4-6 4z"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 19v2h16v-2"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]||''}</svg>`;
}
function readLocalEntries(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(value) ? value.filter(item => item && Number.isInteger(Number(item.id))) : [];
  } catch { return []; }
}
function writeLocalEntries(key, entries) {
  try { localStorage.setItem(key, JSON.stringify(entries.slice(0, 100))); return true; }
  catch { toast('Браузер не разрешил сохранить этот список'); return false; }
}
function hasLocalEntry(key, id) { return readLocalEntries(key).some(item => Number(item.id) === Number(id)); }
function rememberLocalEntry(key, id) {
  const entries = readLocalEntries(key).filter(item => Number(item.id) !== Number(id));
  entries.unshift({id: Number(id), savedAt: new Date().toISOString()});
  return writeLocalEntries(key, entries);
}
function removeLocalEntry(key, id) {
  return writeLocalEntries(key, readLocalEntries(key).filter(item => Number(item.id) !== Number(id)));
}
async function videosFromLocalList(key) {
  const entries = readLocalEntries(key);
  const videos = await Promise.all(entries.map(async item => {
    try { return await api(`/api/videos/${item.id}`); } catch { return null; }
  }));
  return videos.filter(video => video && video.status === 'ready');
}
function videoCard(v, options={}) {
  const saved = hasLocalEntry(STORAGE_KEYS.watchLater, v.id);
  const downloadAction = options.downloadAction ? `<button class="card-action card-download" type="button" data-download-video="${v.id}" aria-label="Скачать видео" title="Скачать">${icon('download')}</button>` : '';
  return `<article class="video-card" data-open-video="${v.id}"><div class="thumb-wrap">${v.thumbnail_url?`<img loading="lazy" decoding="async" src="${v.thumbnail_url}" alt="">`:''}<button class="card-action save-video-button ${saved?'is-saved':''}" type="button" data-save-video="${v.id}" aria-label="${saved?'Убрать из списка «Смотреть позже»':'Сохранить на потом'}" title="${saved?'Сохранено':'Смотреть позже'}">${icon(saved?'check':'bookmark')}</button>${downloadAction}<span class="duration">${duration(v.duration)}</span></div><div class="video-info">${avatar(v.owner.username)}<div class="video-text"><h3 class="video-title">${esc(v.title)}</h3><div class="video-meta"><a href="/channel/${encodeURIComponent(v.owner.username)}" data-link>${esc(v.owner.username)}</a><br>${Number(v.views).toLocaleString('ru-RU')} просмотров · ${ago(v.created_at)}</div></div></div></article>`;
}
function miniCard(v){return `<article class="mini-card" data-open-video="${v.id}"><div class="thumb-wrap">${v.thumbnail_url?`<img loading="lazy" decoding="async" src="${v.thumbnail_url}" alt="">`:''}<span class="duration">${duration(v.duration)}</span></div><div><h3 class="video-title">${esc(v.title)}</h3><div class="video-meta">${esc(v.owner.username)}<br>${Number(v.views).toLocaleString('ru-RU')} просмотров</div></div></article>`;}
function empty(text){return `<div class="empty-state">${esc(text)}</div>`;}
function updateTopbar(){const actions=document.getElementById('top-actions');const mod=document.getElementById('moderation-link');const my=document.getElementById('my-channel-link');if(currentUser){actions.innerHTML=`<span class="user-pill">${avatar(currentUser.username,true)}<b>${esc(currentUser.username)}</b></span><button class="btn btn-outline" id="logout-btn">Выйти</button>`;my.href=`/channel/${encodeURIComponent(currentUser.username)}`;my.dataset.link='';}else{actions.innerHTML='<a class="btn btn-outline" href="/login" data-link>Войти</a>';my.href='/login';my.dataset.link='';}mod.hidden=!(currentUser&&['moderator','admin'].includes(currentUser.role));}
async function loadUser(){try{currentUser=await api('/api/auth/me');}catch{currentUser=null;}updateTopbar();}
function navigate(path){history.pushState({},'',path);render();document.getElementById('sidebar').classList.remove('open');document.getElementById('menu-toggle').setAttribute('aria-expanded','false');window.scrollTo(0,0);}
function syncNavigation(){
  const path=location.pathname;
  const params=new URLSearchParams(location.search);
  let active=path.split('/').filter(Boolean)[0]||'home';
  if(path==='/'&&params.get('sort')==='popular')active='trending';
  if(path==='/'&&params.get('sort')!=='popular')active='home';
  if(path.startsWith('/channel/')&&currentUser&&decodeURIComponent(path.split('/')[2]||'')===currentUser.username)active='my-channel';
  if(path.startsWith('/playlist/'))active='playlists';
  document.querySelectorAll('.nav-item[data-nav]').forEach(link=>{
    const selected=link.dataset.nav===active;
    link.classList.toggle('active',selected);
    if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  });
}
function attachCommon(){
  syncNavigation();
  if(commonHandlersAttached)return;
  commonHandlersAttached=true;
  document.addEventListener('click',async event=>{
    const link=event.target.closest('a[data-link]');
    if(link){if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();event.stopPropagation();navigate(link.getAttribute('href'));return;}
    const saveButton=event.target.closest('[data-save-video]');
    if(saveButton){event.preventDefault();event.stopPropagation();const id=Number(saveButton.dataset.saveVideo);const saved=hasLocalEntry(STORAGE_KEYS.watchLater,id);if(saved){removeLocalEntry(STORAGE_KEYS.watchLater,id);toast('Видео удалено из списка «Смотреть позже»');}else{rememberLocalEntry(STORAGE_KEYS.watchLater,id);toast('Видео сохранено на потом');}const nextSaved=!saved;saveButton.classList.toggle('is-saved',nextSaved);saveButton.innerHTML=icon(nextSaved?'check':'bookmark');saveButton.title=nextSaved?'Сохранено':'Смотреть позже';saveButton.setAttribute('aria-label',nextSaved?'Убрать из списка «Смотреть позже»':'Сохранить на потом');return;}
    const downloadButton=event.target.closest('[data-download-video]');
    if(downloadButton){event.preventDefault();event.stopPropagation();startVideoDownload(Number(downloadButton.dataset.downloadVideo));return;}
    if(event.target.closest('#logout-btn')){try{await api('/api/auth/logout',{method:'POST'});currentUser=null;updateTopbar();toast('Вы вышли из аккаунта');navigate('/');}catch(error){toast(error.message);}return;}
    const video=event.target.closest('[data-open-video]');
    if(video){navigate(`/watch/${video.dataset.openVideo}`);}
  });
}
function startVideoDownload(id){
  const anchor=document.createElement('a');
  anchor.href=`/api/videos/${id}/download`;
  anchor.download=`streamhub-video-${id}.mp4`;
  anchor.rel='noopener';
  document.body.appendChild(anchor);anchor.click();anchor.remove();
  rememberLocalEntry(STORAGE_KEYS.downloads,id);
  toast('Загрузка файла началась');
}
async function requireAccount(){
  if(currentUser)return true;
  app.innerHTML=`<div class="library-empty"><div class="library-empty-icon">${icon('bookmark')}</div><h1>Войдите в StreamHub</h1><p>Этот раздел связан с вашим аккаунтом. Войдите, чтобы увидеть свои видео и плейлисты.</p><a class="btn btn-primary" href="/login" data-link>Войти</a><a class="text-link" href="/register" data-link>Создать аккаунт</a></div>`;
  return false;
}
async function renderHome(){
  const params=new URLSearchParams(location.search);
  const sort=params.get('sort')==='popular'?'popular':'recent';
  const category=params.get('category')||'all';
  const categories=[['all','Все'],['science','Научпоп'],['nature','Природа'],['technology','Технологии'],['history','История'],['education','Образование'],['travel','Путешествия'],['gaming','Игры']];
  const categoryQuery={science:'научпоп',nature:'природа',technology:'технологии',history:'история',education:'образование',travel:'путешествия',gaming:'игры'};
  app.innerHTML=`<div class="home-toolbar"><div class="category-strip" role="group" aria-label="Категории">${categories.map(([key,label])=>`<button class="chip category-chip ${category===key?'active':''}" data-category="${key}">${label}</button>`).join('')}</div><div class="tabs home-sort"><button class="chip ${sort==='recent'?'active':''}" id="recent-sort">Недавние</button><button class="chip ${sort==='popular'?'active':''}" id="popular-sort">Популярные</button></div></div><div class="section-head"><h1>${category==='all'?(sort==='popular'?'Популярные видео':'Рекомендации'):(categories.find(x=>x[0]===category)?.[1]||'Видео')}</h1><span class="video-meta">${sort==='popular'?'Сейчас смотрят':'Последние публикации'}</span></div><div id="home-videos" class="video-grid"><div class="loading">Загружаем видео…</div></div>`;
  const result=category==='all'?await api(`/api/videos?sort=${sort}&limit=48`):await api(`/api/search?q=${encodeURIComponent(categoryQuery[category]||category)}&limit=48`);
  const videos=result.items||[];
  const host=document.getElementById('home-videos');
  if(host)host.innerHTML=videos.length?videos.map(videoCard).join(''):empty(category==='all'?'Пока нет опубликованных видео. Загрузите первое!':'В этой категории пока нет видео. Попробуйте другую подборку или загрузите своё.');
  document.getElementById('recent-sort').onclick=()=>navigate(category==='all'?'/':`/?category=${category}`);
  document.getElementById('popular-sort').onclick=()=>navigate(`/?sort=popular${category==='all'?'':`&category=${category}`}`);
  document.querySelectorAll('[data-category]').forEach(button=>button.onclick=()=>navigate(button.dataset.category==='all'?`/?sort=${sort}`:`/?sort=${sort}&category=${button.dataset.category}`));
}
async function renderSearch(){const q=new URLSearchParams(location.search).get('q')||'';app.innerHTML=`<div class="section-head"><h1>Результаты поиска: ${esc(q)}</h1></div><div id="search-results" class="video-grid">Загрузка…</div>`;const result=await api(`/api/search?q=${encodeURIComponent(q)}`);document.getElementById('search-results').innerHTML=result.items.length?result.items.map(videoCard).join(''):empty('Ничего не найдено. Попробуйте изменить запрос.');}
async function renderWatch(id){app.innerHTML='<div class="loading">Загружаем видео…</div>';const v=await api(`/api/videos/${id}`);if(v.status!=='ready'){const failed=v.status==='failed';app.innerHTML=`<div class="form-card"><h1>${failed?'Не удалось обработать видео':'Видео обрабатывается'}</h1><p class="form-subtitle">${failed?'Обработка завершилась с ошибкой. Проверьте логи сервера или обратитесь к администратору.':'Файл принят и находится в очереди. Страница автоматически обновится, когда ролик будет готов.'}</p><div class="progress"><span style="width:${failed?'100%':'55%'}"></span></div><a class="btn btn-outline" href="/" data-link>На главную</a></div>`;if(!failed)setTimeout(()=>{if(location.pathname===`/watch/${id}`)renderWatch(id);},3000);return;}rememberLocalEntry(STORAGE_KEYS.history,id);const [comments,suggestions]=await Promise.all([api(`/api/videos/${id}/comments`),api('/api/videos?sort=popular&limit=8')]);const related=suggestions.items.filter(x=>x.id!==v.id).slice(0,7);app.innerHTML=`<div class="watch-layout"><section><div class="player"><video controls playsinline preload="metadata" poster="${v.thumbnail_url||''}" src="${v.stream_url||''}"></video></div><h1 class="watch-title">${esc(v.title)}</h1><div class="watch-toolbar"><div class="channel-row">${avatar(v.owner.username)}<div><a class="channel-name" href="/channel/${encodeURIComponent(v.owner.username)}" data-link>${esc(v.owner.username)}</a><div class="channel-subcount">${Number(v.views).toLocaleString('ru-RU')} просмотров</div></div>${currentUser&&currentUser.id!==v.owner.id?`<button class="btn btn-subscribe" id="subscribe-btn">${v.is_subscribed?'Вы подписаны':'Подписаться'}</button>`:''}</div><div class="watch-actions"><button class="btn" id="like-btn">${v.is_liked?'♥':'♡'} ${Number(v.like_count).toLocaleString('ru-RU')}</button><button class="btn" id="share-btn">↗ Поделиться</button><button class="btn" id="watch-later-btn">${hasLocalEntry(STORAGE_KEYS.watchLater,id)?"✓ Сохранено":"◷ Смотреть позже"}</button><button class="btn" id="download-current-btn">↓ Скачать</button>${currentUser&&currentUser.id!==v.owner.id?'<button class="btn" id="report-btn">⚑ Пожаловаться</button>':''}</div></div><div class="description-box">${esc(v.description||'Описание отсутствует')}<div class="video-meta" style="margin-top:9px">Опубликовано ${new Date(v.created_at).toLocaleDateString('ru-RU')}</div></div>${currentUser&&currentUser.id===v.owner.id&&v.visibility==='private'?`<div class="description-box"><b>Приватное видео</b><p class="video-meta">Видео доступно только вам и пользователям, которым вы выдали разрешение.</p><form id="grant-form" class="comment-form"><input type="email" name="email" placeholder="Email пользователя" required><button class="btn btn-primary">Выдать доступ</button></form><div id="grant-list" class="video-meta"></div></div>`:''}<section class="comments"><h2>${comments.length} комментариев</h2>${currentUser?`<form class="comment-form" id="comment-form">${avatar(currentUser.username,true)}<input name="body" maxlength="2000" placeholder="Оставьте комментарий…" required><button class="btn btn-primary">Отправить</button></form>`:'<p class="video-meta"><a href="/login" data-link>Войдите</a>, чтобы оставить комментарий.</p>'}<div id="comments-list">${comments.map(commentHtml).join('')||empty('Комментариев пока нет.')}</div></section></section><aside class="side-videos">${related.map(miniCard).join('')}</aside></div>`;
  document.getElementById('like-btn').onclick=async()=>{if(!currentUser)return navigate('/login');const r=await api(`/api/videos/${id}/like`,{method:'POST'});document.getElementById('like-btn').textContent=`${r.liked?'♥':'♡'} ${r.like_count}`;};
  const sub=document.getElementById('subscribe-btn');if(sub)sub.onclick=async()=>{const r=await api(`/api/channels/${encodeURIComponent(v.owner.username)}/subscribe`,{method:'POST'});sub.textContent=r.subscribed?'Вы подписаны':'Подписаться';};
  document.getElementById('share-btn').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);toast('Ссылка скопирована');}catch{toast(location.href);}};
  document.getElementById('watch-later-btn').onclick=()=>{const button=document.getElementById('watch-later-btn');if(hasLocalEntry(STORAGE_KEYS.watchLater,id)){removeLocalEntry(STORAGE_KEYS.watchLater,id);button.textContent='◷ Смотреть позже';toast('Видео удалено из списка');}else{rememberLocalEntry(STORAGE_KEYS.watchLater,id);button.textContent='✓ Сохранено';toast('Видео сохранено на потом');}};
  document.getElementById('download-current-btn').onclick=()=>startVideoDownload(Number(id));
  const report=document.getElementById('report-btn');if(report)report.onclick=async()=>{const reason=prompt('Причина жалобы: spam, misleading, copyright, violence, hate, sexual или other','other');if(!reason)return;try{await api(`/api/videos/${id}/report`,{method:'POST',body:{reason,details:''}});toast('Жалоба отправлена');}catch(e){toast(e.message);}};
  const cf=document.getElementById('comment-form');if(cf)cf.onsubmit=async e=>{e.preventDefault();try{const r=await api(`/api/videos/${id}/comments`,{method:'POST',body:{body:new FormData(cf).get('body')}});document.getElementById('comments-list').insertAdjacentHTML('beforeend',commentHtml(r));cf.reset();}catch(err){toast(err.message);}};
  const gf=document.getElementById('grant-form');if(gf){gf.onsubmit=async e=>{e.preventDefault();try{const r=await api(`/api/videos/${id}/access`,{method:'POST',body:{email:new FormData(gf).get('email')}});toast(r.message);gf.reset();await loadGrantList(id);}catch(err){toast(err.message);}};await loadGrantList(id);}
}
function commentHtml(c){return `<div class="comment">${avatar(c.user.username,true)}<div class="comment-body"><div class="comment-author">${esc(c.user.username)} <span class="comment-time">${new Date(c.created_at).toLocaleString('ru-RU')}</span></div><div class="comment-text">${esc(c.body)}</div></div></div>`;}
async function loadGrantList(id){const items=await api(`/api/videos/${id}/access`);const el=document.getElementById('grant-list');if(el)el.innerHTML=items.length?'Доступ есть у: '+items.map(x=>esc(x.email)).join(', '):'Доступ ещё никому не выдан.';}
async function renderChannel(username){app.innerHTML='<div class="loading">Загружаем канал…</div>';const data=await api(`/api/channels/${encodeURIComponent(username)}`);const c=data.channel;app.innerHTML=`<div class="channel-banner"></div><div class="channel-header">${avatar(c.username)}<div style="flex:1"><h1>${esc(c.username)}</h1><div class="video-meta">${Number(c.subscriber_count).toLocaleString('ru-RU')} подписчиков · ${c.video_count} видео</div><div class="video-meta">${esc(c.bio||'')}</div></div>${currentUser&&currentUser.id!==c.id?`<button class="btn btn-subscribe" id="channel-subscribe">${c.is_subscribed?'Вы подписаны':'Подписаться'}</button>`:''}</div><div class="channel-tabs"><span>Видео</span><span>Плейлисты</span></div><div class="section-head"><h2>Видео</h2></div><div class="video-grid">${data.videos.length?data.videos.map(videoCard).join(''):empty('На этом канале пока нет видео.')}</div><div class="section-head" style="margin-top:38px"><h2>Плейлисты</h2></div><div class="playlist-list">${data.playlists.map(p=>`<a class="playlist-card" href="/playlist/${p.id}" data-link><b>${esc(p.title)}</b><p class="video-meta">${p.video_count} видео</p></a>`).join('')||'<span class="video-meta">Плейлистов пока нет.</span>'}</div>`;const sb=document.getElementById('channel-subscribe');if(sb)sb.onclick=async()=>{const r=await api(`/api/channels/${encodeURIComponent(username)}/subscribe`,{method:'POST'});sb.textContent=r.subscribed?'Вы подписаны':'Подписаться';};}
async function renderPlaylist(id){const p=await api(`/api/playlists/${id}`);app.innerHTML=`<div class="section-head"><div><h1>${esc(p.title)}</h1><p class="video-meta">Плейлист · ${esc(p.owner)} · ${p.videos.length} видео</p></div></div><div class="video-grid">${p.videos.map(videoCard).join('')||empty('В плейлисте пока нет доступных видео.')}</div>`;}
async function renderLocalCollection(title, key, emptyText, options={}){
  app.innerHTML=`<div class="section-head"><div><h1>${esc(title)}</h1><p class="video-meta">${options.description||'Список доступен в этом браузере'}</p></div></div><div id="library-videos" class="video-grid"><div class="loading">Загружаем видео…</div></div>`;
  const videos=await videosFromLocalList(key);
  const host=document.getElementById('library-videos');
  if(host)host.innerHTML=videos.length?videos.map(video=>videoCard(video,{downloadAction:options.downloadAction})).join(''):empty(emptyText);
}
async function renderHistory(){await renderLocalCollection('История просмотров',STORAGE_KEYS.history,'Здесь появятся видео, которые вы открывали.');}
async function renderWatchLater(){await renderLocalCollection('Смотреть позже',STORAGE_KEYS.watchLater,'Список пока пуст. Нажмите на значок закладки на карточке видео, чтобы сохранить его.');}
async function renderDownloads(){await renderLocalCollection('Загрузки',STORAGE_KEYS.downloads,'Вы ещё не запускали загрузку видео. На странице просмотра нажмите «Скачать».',{description:'Видео, загрузку которых вы запускали в этом браузере',downloadAction:true});}
async function renderLiked(){
  if(!await requireAccount())return;
  app.innerHTML=`<div class="section-head"><h1>Понравившиеся</h1></div><div id="library-videos" class="video-grid"><div class="loading">Загружаем видео…</div></div>`;
  const result=await api('/api/me/liked');
  const host=document.getElementById('library-videos');if(host)host.innerHTML=result.items.length?result.items.map(videoCard).join(''):empty('Вы пока не отметили ни одного видео.');
}
async function renderYourVideos(){
  if(!await requireAccount())return;
  app.innerHTML=`<div class="section-head"><div><h1>Ваши видео</h1><p class="video-meta">Опубликованные ролики вашего канала</p></div><a class="btn btn-red" href="/upload" data-link>＋ Загрузить видео</a></div><div id="library-videos" class="video-grid"><div class="loading">Загружаем видео…</div></div>`;
  const result=await api('/api/me/videos');
  const host=document.getElementById('library-videos');if(host)host.innerHTML=result.items.length?result.items.map(videoCard).join(''):empty('Вы ещё не опубликовали видео.');
}
async function renderSubscriptions(){
  if(!await requireAccount())return;
  app.innerHTML=`<div class="section-head"><div><h1>Подписки</h1><p class="video-meta">Новые видео с каналов, на которые вы подписаны</p></div></div><div id="library-videos" class="video-grid"><div class="loading">Загружаем видео…</div></div>`;
  const result=await api('/api/subscriptions/feed');
  const host=document.getElementById('library-videos');if(host)host.innerHTML=result.items.length?result.items.map(videoCard).join(''):empty('Здесь появятся новые видео авторов, на которых вы подпишетесь.');
}
async function renderPlaylists(){
  if(!await requireAccount())return;
  app.innerHTML=`<div class="section-head"><div><h1>Плейлисты</h1><p class="video-meta">Ваши подборки видео</p></div></div><form id="playlist-create-form" class="playlist-create"><div class="field"><label for="playlist-title">Название плейлиста</label><input id="playlist-title" name="title" maxlength="120" placeholder="Например, Посмотреть позже" required></div><div class="field"><label for="playlist-description">Описание</label><input id="playlist-description" name="description" maxlength="1000" placeholder="Коротко о подборке"></div><div class="field"><label for="playlist-visibility">Доступ</label><select id="playlist-visibility" name="visibility"><option value="public">Открытый</option><option value="private">Приватный</option></select></div><button class="btn btn-primary" type="submit">Создать плейлист</button></form><div id="playlists-list" class="playlist-list library-playlists"><div class="loading">Загружаем плейлисты…</div></div>`;
  const form=document.getElementById('playlist-create-form');
  form.onsubmit=async event=>{event.preventDefault();const data=new FormData(form);try{await api('/api/playlists',{method:'POST',body:{title:data.get('title'),description:data.get('description')||'',visibility:data.get('visibility')}});toast('Плейлист создан');await loadPlaylists();form.reset();}catch(error){toast(error.message);}};
  await loadPlaylists();
}
async function loadPlaylists(){
  const result=await api('/api/me/playlists');
  const host=document.getElementById('playlists-list');if(!host)return;
  host.innerHTML=result.items.length?result.items.map(item=>`<a class="playlist-card" href="/playlist/${item.id}" data-link><div class="playlist-cover">${icon('bookmark')}</div><b>${esc(item.title)}</b><p class="video-meta">${item.video_count} видео · ${item.visibility==='private'?'Приватный':'Открытый'}</p></a>`).join(''):empty('У вас пока нет плейлистов. Создайте первую подборку выше.');
}
function authForm(mode){const register=mode==='register';app.innerHTML=`<div class="form-card"><h1>${register?'Создать аккаунт':'Вход в StreamHub'}</h1><p class="form-subtitle">${register?'Присоединяйтесь к сообществу авторов и зрителей.':'Войдите, чтобы ставить лайки, комментировать и загружать видео.'}</p><form id="auth-form">${register?`<div class="field"><label>Имя канала</label><input name="username" minlength="3" maxlength="40" pattern="[A-Za-z0-9_.-]+" placeholder="my_channel" required></div>`:''}<div class="field"><label>Email</label><input type="email" name="email" autocomplete="email" required></div><div class="field"><label>Пароль</label><input type="password" name="password" minlength="8" autocomplete="${register?'new-password':'current-password'}" required></div><div id="auth-error"></div><div class="form-footer"><span class="video-meta">${register?'Уже есть аккаунт?':'Нет аккаунта?'} <a href="/${register?'login':'register'}" data-link>${register?'Войти':'Регистрация'}</a></span><button class="btn btn-primary">${register?'Зарегистрироваться':'Войти'}</button></div></form></div>`;document.getElementById('auth-form').onsubmit=async e=>{e.preventDefault();const form=new FormData(e.currentTarget);const body={email:form.get('email'),password:form.get('password')};if(register)body.username=form.get('username');try{await api(`/api/auth/${register?'register':'login'}`,{method:'POST',body});await loadUser();toast(register?'Аккаунт создан':'Вы вошли');navigate('/');}catch(err){document.getElementById('auth-error').innerHTML=`<div class="notice error">${esc(err.message)}</div>`;}};}
function renderUpload(){if(!currentUser){navigate('/login');return;}app.innerHTML=`<div class="form-card"><h1>Загрузка видео</h1><p class="form-subtitle">Выберите видео, добавьте название и описание. После загрузки файл будет обработан в фоне.</p><form id="upload-form"><div class="field"><label>Файл видео</label><input type="file" name="file" accept=".mp4,.mov,.mkv,.webm,video/*" required><div class="field-help">Форматы: MP4, MOV, MKV, WEBM. Ограничение размера задаётся сервером.</div></div><div class="field"><label>Название</label><input name="title" maxlength="120" placeholder="Название видео" required></div><div class="field"><label>Описание</label><textarea name="description" maxlength="10000" placeholder="Расскажите о видео"></textarea></div><div class="field"><label>Доступ</label><select name="visibility"><option value="public">Открытое — видно всем</option><option value="private">Приватное — только мне и выбранным пользователям</option></select></div><div id="upload-progress" class="hidden"><div class="progress"><span id="progress-value"></span></div><div id="progress-label" class="video-meta">0%</div></div><div id="upload-message"></div><div class="form-footer"><span class="video-meta">Максимум 2 ГБ по умолчанию</span><button class="btn btn-red" id="upload-submit">Загрузить</button></div></form></div>`;document.getElementById('upload-form').onsubmit=e=>{e.preventDefault();const form=e.currentTarget;const data=new FormData(form);const xhr=new XMLHttpRequest();const progress=document.getElementById('upload-progress');const bar=document.getElementById('progress-value');const label=document.getElementById('progress-label');const msg=document.getElementById('upload-message');const btn=document.getElementById('upload-submit');progress.classList.remove('hidden');btn.disabled=true;xhr.open('POST','/api/videos/upload');xhr.withCredentials=true;xhr.upload.onprogress=event=>{if(event.lengthComputable){const n=Math.round(event.loaded/event.total*100);bar.style.width=n+'%';label.textContent=`Загрузка: ${n}%`;}};xhr.onload=()=>{btn.disabled=false;let result={};try{result=JSON.parse(xhr.responseText);}catch{}if(xhr.status>=200&&xhr.status<300){msg.innerHTML='<div class="notice">Файл принят. Обработка началась. Видео появится на канале после завершения.</div>';label.textContent='Загрузка завершена';toast('Видео отправлено на обработку');setTimeout(()=>navigate(`/watch/${result.video.id}`),1200);}else{msg.innerHTML=`<div class="notice error">${esc(result.detail||'Ошибка загрузки')}</div>`;}};xhr.onerror=()=>{btn.disabled=false;msg.innerHTML='<div class="notice error">Ошибка соединения при загрузке.</div>';};xhr.send(data);};}
async function renderModeration(){if(!currentUser||!['moderator','admin'].includes(currentUser.role)){app.innerHTML=empty('Доступ к модерации запрещён.');return;}const items=await api('/api/moderation/reports');app.innerHTML=`<div class="section-head"><h1>Модерация · Жалобы</h1><span class="video-meta">${items.filter(x=>x.status==='open').length} открытых</span></div><div class="report-list">${items.length?items.map(r=>`<article class="report-card"><h3>${esc(r.video_title)}</h3><div class="video-meta">Жалоба #${r.id} · ${esc(r.reason)} · от ${esc(r.reporter)} · ${new Date(r.created_at).toLocaleString('ru-RU')}</div><p>${esc(r.details||'Без дополнительных сведений')}</p><div class="report-actions"><a class="btn btn-outline" href="/watch/${r.video_id}" data-link>Открыть видео</a>${r.status==='open'?`<button class="btn btn-primary" data-resolve="${r.id}" data-hide="false">Закрыть</button><button class="btn btn-red" data-resolve="${r.id}" data-hide="true">Скрыть видео и закрыть</button>`:`<span class="video-meta">Статус: ${esc(r.status)}</span>`}</div></article>`).join(''):empty('Жалоб пока нет.')}</div>`;document.querySelectorAll('[data-resolve]').forEach(btn=>btn.onclick=async()=>{try{await api(`/api/moderation/reports/${btn.dataset.resolve}`,{method:'PATCH',body:{status:'resolved',hide_video:btn.dataset.hide==='true'}});toast('Жалоба обработана');renderModeration();}catch(e){toast(e.message);}});}
async function render(){try{const path=location.pathname;const parts=path.split('/').filter(Boolean);if(path==='/'||path===''){await renderHome();}else if(parts[0]==='watch'&&parts[1]){await renderWatch(parts[1]);}else if(parts[0]==='channel'&&parts[1]){await renderChannel(decodeURIComponent(parts[1]));}else if(parts[0]==='search'){await renderSearch();}else if(parts[0]==='login'||parts[0]==='register'){authForm(parts[0]);}else if(path==='/upload'){renderUpload();}else if(path==='/studio/moderation'){await renderModeration();}else if(parts[0]==='playlist'&&parts[1]){await renderPlaylist(parts[1]);}else if(path==='/history'){await renderHistory();}else if(path==='/watch-later'){await renderWatchLater();}else if(path==='/downloads'){await renderDownloads();}else if(path==='/liked'){await renderLiked();}else if(path==='/your-videos'){await renderYourVideos();}else if(path==='/playlists'){await renderPlaylists();}else if(path==='/subscriptions'){await renderSubscriptions();}else{app.innerHTML=empty('Страница не найдена.');}}catch(error){app.innerHTML=`<div class="empty-state"><h2>Не удалось загрузить страницу</h2><p>${esc(error.message)}</p><a class="btn btn-outline" href="/" data-link>На главную</a></div>`;}attachCommon();}

document.getElementById('search-form').addEventListener('submit',e=>{e.preventDefault();const q=document.getElementById('search-input').value.trim();if(q)navigate(`/search?q=${encodeURIComponent(q)}`);});
document.getElementById('menu-toggle').addEventListener('click',()=>{const sidebar=document.getElementById('sidebar');const open=sidebar.classList.toggle('open');document.getElementById('menu-toggle').setAttribute('aria-expanded',String(open));});
window.addEventListener('popstate',render);
(async()=>{await loadUser();const q=new URLSearchParams(location.search).get('q');if(q)document.getElementById('search-input').value=q;await render();})();
