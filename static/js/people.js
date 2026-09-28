// 회의실 인물 — three.js 도형. 회의 참석자 4명은 사람, AI 비서(에이전트)는 로봇 (09-28 작성자)
// 출처: 작성자 본인 프로젝트 senior-team-3d/characters.js 의 사람만들기 · 자세잡기 · 로봇만들기를 옮겨 와 인물만 바꿈
import * as THREE from 'three';

const 피부 = 0xf0c9a8;
// 인물은 회의록 머리의 역할 그대로. 색은 구분용
export const 인물 = {
  도윤: { 머리카락: 0x1c1a1a, 옷: 0x2b3a55, 셔츠: 0xf6f6f4, 피부, 머리길이: 0.2, 역할: '대표 · 강사' },
  지수: { 머리카락: 0x3b2a22, 옷: 0x5a2a36, 셔츠: 0xf4f2ee, 피부, 머리길이: 0.36, 역할: '외주 교안 디자이너' },
  민호: { 머리카락: 0x161616, 옷: 0x3a4a3a, 셔츠: 0xeceae4, 피부, 머리길이: 0.2, 안경: true, 역할: '외주 영상 편집자' },
  영숙: { 머리카락: 0x4a3222, 옷: 0x6a5a3a, 셔츠: 0xf6f6f4, 피부, 머리길이: 0.26, 역할: '해맑은복지관 담당자' },
};

// AI 비서 로봇 — 받침 위에 떠 있어 걷지 않고 미끄러지듯 움직인다. 팔은 앞으로 뻗어 카드를 받쳐 든다
export function 로봇만들기() {
  const 금속 = new THREE.MeshStandardMaterial({ color: 0xc4cad2, metalness: 0.3, roughness: 0.35 });
  const 짙은금속 = new THREE.MeshStandardMaterial({ color: 0x4a5360, metalness: 0.3, roughness: 0.45 });
  const 빛 = new THREE.MeshStandardMaterial({ color: 0x4fc3ff, emissive: 0x4fc3ff, emissiveIntensity: 0.6 });
  const 몸 = new THREE.Group();
  const 원판 = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.06, 32), 짙은금속); 원판.position.y = 0.03;
  const 기둥 = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.1, 0.5, 16), 금속); 기둥.position.y = 0.3;
  몸.add(원판, 기둥);
  const 상체 = new THREE.Group(); 상체.position.y = 0.55;
  const 허리 = new THREE.Mesh(new THREE.SphereGeometry(0.13, 20, 14), 짙은금속);
  const 몸통 = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.46, 0.3), 금속); 몸통.position.y = 0.33; 몸통.castShadow = true;
  const 가슴빛 = new THREE.Mesh(new THREE.CircleGeometry(0.06, 24), 빛); 가슴빛.position.set(0, 0.38, 0.152);
  const 목 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.1, 12), 짙은금속); 목.position.y = 0.61;
  상체.add(허리, 몸통, 가슴빛, 목);
  const 머리 = new THREE.Group(); 머리.position.y = 0.66;
  const 머리통 = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.26, 0.28), 금속); 머리통.position.y = 0.14; 머리통.castShadow = true;
  const 얼굴판 = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.12, 0.02), 짙은금속); 얼굴판.position.set(0, 0.15, 0.14);
  머리.add(머리통, 얼굴판);
  for (const s of [-1, 1]) {
    const 눈 = new THREE.Mesh(new THREE.SphereGeometry(0.025, 12, 8), 빛); 눈.position.set(0.065 * s, 0.15, 0.152);
    const 귀 = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.04, 16), 짙은금속); 귀.rotation.z = Math.PI / 2; 귀.position.set(0.19 * s, 0.14, 0);
    머리.add(눈, 귀);
  }
  const 안테나 = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.14), 짙은금속); 안테나.position.y = 0.34;
  const 안테나빛 = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 8), 빛); 안테나빛.position.y = 0.42;
  머리.add(안테나, 안테나빛);
  상체.add(머리);
  for (const s of [-1, 1]) {
    const 어깨 = V(0.27 * s, 0.5, 0), 팔꿈치 = V(0.3 * s, 0.26, 0.22), 손 = V(0.14 * s, 0.3, 0.5);
    상체.add(마디(어깨, 팔꿈치, 0.045, 짙은금속), 마디(팔꿈치, 손, 0.04, 금속));
    const 관절 = new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 10), 짙은금속); 관절.position.copy(어깨);
    const 손모양 = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), 짙은금속); 손모양.position.copy(손);
    상체.add(관절, 손모양);
  }
  몸.add(상체);
  return { 사람: 몸, 상체, 머리, 빛 };
}

const 옆 = s => (s > 0 ? 'L' : 'R');
const 위쪽 = new THREE.Vector3(0, 1, 0);
const V = (x, y, z) => new THREE.Vector3(x, y, z);
function 마디(a, b, r, mat) {
  const dir = new THREE.Vector3().subVectors(b, a);
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, Math.max(dir.length() - r * 2, 0.01), 6, 12), mat);
  m.position.addVectors(a, b).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(위쪽, dir.normalize());
  m.castShadow = true;
  return m;
}

export const 다리길이 = { 허벅지: 0.42, 정강이: 0.45 };
const 선엉덩이높이 = 다리길이.허벅지 + 다리길이.정강이 + 0.07;
const 섞기 = THREE.MathUtils.lerp;

// 캐릭터는 +z 를 본다. 자리 그룹 기준 사람은 z≈-0.3 에 앉는다
export function 사람만들기(c) {
  const 재질 = k => new THREE.MeshStandardMaterial({ color: c[k], roughness: 0.8 });
  const 옷 = 재질('옷'), 피부재질 = 재질('피부'), 머리카락 = 재질('머리카락'), 셔츠 = 재질('셔츠');
  const 의자재질 = new THREE.MeshStandardMaterial({ color: 0x2a2a2e });
  const 사람 = new THREE.Group();

  const 의자 = new THREE.Group();
  의자.position.z = -0.3;
  const 좌판 = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.06, 0.5), 의자재질); 좌판.position.set(0, 0.45, 0);
  const 등받이 = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.6, 0.06), 의자재질); 등받이.position.set(0, 0.8, -0.26);
  const 기둥 = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.42), 의자재질); 기둥.position.set(0, 0.22, 0);
  의자.add(좌판, 등받이, 기둥);
  사람.add(의자);

  const 몸 = new THREE.Group();
  몸.position.set(0, 0.55, -0.3);
  const 다리 = [];
  for (const s of [-1, 1]) {
    const 엉덩이 = new THREE.Group(); 엉덩이.name = `hip_${옆(s)}`; 엉덩이.position.set(0.11 * s, 0, 0);
    엉덩이.add(마디(V(0, 0, 0), V(0, -다리길이.허벅지, 0), 0.075, 옷));
    const 무릎 = new THREE.Group(); 무릎.position.y = -다리길이.허벅지;
    무릎.add(마디(V(0, 0, 0), V(0, -다리길이.정강이, 0), 0.065, 옷));
    const 신발 = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.07, 0.2), 의자재질);
    신발.position.set(0, -다리길이.정강이 - 0.035, 0.05);
    무릎.add(신발); 엉덩이.add(무릎); 몸.add(엉덩이);
    다리.push({ 엉덩이, 무릎 });
  }
  const 상체 = new THREE.Group();
  const 몸통 = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.32, 8, 16), 옷);
  몸통.scale.set(1, 1, 0.72); 몸통.position.set(0, 0.33, 0); 몸통.castShadow = true;
  const 앞섶 = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.28, 3), 셔츠); 앞섶.rotation.set(Math.PI, 0, 0); 앞섶.position.set(0, 0.52, 0.13);
  const 목 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.1), 피부재질); 목.position.set(0, 0.72, 0);
  상체.add(몸통, 앞섶, 목);

  const 머리 = new THREE.Group(); 머리.position.set(0, 0.8, 0);
  const 얼굴 = new THREE.Mesh(new THREE.SphereGeometry(0.15, 24, 18), 피부재질);
  얼굴.scale.set(0.92, 1.1, 0.98); 얼굴.position.y = 0.12; 얼굴.castShadow = true;
  const 눈재질 = new THREE.MeshStandardMaterial({ color: 0x1a1414 });
  for (const s of [-1, 1]) { const 눈 = new THREE.Mesh(new THREE.SphereGeometry(0.018, 10, 8), 눈재질); 눈.position.set(0.05 * s, 0.14, 0.135); 머리.add(눈); }
  const 윗머리 = new THREE.Mesh(new THREE.SphereGeometry(0.168, 24, 16, 0, Math.PI * 2, 0, Math.PI * 0.4), 머리카락);
  윗머리.position.set(0, 0.13, -0.01);
  const h = c.머리길이;
  const 옆머리 = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17 + h * 0.06, h, 24, 1, true, Math.PI * 0.3, Math.PI * 1.4),
    new THREE.MeshStandardMaterial({ color: c.머리카락, roughness: 0.8, side: THREE.DoubleSide }));
  옆머리.position.set(0, 0.19 - h / 2, -0.01);
  머리.add(얼굴, 윗머리, 옆머리);
  if (c.안경) {
    const 테 = new THREE.MeshStandardMaterial({ color: 0x8a8f96, metalness: 0.6, roughness: 0.3 });
    for (const s of [-1, 1]) { const 알 = new THREE.Mesh(new THREE.TorusGeometry(0.036, 0.006, 8, 20), 테); 알.position.set(0.05 * s, 0.14, 0.15); 머리.add(알); }
  }
  상체.add(머리);

  const 팔 = [];
  for (const s of [-1, 1]) {
    const 어깨 = new THREE.Group(); 어깨.position.set(0.21 * s, 0.56, 0);
    어깨.add(마디(V(0, 0, 0), V(0, -0.3, 0), 0.055, 옷));
    const 팔꿈치 = new THREE.Group(); 팔꿈치.position.y = -0.3;
    팔꿈치.add(마디(V(0, 0, 0), V(0, -0.34, 0), 0.05, 옷));
    const 손 = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), 피부재질); 손.scale.set(1, 1.3, 0.6); 손.position.y = -0.38;
    팔꿈치.add(손); 어깨.add(팔꿈치); 상체.add(어깨);
    팔.push({ 어깨, 팔꿈치, 손 });
  }
  몸.add(상체);
  사람.add(몸);
  const q = { 사람, 의자, 몸, 상체, 머리, 다리, 팔 };
  자세잡기(q, 1, 0, 0);
  return q;
}

// 앉음 1 = 앉음 · 0 = 섬 · 걸음 = 걷기 위상 · 뻗기 1 = 팔을 앞으로
export function 자세잡기(q, 앉음, 걸음, 뻗기, 걷는중 = 0) {
  const 흔들 = Math.sin(걸음) * 걷는중;
  q.다리.forEach(({ 엉덩이, 무릎 }, k) => {
    const 방향 = k === 0 ? 1 : -1;
    엉덩이.rotation.x = 섞기(흔들 * 0.5 * 방향, -Math.PI / 2, 앉음);
    무릎.rotation.x = 섞기(Math.max(0, -Math.sin(걸음) * 방향) * 0.7 * 걷는중, Math.PI / 2, 앉음);
  });
  q.팔.forEach(({ 어깨, 팔꿈치 }, k) => {
    const 방향 = k === 0 ? -1 : 1;
    어깨.rotation.x = 섞기(섞기(흔들 * 0.45 * 방향, -1.25, 뻗기), -0.4, 앉음);
    팔꿈치.rotation.x = 섞기(섞기(-0.25, -0.15, 뻗기), -1.1, 앉음);
  });
  q.몸.position.y = 섞기(선엉덩이높이 + Math.abs(Math.sin(걸음)) * 0.03 * 걷는중, 0.55, 앉음);
}
