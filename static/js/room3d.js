// ② 회의실 3D — 회의록 한 편의 처리를 재생한다. HITL 을 눈으로: 카드가 업무 보드(자동)로 가나, 승인함(멈춤)으로 가나.
// 원탁에 도윤 · 지수 · 민호 · 영숙(사람), AI 비서(에이전트 · 로봇)가 할 일 카드를 들고 떠서 옮긴다.
// 사람도 움직인다 (09-29 작성자 「로봇만 움직이잖아」):
//   자동 등록 → 담당자가 일어나 손을 든다 (알림을 받음 = 바깥으로 나감)
//   멈춤     → 도윤(대표 · 승인자)이 승인함 쪽으로 고개를 돌린다 (사람이 볼 건)
//   재생 끝  → 도윤이 승인함으로 걸어가, 반려한 카드는 흐리게 하고 승인한 카드를 들고 업무 보드로 옮긴다 (사람의 답 → 이어서 실행)
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { 인물, 사람만들기, 로봇만들기, 자세잡기 } from './people.js';

let 장면, 카메라, 그리기, 글씨그리기, 조종, 시계, 모니터, 자막;
let 사람들 = {}, 비서, 카드들 = [], 할일목록 = [], 사건 = [], 속도 = 1, 멈춤 = true, 시각 = 0;
const 보드자리 = new THREE.Vector3(-3.6, 0, 0.2), 승인함자리 = new THREE.Vector3(3.2, 0, 0.2);
const 비서자리 = new THREE.Vector3(0, 0, 2.1);
const 문자리 = new THREE.Vector3(4.2, 0, -3.0);
// 문에서 자리까지 — 원탁 · 승인함 책상 · 다른 사람 의자를 돌아가는 경유점 (세계 좌표 · 마지막 '자리' = 자기 자리)
const 들어오는길 = {
  도윤: [new THREE.Vector3(2.6, 0, -2.9), new THREE.Vector3(0.8, 0, -2.7), '자리'],
  지수: [new THREE.Vector3(3.2, 0, -1.7), new THREE.Vector3(2.9, 0, -0.9), '자리'],
  민호: [new THREE.Vector3(2.6, 0, -2.9), new THREE.Vector3(-1.2, 0, -2.8), new THREE.Vector3(-2.7, 0, -1.4), '자리'],
  영숙: [new THREE.Vector3(2.6, 0, -2.9), new THREE.Vector3(-1.2, 0, -2.8), new THREE.Vector3(-2.9, 0, -0.9), new THREE.Vector3(-2.5, 0, 1.9), '자리'],
};
const 자리각 = { 도윤: Math.PI, 지수: Math.PI * 0.55, 민호: -Math.PI * 0.55, 영숙: Math.PI * 1.5 + 0.9 };

function 이름표(글, 색 = '#e8ecf1') {
  const d = document.createElement('div');
  d.style.cssText = `font:600 13px "Malgun Gothic",sans-serif;color:${색};background:rgba(16,19,24,.78);padding:2px 8px;border-radius:999px;white-space:nowrap`;
  d.textContent = 글;
  return new CSS2DObject(d);
}

// 사람 머리 위 말풍선 — 할 일의 근거 줄(그라운딩)을 보여 준다 · 한 번에 하나만 (09-29 작성자 「나」)
function 말풍선() {
  const d = document.createElement('div');
  d.style.cssText = 'font:600 13px "Malgun Gothic",sans-serif;color:#15181d;background:#f3f5f8;padding:5px 10px;border-radius:10px;' +
    'max-width:220px;white-space:normal;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.45)';
  const o = new CSS2DObject(d);
  o.visible = false;   // 숨길 때는 visible 로 — CSS2DRenderer 가 매 장면 style.display 를 visible 에 맞춰 덮어쓴다
  o.center.set(0.5, 1);   // 말풍선의 아래 끝을 기준점에 — 이름표 바로 위에 올라앉게 (이름표를 덮지 않음)
  return o;
}
function 말끄기() { for (const s of Object.values(사람들)) s.말.visible = false; }
function 말하기(이름, 줄) {
  말끄기();
  const s = 사람들[이름]; if (!s || !줄) return;
  const 말 = 줄.split(': ').slice(1).join(': ').trim();
  s.말.element.textContent = 말.length > 30 ? 말.slice(0, 30) + '…' : 말;
  s.말.visible = true;
}

// 말은 3D 공간이 아니라 화면 위쪽 자막으로 (이름표와 겹치지 않게)
function 자막만들기(그릇) {
  const d = document.createElement('div');
  d.style.cssText = 'position:absolute;bottom:14px;left:50%;transform:translateX(-50%);max-width:80%;font:600 15px "Malgun Gothic",sans-serif;' +
    'color:#111;background:rgba(255,255,255,.94);padding:7px 14px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.45);display:none;pointer-events:none;text-align:center';
  if (getComputedStyle(그릇).position === 'static') 그릇.style.position = 'relative';
  그릇.appendChild(d);
  return d;
}

function 모니터만들기() {
  // 09-29 작성자 「칠판을 크게 · 글자가 정확히 보이게」 — 3.6 × 1.4 → 5.2 × 2.0 · 캔버스 두 배
  const c = document.createElement('canvas'); c.width = 2080; c.height = 800;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 2.0), new THREE.MeshBasicMaterial({ map: t }));
  m.position.set(0, 2.45, -3.4);
  장면.add(m);
  const 테 = new THREE.Mesh(new THREE.BoxGeometry(5.36, 2.16, 0.06), new THREE.MeshStandardMaterial({ color: 0x0c0f13 }));
  테.position.set(0, 2.45, -3.44); 장면.add(테);
  return { c, t };
}

function 모니터쓰기(단계, 줄들) {
  const { c, t } = 모니터, g = c.getContext('2d');
  g.fillStyle = '#0f141b'; g.fillRect(0, 0, c.width, c.height);
  const 이름 = ['① 분류', '② 뽑기', '③ 정리 · 대조 · 검수', '④ 가드레일'];
  g.font = 'bold 80px "Malgun Gothic"';
  let 왼 = 50;
  이름.forEach((x, i) => { g.fillStyle = i === 단계 ? '#5fc0e6' : '#56606e'; g.fillText(x, 왼, 110); 왼 += g.measureText(x).width + 70; });   // 글자 폭을 재서 겹치지 않게
  g.fillStyle = '#ffffff'; g.font = 'bold 96px "Malgun Gothic"';
  // 줄이 길면 캔버스 폭에 맞춰 자른다 (글자 수가 아니라 실제 폭으로)
  const 폭 = c.width - 100, 자르기 = l => { if (g.measureText(l).width <= 폭) return l; while (l.length && g.measureText(l + '…').width > 폭) l = l.slice(0, -1); return l + '…'; };
  줄들.slice(0, 4).forEach((l, i) => g.fillText(자르기(l), 50, 270 + i * 140));
  t.needsUpdate = true;
}

function 탁자와방() {
  const 바닥 = new THREE.Mesh(new THREE.PlaneGeometry(14, 10), new THREE.MeshStandardMaterial({ color: 0x5a5f66, roughness: 0.95 }));
  바닥.rotation.x = -Math.PI / 2; 바닥.receiveShadow = true; 장면.add(바닥);
  const 벽 = new THREE.Mesh(new THREE.PlaneGeometry(14, 5), new THREE.MeshStandardMaterial({ color: 0x46505e }));
  벽.position.set(0, 2.5, -3.5); 장면.add(벽);
  const 원탁 = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 1.15, 0.06, 48), new THREE.MeshStandardMaterial({ color: 0x8a6a4a, roughness: 0.6 }));
  원탁.position.y = 0.74; 원탁.castShadow = 원탁.receiveShadow = true; 장면.add(원탁);
  const 다리 = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.3, 0.72, 20), new THREE.MeshStandardMaterial({ color: 0x3a2e24 }));
  다리.position.y = 0.36; 장면.add(다리);
  // 업무 보드 (왼쪽 벽 판) · 승인함 (오른쪽 책상)
  const 보드 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.0, 2.6), new THREE.MeshStandardMaterial({ color: 0x1f3a2e }));
  보드.position.set(보드자리.x - 0.5, 1.6, 보드자리.z); 장면.add(보드);
  보드표 = 이름표('업무 보드', '#8fe0b8'); 보드표.position.set(보드자리.x - 0.5, 2.8, 보드자리.z); 장면.add(보드표);
  const 책상 = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.06, 1.0), new THREE.MeshStandardMaterial({ color: 0x5a4a2a }));
  책상.position.set(승인함자리.x + 0.4, 0.78, 승인함자리.z); 책상.castShadow = true; 장면.add(책상);
  const 책상다리 = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.76, 0.9), new THREE.MeshStandardMaterial({ color: 0x2e2618 }));
  책상다리.position.set(승인함자리.x + 0.4, 0.38, 승인함자리.z); 장면.add(책상다리);
  함표 = 이름표('승인함', '#ffd08a');
  // 문 (뒷벽 오른쪽) — 재생을 시작하면 참석자가 여기로 들어와 자리에 앉는다
  const 문틀 = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.3, 0.08), new THREE.MeshStandardMaterial({ color: 0x2b2118 }));
  문틀.position.set(문자리.x, 1.15, -3.46); 장면.add(문틀);
  const 문짝 = new THREE.Mesh(new THREE.BoxGeometry(1.0, 2.15, 0.06), new THREE.MeshStandardMaterial({ color: 0x7a5a3a, roughness: 0.7 }));
  문짝.position.set(문자리.x, 1.08, -3.42); 장면.add(문짝);
  const 손잡이 = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), new THREE.MeshStandardMaterial({ color: 0xd8c27a, metalness: 0.6, roughness: 0.3 }));
  손잡이.position.set(문자리.x - 0.38, 1.05, -3.37); 장면.add(손잡이); 함표.position.set(승인함자리.x + 0.4, 1.35, 승인함자리.z); 장면.add(함표);
}

function 사람배치() {
  for (const [이름, 각] of Object.entries(자리각)) {
    const q = 사람만들기(인물[이름]);
    const 자리 = new THREE.Group();
    자리.position.set(Math.sin(각) * 1.9, 0, Math.cos(각) * 1.9);
    자리.lookAt(0, 0, 0);
    자리.add(q.사람);
    자리.add(q.의자);   // 의자는 자리에 남기고 사람만 걷는다 (자리 기준 위치는 그대로)
    const 표 = 이름표(이름); 표.position.set(0, 1.85, -0.3); q.사람.add(표);   // 이름만 (직함은 무대 위 설명 줄에 · 09-29 작성자) · 사람을 따라감
    const 말 = 말풍선(); 말.position.set(0, 2.02, -0.3); q.사람.add(말);   // 할 일의 근거 줄을 말한 사람 머리 위 (한 번에 하나)
    장면.add(자리);
    사람들[이름] = { q, 자리, 말, 끄덕: 0, 앉음: 1, 목표앉음: 1, 뻗기: 0, 목표뻗기: 0, 손: 0, 목표손: 0, 걸음: 0, 이동: null, 고개: 0, 목표고개: 0, 든카드들: [] };
  }
  const q = 로봇만들기();
  const 무리 = new THREE.Group(); 무리.add(q.사람); 무리.position.copy(비서자리); 무리.lookAt(0, 0, 0);
  const 표 = 이름표('AI 비서', '#9fd8ee'); 표.position.set(0, 1.85, 0); 무리.add(표);
  장면.add(무리);
  비서 = { q, 무리, 든카드: null };
}

// ── 사람 움직이기 (자리 그룹 기준 좌표로 걷는다 · 자리 원점 = 의자 앞 앉는 곳) ──
function 사람자리로(s, 세계점) { return s.자리.worldToLocal(세계점.clone()); }
// 손 1 = 한 손만 위로 (두 팔을 앞으로 일자로 뻗는 모양은 무서워 보여 쓰지 않는다 · 09-29 작성자)
function 일어나기(s, 손 = 0) { s.목표앉음 = 0; s.목표손 = 손; s.목표뻗기 = 0; }
function 앉기(s) { s.목표앉음 = 1; s.목표뻗기 = 0; s.목표손 = 0; s.목표고개 = 0; s.q.사람.rotation.y = 0; }
function 손들기(s) { s.목표손 = 1; }   // 앉은 채로 손만 (알림을 받음 · 09-29 작성자 「일어나지 말고 손만」)
function 손내리기(s) { s.목표손 = 0; }
function 걸어가기(s, 세계점들, 속력 = 1.3) {   // 경유점(세계 좌표)을 차례로 · 마지막 점이 자리 원점이면 자리로 돌아옴
  const 점들 = [s.q.사람.position.clone(), ...세계점들.map(p => p === '자리' ? new THREE.Vector3() : 사람자리로(s, p))];
  let 길이 = 0; for (let i = 1; i < 점들.length; i++) 길이 += 점들[i].distanceTo(점들[i - 1]);
  s.이동 = { 점들, 길이, 지난: 0, 속력 };
}
function 고개돌리기(s, 세계점) {
  const 쪽 = 사람자리로(s, 세계점);
  s.목표고개 = THREE.MathUtils.clamp(Math.atan2(쪽.x, 쪽.z), -1.1, 1.1);
}
function 손위치(s) { const p = new THREE.Vector3(); s.q.팔[1].손.getWorldPosition(p); return p; }
function 사람들처음으로() {
  for (const s of Object.values(사람들)) {
    s.q.사람.position.set(0, 0, 0); s.q.사람.visible = true; 앉기(s); s.앉음 = 1; s.이동 = null; s.든카드들 = []; s.끄덕 = 0; s.말.visible = false;
  }
}

function 카드만들기(t) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.02, 0.24), new THREE.MeshStandardMaterial({ color: 0xf4f1ea, roughness: 0.7 }));
  m.castShadow = true;
  m.position.set((Math.random() - 0.5) * 0.6, 0.78, (Math.random() - 0.5) * 0.6);
  m.userData = t;
  const 표 = 이름표(t.내용.length > 14 ? t.내용.slice(0, 14) + '…' : t.내용, '#cfd6de');
  표.position.set(0, 0.12, 0); 표.element.style.fontSize = '11px'; 표.visible = false; m.add(표);
  m.userData.표 = 표;
  장면.add(m);
  return m;
}

let 보드표, 함표;
function 장수쓰기() {
  const 셈 = 곳 => 할일목록.filter(x => x.지금곳 === 곳).length;
  보드표.element.textContent = `업무 보드 · ${셈('보드')}장`;
  함표.element.textContent = `승인함 · ${셈('승인함')}장` + (셈('반려') ? ` · 반려 ${셈('반려')}` : '');
}

function 카드놓기(카드, 어디, 번호) {
  const 색 = { 보드: 0x4fb286, 승인함: 0xe0a13c, 반려: 0x555a60 }[어디];
  카드.material.color.setHex(색);
  카드.userData.표.visible = false;   // 놓은 카드는 이름표를 숨긴다 (겹쳐서 안 읽힘) — 들고 가는 동안만 보인다
  카드.userData.지금곳 = 어디;
  const 항목 = 할일목록.find(x => x.카드 === 카드); if (항목) 항목.지금곳 = 어디;
  if (어디 === '보드') {
    카드.rotation.set(0, Math.PI / 2, Math.PI / 2);
    카드.position.set(보드자리.x - 0.44, 2.35 - (번호 % 6) * 0.3, 보드자리.z - 1.0 + Math.floor(번호 / 6) * 0.42);
  } else {
    카드.rotation.set(0, 0, 0);
    카드.position.set(승인함자리.x + 0.1 + (번호 % 3) * 0.36, 0.82 + Math.floor(번호 / 9) * 0.03, 승인함자리.z - 0.3 + (Math.floor(번호 / 3) % 3) * 0.28);
    if (어디 === '반려') 카드.material.opacity = 0.35, 카드.material.transparent = true;
  }
  장수쓰기();
}

// 사건 목록: 시각(초)마다 할 일. 속도로 나눠 재생
function 사건만들기(d) {
  사건 = []; let t = 0.1;
  const 줄 = d.줄들;
  // 회의 시작 — 참석자가 문으로 들어와 차례로 자리에 앉는다 (09-29 작성자)
  사건.push({ t, 할: () => { 풍선('회의 시작 — 참석자가 들어옵니다'); 모니터쓰기(-1, [`${d.id} ${d.제목} · ${d.회의일}`]);
    for (const s of Object.values(사람들)) { s.q.사람.position.copy(사람자리로(s, 문자리)); s.q.사람.visible = false; s.앉음 = 0; s.목표앉음 = 0; } } });
  Object.keys(들어오는길).forEach((이름, k) => {
    const s = 사람들[이름]; if (!s) return;
    사건.push({ t: t + 0.3 + k * 1.2, 할: () => { s.q.사람.visible = true; s.목표앉음 = 1; 걸어가기(s, 들어오는길[이름], 2.0); } });
  });
  t += 10.5;
  사건.push({ t, 할: () => 풍선('') });
  사건.push({ t, 할: () => 모니터쓰기(0, 줄) });
  t += 2.0;
  사건.push({ t, 할: () => 모니터쓰기(1, d.진행.도구기록.map(x => `날짜 도구: 「${x.표현}」 → ${x.날짜 || '정할 수 없음'}`).concat(['할 일을 근거 줄로만 뽑는 중…'])) });
  t += 2.0;
  사건.push({ t, 할: () => 모니터쓰기(2, ['정리: 마감을 날짜 도구로 다시 계산해 맞춰 봄',
    '대조: 같은 일을 두 번 뽑았나', '검수: 담당자 · 마감 · 근거 · 확정된 할 일인가']) });
  t += 1.5;
  let 보드수 = 0, 함수 = 0;
  할일목록.forEach((x, i) => {
    const 가는곳 = x.걸린규칙.length ? '승인함' : '보드';
    const 번호 = 가는곳 === '보드' ? 보드수++ : 함수++;
    const 목표 = 가는곳 === '보드' ? 보드자리.clone().add(new THREE.Vector3(0.6, 0, 0)) : 승인함자리.clone().add(new THREE.Vector3(-0.6, 0, 0));
    const 말 = 가는곳 === '보드' ? `자동 등록 → ${x.담당자 || '?'}에게 알림` : `멈춤 · ${x.걸린규칙.join(' ')} — 사람에게`;
    const 이름만 = String(x.내용).replace(/^\(할 일 후보 · 뽑기에서 빠짐\)\s*/, '후보 · ');
    사건.push({ t, 할: () => { 모니터쓰기(3, [`${i + 1}/${할일목록.length} ${이름만}`, `담당 ${x.담당자 || '없음'} · 마감 ${x.마감 || '없음'}`, x.걸린규칙.length ? `걸린 규칙: ${x.걸린규칙.join(', ')}` : '걸린 규칙 없음']);
      끄덕이기(x); 말하기((x.근거줄 || '').split(':')[0], x.근거줄); 비서.든카드 = x.카드; x.카드.userData.표.visible = true; 풍선(말); } });
    사건.push({ t: t + 1.7, 할: () => 말끄기() });
    사건.push({ t: t + 0.3, 걷기: { 목표, 길이: 1.4 } });
    사건.push({ t: t + 1.8, 할: () => { 카드놓기(x.카드, 가는곳, 번호); x.놓인곳 = { 가는곳, 번호 }; 비서.든카드 = null; } });
    사건.push({ t: t + 1.9, 걷기: { 목표: 비서자리.clone(), 길이: 1.2 } });
    const 담당 = 사람들[x.담당자], 도윤 = 사람들['도윤'];
    if (가는곳 === '보드' && 담당) {   // 알림을 받은 담당자가 일어나 손을 든다
      사건.push({ t: t + 1.9, 할: () => { if (!담당.이동) 손들기(담당); 풍선(`자동 등록 → ${x.담당자}에게 알림이 나갔습니다`); } });
      사건.push({ t: t + 3.0, 할: () => 손내리기(담당) });
    } else if (가는곳 === '승인함' && 도윤) {   // 승인자가 승인함 쪽을 본다
      사건.push({ t: t + 1.9, 할: () => 고개돌리기(도윤, 승인함자리) });
      사건.push({ t: t + 3.1, 할: () => { 도윤.목표고개 = 0; } });
    }
    t += 3.3;
  });
  t = 사람처리사건(t);
  사건.push({ t, 할: () => { 지금상태맞추기(); 풍선('재생 끝 — 지금 상태입니다. 승인한 카드는 보드로, 반려한 카드는 흐리게.'); 모니터쓰기(3, 요약줄()); } });
  return t;
}

// 재생 끝: 사람(도윤)이 승인함을 처리하는 모습 — 지금 기록(승인 · 수정 후 승인 · 반려)대로
// 길은 원탁과 다른 사람 의자를 돌아간다 (세계 좌표)
const 길 = {
  승인함으로: [new THREE.Vector3(1.6, 0, -2.6), new THREE.Vector3(2.7, 0, -1.3), new THREE.Vector3(2.55, 0, 0.2)],
  보드로: [new THREE.Vector3(2.3, 0, 2.9), new THREE.Vector3(-2.3, 0, 2.9), new THREE.Vector3(-2.95, 0, 0.2)],
  자리로: [new THREE.Vector3(-2.85, 0, -1.6), new THREE.Vector3(-1.5, 0, -2.6), '자리'],
};
function 사람처리사건(t) {
  const 도윤 = 사람들['도윤'];
  const 승인 = 할일목록.filter(x => x.걸린규칙.length && /승인/.test(x.상태 || ''));
  const 반려 = 할일목록.filter(x => x.걸린규칙.length && x.상태 === '반려');
  if (!도윤 || (!승인.length && !반려.length)) return t;
  let 보드수 = 할일목록.filter(x => !x.걸린규칙.length).length;
  사건.push({ t, 할: () => { 풍선(`사람(도윤)이 승인함을 확인합니다 — 승인 ${승인.length}건 · 반려 ${반려.length}건`); 모니터쓰기(3, 요약줄()); 일어나기(도윤); } });
  사건.push({ t: t + 0.7, 할: () => 걸어가기(도윤, 길.승인함으로) });
  t += 0.7 + 4.2;
  사건.push({ t, 할: () => { 일어나기(도윤); 도윤.목표뻗기 = 0.25;   // 책상 위 카드를 집음 (두 팔을 살짝만)
    반려.forEach(x => 카드놓기(x.카드, '반려', x.놓인곳?.번호 ?? 0));
    도윤.든카드들 = 승인.map(x => x.카드); 승인.forEach(x => { x.카드.userData.표.visible = false; });
    풍선(승인.length ? `반려 ${반려.length}건은 등록하지 않고 · 승인한 ${승인.length}건을 업무 보드로` : `반려 ${반려.length}건은 등록하지 않습니다`); } });
  if (승인.length) {
    사건.push({ t: t + 0.8, 할: () => { 도윤.목표뻗기 = 0.2; 걸어가기(도윤, 길.보드로, 1.7); } });   // 카드를 안고 걸음 · 약 10m → 6초 안
    t += 0.8 + 6.3;
    사건.push({ t, 할: () => { 도윤.목표뻗기 = 0; 도윤.목표손 = 1; 승인.forEach(x => 카드놓기(x.카드, '보드', 보드수++)); 도윤.든카드들 = [];   // 한 손을 올려 붙임
      풍선(`승인한 ${승인.length}건 등록 → 담당자에게 알림`); } });
    승인.map(x => 사람들[x.담당자]).filter(Boolean).forEach(s => {
      if (s === 도윤) return;   // 도윤은 보드 앞에서 이미 손을 올려 붙이는 중
      사건.push({ t: t + 0.2, 할: () => 손들기(s) }); 사건.push({ t: t + 1.4, 할: () => 손내리기(s) }); });
  }
  사건.push({ t: t + 0.8, 할: () => { 도윤.목표뻗기 = 0; 도윤.목표손 = 0; 걸어가기(도윤,승인.length ? 길.자리로 : [...길.승인함으로].reverse().slice(1).concat('자리')); } });
  t += 0.8 + 5.2;
  사건.push({ t, 할: () => 앉기(도윤) });
  return t + 0.8;
}

function 요약줄() {
  const n = 할일목록.length, 자 = 할일목록.filter(x => !x.걸린규칙.length).length;
  const 세 = s => 할일목록.filter(x => x.상태 === s).length;
  return [`할 일 ${n}건 · 자동 등록 ${자} · 멈춤 ${n - 자}`, `지금: 대기 ${세('대기')} · 승인 ${세('승인 등록')} · 수정 후 승인 ${세('수정 후 승인 등록')} · 반려 ${세('반려')}`];
}

function 지금상태맞추기() {
  let 보드수 = 할일목록.filter(x => !x.걸린규칙.length).length;
  할일목록.forEach(x => {
    if (!x.놓인곳) { const 가는곳 = x.걸린규칙.length ? '승인함' : '보드'; x.놓인곳 = { 가는곳, 번호: 0 }; }
    if (x.걸린규칙.length && /승인/.test(x.상태)) 카드놓기(x.카드, '보드', 보드수++);
    else if (x.상태 === '반려') 카드놓기(x.카드, '반려', x.놓인곳.번호);
    else if (!x.걸린규칙.length || x.상태 === '대기') 카드놓기(x.카드, x.놓인곳.가는곳, x.놓인곳.번호);
  });
}

function 끄덕이기(x) {
  const 말한 = (x.근거줄 || '').split(':')[0];
  if (사람들[말한]) 사람들[말한].끄덕 = 1.2;
}

function 풍선(말) { if (!자막) return; 자막.textContent = 말; 자막.style.display = 말 ? 'block' : 'none'; }

let 걷는중 = null;
function 한틀(dt) {
  if (!멈춤) {
    const 전 = 시각; 시각 += dt * 속도;
    사건.filter(e => e.t > 전 && e.t <= 시각).forEach(e => {
      if (e.할) e.할();
      if (e.걷기) 걷는중 = { 시작: 비서.무리.position.clone(), ...e.걷기, 지난: 0 };
    });
  }
  if (걷는중) {
    걷는중.지난 += dt * 속도;
    const k = Math.min(걷는중.지난 / 걷는중.길이, 1);
    비서.무리.position.lerpVectors(걷는중.시작, 걷는중.목표, k);
    const 앞 = 걷는중.목표.clone(); 앞.y = 0;
    if (k < 1) 비서.무리.lookAt(앞);
    비서.q.사람.position.y = k < 1 ? 0.04 + Math.sin(걷는중.지난 * 10) * 0.02 : 0;   // 떠서 미끄러지듯
    if (k >= 1) { 걷는중 = null; 비서.무리.lookAt(0, 0, 0); }
  }
  if (비서.든카드) {
    const 손 = new THREE.Vector3(0, 0.9, 0.52).applyMatrix4(비서.무리.matrixWorld);
    비서.든카드.position.copy(손);
    비서.든카드.rotation.set(0, 비서.무리.rotation.y, 0);
  }
  비서.q.빛.emissiveIntensity = 비서.든카드 ? 0.6 + Math.sin(performance.now() / 120) * 0.4 : 0.6;   // 일할 때 눈 · 가슴빛이 깜빡임
  const 지금 = performance.now() / 1000;
  const 다가가기 = (a, b, 빠르기) => a + (b - a) * Math.min(1, dt * 빠르기);
  for (const s of Object.values(사람들)) {
    s.끄덕 = Math.max(0, s.끄덕 - dt);
    s.q.머리.rotation.x = s.끄덕 > 0 ? Math.sin(지금 * 9) * 0.12 : Math.sin(지금 * 1.3 + s.자리.position.x) * 0.02;
    s.고개 = 다가가기(s.고개, s.목표고개, 5); s.q.머리.rotation.y = s.고개;
    s.앉음 = 다가가기(s.앉음, s.이동 ? 0 : s.목표앉음, 5);
    s.뻗기 = 다가가기(s.뻗기, s.목표뻗기, 6);
    let 걷는 = 0;
    if (s.이동) {   // 경유점을 차례로 따라감 (자리 그룹 기준 좌표)
      const m = s.이동; m.지난 += dt * 속도;
      let 남은 = Math.min(m.지난 * m.속력, m.길이), i = 1;
      while (i < m.점들.length - 1 && 남은 > m.점들[i].distanceTo(m.점들[i - 1])) { 남은 -= m.점들[i].distanceTo(m.점들[i - 1]); i++; }
      const a = m.점들[i - 1], b = m.점들[i], 구간 = Math.max(a.distanceTo(b), 1e-6);
      s.q.사람.position.lerpVectors(a, b, Math.min(남은 / 구간, 1));
      s.q.사람.rotation.y = Math.atan2(b.x - a.x, b.z - a.z);   // 사람은 +z 를 본다
      s.걸음 += dt * 속도 * 8; 걷는 = 1;
      if (m.지난 * m.속력 >= m.길이) { s.이동 = null; if (s.목표앉음 === 1) s.q.사람.rotation.y = 0; }   // 자리에 오면 원탁을 보고 앉음
    }
    자세잡기(s.q, s.앉음, s.걸음, s.뻗기, 걷는);
    s.손 = 다가가기(s.손, s.목표손, 6);
    if (s.손 > 0.01) {   // 한 손만 위로 — 어깨를 머리 위로 올리고 팔꿈치는 거의 폄
      const { 어깨, 팔꿈치 } = s.q.팔[1];
      어깨.rotation.x = THREE.MathUtils.lerp(어깨.rotation.x, -2.85, s.손);
      어깨.rotation.z = THREE.MathUtils.lerp(0, -0.18, s.손);   // 이 팔은 +x 쪽 → 음수여야 바깥으로 살짝 벌어짐
      팔꿈치.rotation.x = THREE.MathUtils.lerp(팔꿈치.rotation.x, -0.2, s.손);
    } else s.q.팔[1].어깨.rotation.z = 0;
    s.든카드들.forEach((c, k) => { c.position.copy(손위치(s)).add(new THREE.Vector3(0, 0.03 * k, 0)); c.rotation.set(0, s.자리.rotation.y + s.q.사람.rotation.y, 0); });
  }
}

export function 무대(그릇) {
  if (장면) return;
  장면 = new THREE.Scene(); 장면.background = new THREE.Color(0x14171c);
  카메라 = new THREE.PerspectiveCamera(46, 그릇.clientWidth / 그릇.clientHeight, 0.1, 100);
  카메라.position.set(0, 4.3, 6.8);   // 칠판을 키운 만큼 조금 더 넓고 높게 본다
  그리기 = new THREE.WebGLRenderer({ antialias: true }); 그리기.shadowMap.enabled = true;
  그리기.setPixelRatio(Math.min(devicePixelRatio, 2)); 그리기.setSize(그릇.clientWidth, 그릇.clientHeight);
  그릇.appendChild(그리기.domElement);
  글씨그리기 = new CSS2DRenderer(); 글씨그리기.setSize(그릇.clientWidth, 그릇.clientHeight);
  글씨그리기.domElement.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none';
  그릇.appendChild(글씨그리기.domElement);
  조종 = new OrbitControls(카메라, 그리기.domElement); 조종.target.set(0, 1.35, -0.4); 조종.maxPolarAngle = Math.PI * 0.47; 조종.update();
  장면.add(new THREE.HemisphereLight(0xeef3f8, 0x3a3530, 1.6));
  장면.add(new THREE.AmbientLight(0xffffff, 0.35));
  const 해 = new THREE.DirectionalLight(0xffffff, 1.8); 해.position.set(3, 7, 4); 해.castShadow = true; 해.shadow.mapSize.set(1024, 1024);
  Object.assign(해.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6 }); 장면.add(해);
  탁자와방(); 모니터 = 모니터만들기(); 사람배치(); 자막 = 자막만들기(그릇); 모니터쓰기(-1, ['회의록을 고르고 ▶ 재생을 누르세요']);
  시계 = new THREE.Clock();
  new ResizeObserver(() => { const w = 그릇.clientWidth, h = 그릇.clientHeight; 카메라.aspect = w / h; 카메라.updateProjectionMatrix(); 그리기.setSize(w, h); 글씨그리기.setSize(w, h); }).observe(그릇);
  그리기.setAnimationLoop(() => { 한틀(Math.min(시계.getDelta(), 0.1)); 그리기.render(장면, 카메라); 글씨그리기.render(장면, 카메라); });
}

// d = /api/meetings/{mid} 응답
export function 불러오기(d) {
  카드들.forEach(c => { c.userData.표.element.remove(); 장면.remove(c); });
  카드들 = []; 할일목록 = []; 장수쓰기(); 멈춤 = true; 시각 = 0; 걷는중 = null; 비서.든카드 = null; 풍선(''); 사람들처음으로();
  비서.무리.position.copy(비서자리); 비서.무리.lookAt(0, 0, 0);
  if (!d.진행) { 모니터쓰기(-1, ['아직 처리하지 않은 회의록입니다', '① 회의록에서 「시연 자료로 채우기」 를 누르세요']); return 0; }
  할일목록 = d.진행.할일.map(x => ({ ...x }));
  할일목록.forEach(x => { x.카드 = 카드만들기(x); 카드들.push(x.카드); });
  모니터쓰기(-1, [`${d.id} ${d.제목} · ${d.회의일}`, `할 일 ${할일목록.length}건 — ▶ 재생을 누르세요`]);
  return 사건만들기(d);
}
// 확인용: 브라우저가 화면을 그리지 않을 때(창이 가려짐) 시간을 손으로 넘긴다 — 회의실3D.손으로(초)
export function 손으로(초, dt = 0.05) {
  for (let t = 0; t < 초; t += dt) 한틀(dt);
  그리기.render(장면, 카메라); 글씨그리기.render(장면, 카메라);
  return { 시각: +시각.toFixed(2), 끝: 사건.at(-1)?.t, 비서위치: 비서.무리.position.toArray().map(v => +v.toFixed(2)),
    카드: 할일목록.map(x => [x.내용.slice(0, 10), x.지금곳 || '탁자', x.상태]),
    도윤: 사람들['도윤']?.q.사람.position.toArray().map(v => +v.toFixed(2)) };
}
export function 재생() {
  if (시각 >= (사건.at(-1)?.t ?? 0)) { 시각 = 0; 할일목록.forEach(x => { x.카드.position.set((Math.random() - 0.5) * 0.6, 0.78, (Math.random() - 0.5) * 0.6);
    x.카드.rotation.set(0, 0, 0); x.카드.material.color.setHex(0xf4f1ea); x.카드.material.opacity = 1; x.지금곳 = null; x.놓인곳 = null; }); 장수쓰기(); 사람들처음으로(); }
  멈춤 = false;
}
export function 잠깐() { 멈춤 = true; }
export function 속도바꾸기(v) { 속도 = v; }
export function 끝으로() { 사건.forEach(e => e.할 && e.t > 시각 && e.할()); 시각 = 사건.at(-1)?.t ?? 0; 걷는중 = null; 비서.든카드 = null;
  비서.무리.position.copy(비서자리); 비서.무리.lookAt(0, 0, 0); 사람들처음으로(); 지금상태맞추기(); 멈춤 = true; }
