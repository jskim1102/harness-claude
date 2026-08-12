import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

// href 스킴 검증 — http/https 만 허용(javascript: 등 차단). 백엔드도 가드하지만 프론트 defense-in-depth.
const safeUrl = (u) => {
  if (!u) return null
  try {
    const p = new URL(u)
    return p.protocol === 'http:' || p.protocol === 'https:' ? u : null
  } catch {
    return null
  }
}

// 인박스 시각 표시 — db created 는 UTC("YYYY-MM-DD HH:MM:SS", tz표기 없음)라 그대로 쓰면
// 9시간 어긋나 보인다. UTC 로 파싱(Z 부착) 후 브라우저 로컬(KST)로 포맷.
const fmtTime = (s) => {
  if (!s) return ''
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return s
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 읽기 GET 도 토큰 게이트다 (2026-07-21). vite dev 서버가 host 0.0.0.0 으로 뜨고 /api 를
// loopback backend 로 프록시하므로, 이전엔 같은 망 누구나 인박스 본문·state·schema 를 인증
// 없이 읽었다(실 LAN IP 200 실증). backend 의 127.0.0.1 바인딩은 프록시에 우회된다.
//
// 폴링 루프(state 5초·inbox 5초)가 401 마다 prompt 를 띄우면 팝업 폭탄이 되므로 **페이지당
// 한 번만** 묻는다. 취소하면 더 안 묻고, 사용자는 상단 🔑 토큰 버튼으로 언제든 다시 넣는다.
let _tokenAsked = false
const apiGet = async (url) => {
  const hdr = () => {
    const t = localStorage.getItem('dashToken') || ''
    return t ? { headers: { 'X-Dash-Token': t } } : undefined
  }
  let r = await fetch(url, hdr())
  if (r.status === 401 && !_tokenAsked) {
    _tokenAsked = true
    localStorage.removeItem('dashToken')
    const t = window.prompt('대시보드 토큰 (서버 DASH_TOKEN):') || ''
    if (t) {
      localStorage.setItem('dashToken', t)
      r = await fetch(url, hdr())
    }
  }
  return r
}

// ── README 새 탭 뷰어 ────────────────────────────────────────────────────
// 새 탭은 평범한 GET 이라 X-Dash-Token 헤더를 실을 수 없다. 그래서 SPA 가 **토큰을 붙여**
// /api/readme 를 fetch 한 뒤 HTML 문서를 만들어 Blob URL 로 연다 — 토큰이 URL/히스토리에
// 남지 않고 백엔드 인증도 그대로 유지된다. 새 의존성 없음.
//
// 마크다운은 문자열 HTML 로 만들므로 **모든 텍스트를 esc() 로 이스케이프**한다
// (JSX 와 달리 자동 이스케이프가 없다). 링크는 http(s) 만 통과 — javascript: 차단.
const esc = (t) => String(t)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;')

const mdInlineHtml = (text) => {
  let out = ''
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)\s]+\))/g
  let last = 0, m
  while ((m = re.exec(text)) !== null) {
    out += esc(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) out += `<code>${esc(tok.slice(1, -1))}</code>`
    else if (tok.startsWith('**')) out += `<strong>${esc(tok.slice(2, -2))}</strong>`
    else {
      const cut = tok.indexOf('](')
      const label = esc(tok.slice(1, cut))
      const href = tok.slice(cut + 2, -1)
      out += /^https?:\/\//i.test(href)
        ? `<a href="${esc(href)}" target="_blank" rel="noreferrer noopener">${label}</a>`
        : label
    }
    last = m.index + tok.length
  }
  return out + esc(text.slice(last))
}

const mdToHtml = (src) => {
  const lines = (src || '').split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const ln = lines[i]
    if (ln.startsWith('```')) {                        // 코드펜스
      const lang = ln.slice(3).trim()
      const buf = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++])
      i++
      out.push(`<pre>${lang ? `<span class="lang">${esc(lang)}</span>` : ''}<code>${esc(buf.join('\n'))}</code></pre>`)
      continue
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(ln)
    if (h) { out.push(`<h${h[1].length}>${mdInlineHtml(h[2])}</h${h[1].length}>`); i++; continue }
    if (/^(-{3,}|\*{3,})\s*$/.test(ln)) { out.push('<hr/>'); i++; continue }
    if (/^\s*>/.test(ln)) {
      const buf = []
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''))
      out.push(`<blockquote>${mdInlineHtml(buf.join(' '))}</blockquote>`)
      continue
    }
    if (/^(\s*)([-*]|\d+\.)\s+/.test(ln)) {            // 목록 (연속 묶음, 들여쓰기 보존)
      const items = []
      while (i < lines.length) {
        const m2 = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i])
        if (!m2) break
        items.push(`<li style="margin-left:${Math.floor(m2[1].length / 2) * 18}px">`
          + `<span class="b">${/\d/.test(m2[2]) ? esc(m2[2]) : '·'}</span>${mdInlineHtml(m2[3])}</li>`)
        i++
      }
      out.push(`<ul>${items.join('')}</ul>`)
      continue
    }
    if (!ln.trim()) { i++; continue }
    const buf = []
    while (i < lines.length && lines[i].trim()
           && !lines[i].startsWith('```') && !/^#{1,4}\s/.test(lines[i])
           && !/^\s*([-*]|\d+\.)\s/.test(lines[i]) && !/^\s*>/.test(lines[i])) buf.push(lines[i++])
    out.push(`<p>${mdInlineHtml(buf.join(' '))}</p>`)
  }
  return out.join('\n')
}

const README_CSS = `
:root { color-scheme: dark }
body { margin:0; background:#0b0e17; color:#c3cadb; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
.wrap { max-width: 900px; margin: 0 auto; padding: 40px 28px 80px; }
.top { display:flex; align-items:baseline; gap:12px; border-bottom:1px solid rgba(255,255,255,.1); padding-bottom:14px; margin-bottom:8px; }
.top h1 { font-size:19px; margin:0; color:#e7e9f3; font-weight:800; }
.top .m { color:#6b7280; font-size:12px; margin-left:auto; }
h1,h2,h3,h4 { color:#e7e9f3; line-height:1.35; font-weight:800; }
h1 { font-size:21px; margin:26px 0 10px; padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,.1); }
h2 { font-size:17px; margin:24px 0 8px; color:#67e8f9; }
h3 { font-size:14.5px; margin:18px 0 6px; }
h4 { font-size:13px; margin:14px 0 5px; color:#b8c0d4; }
p { font-size:13.5px; line-height:1.75; margin:10px 0; }
ul { margin:9px 0; padding:0; list-style:none; }
li { display:flex; gap:9px; font-size:13.5px; line-height:1.7; margin:3px 0; }
li .b { color:#67e8f9; flex-shrink:0; min-width:14px; }
pre { position:relative; background:rgba(0,0,0,.36); border:1px solid rgba(255,255,255,.08); border-radius:10px; padding:13px 15px; margin:12px 0; overflow-x:auto; }
pre code { font-family:ui-monospace,SFMono-Regular,monospace; font-size:12.5px; line-height:1.62; color:#d7dcea; white-space:pre; }
pre .lang { position:absolute; top:6px; right:11px; font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:.05em; }
code { font-family:ui-monospace,monospace; font-size:12.5px; background:rgba(103,232,249,.11); color:#a5f3fc; border-radius:5px; padding:1.5px 5px; }
a { color:#67e8f9; text-underline-offset:2px; }
blockquote { border-left:3px solid rgba(103,232,249,.45); margin:12px 0; padding:3px 0 3px 13px; color:#9aa3b8; font-size:13px; }
hr { border:0; border-top:1px solid rgba(255,255,255,.1); margin:20px 0; }
`

// 새 탭을 **먼저** 연다 — fetch 를 await 한 뒤 window.open 하면 사용자 제스처가 끊겨
// 팝업 차단에 걸린다. 빈 탭을 잡아두고 내용이 오면 채운다.
const openReadmeTab = async () => {
  const tab = window.open('', '_blank')
  try {
    const r = await apiGet('/api/readme')
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    if (!d.ok) throw new Error(d.error || '읽기 실패')
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8">`
      + `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">`
      + `<meta name="viewport" content="width=device-width,initial-scale=1">`
      + `<title>README.md · Harness</title><style>${README_CSS}</style></head><body><div class="wrap">`
      + `<div class="top"><h1>📄 README.md</h1><span class="m">수정 ${esc(d.mtime || '')}</span></div>`
      + mdToHtml(d.markdown) + `</div></body></html>`
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    if (tab) { tab.location.href = url } else { window.open(url, '_blank') }
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    if (tab) tab.close()
    alert('README 열기 실패: ' + e)
  }
}

const ctoStateOf = (it) => it.cto_state || (it.cto_active ? 'healthy' : 'both-down')
const ctoHealthy = (it) => ctoStateOf(it) === 'healthy'
const ctoPartial = (it) => ['claude-only', 'codex-only', 'partial'].includes(ctoStateOf(it))
const ctoMissing = (it) => {
  const m = []
  if (!it.cto_claude_active) m.push('Claude')
  if (!it.cto_codex_active) m.push('Codex')
  if (it.cto_designer_active === false) m.push('Designer')
  return m
}
const ctoHalfSummary = (it) => {
  const state = ctoStateOf(it)
  if (state === 'healthy') return 'Claude + Codex + Designer 정상'
  if (ctoPartial(it)) return `${ctoMissing(it).join('·')} 누락 · 나머지 실행 중`
  return 'Claude + Codex + Designer 정지'
}

// 복사 아이콘 — 네모 두개(표준 copy 글리프)
const CopyIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
)

// 연결도 — react-force-graph-2d (물리 레이아웃·드래그·줌·팬). CEO 허브 + lineage 트레이스.
function Graph({ items, links, onPick }) {
  const wrapRef = useRef(null)
  const fgRef = useRef(null)
  const [w, setW] = useState(900)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver((es) => setW(Math.max(320, es[0].contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const nodeCache = useRef(new Map())
  const graphData = useMemo(() => {
    const cache = nodeCache.current
    const want = new Set(['CEO', ...items.map((it) => it.name)])
    let ceo = cache.get('CEO')
    if (!ceo) { ceo = { id: 'CEO', ceo: true }; cache.set('CEO', ceo) }
    const nodes = [ceo]
    for (const it of items) {
      let n = cache.get(it.name)
      if (!n) { n = { id: it.name }; cache.set(it.name, n) }
      n.item = it  // 위치(x/y/vx/vy)는 보존, item 만 갱신
      nodes.push(n)
    }
    for (const k of [...cache.keys()]) if (!want.has(k)) cache.delete(k)
    return { nodes, links: links.map((l) => ({ source: l.source, target: l.target, kind: l.kind })) }
  }, [items, links])

  const roundRect = (ctx, x, y, ww, hh, r) => {
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + ww, y, x + ww, y + hh, r)
    ctx.arcTo(x + ww, y + hh, x, y + hh, r)
    ctx.arcTo(x, y + hh, x, y, r)
    ctx.arcTo(x, y, x + ww, y, r)
    ctx.closePath()
  }

  const draw = (node, ctx) => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    if (node.ceo) {
      const r = 22
      ctx.beginPath(); ctx.arc(node.x, node.y, r + 6, 0, 2 * Math.PI)
      ctx.fillStyle = 'rgba(14,116,144,0.12)'; ctx.fill()      // halo
      ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
      ctx.fillStyle = '#0e7490'; ctx.fill()                    // 본체
      ctx.lineWidth = 2; ctx.strokeStyle = '#ffffff'; ctx.stroke()  // 화이트 링
      ctx.fillStyle = '#ffffff'; ctx.font = '700 9px system-ui, sans-serif'
      ctx.fillText('CEO', node.x, node.y)
      node.__r = r
      return
    }
    const it = node.item
    const col = it.type === 'module' ? '#3b82f6' : '#10b981'
    const name = node.id
    const icon = it.git_repo ? '🏆' : '⏳'
    ctx.font = '600 7px system-ui, sans-serif'
    const tw = ctx.measureText(name).width
    const padL = 7, iconW = 10, gap = 3, padR = 10, hh = 20, ww = padL + iconW + gap + tw + padR
    const x = node.x - ww / 2, y = node.y - hh / 2
    ctx.save()
    ctx.shadowColor = 'rgba(15,23,42,0.18)'; ctx.shadowBlur = 8; ctx.shadowOffsetY = 1.5
    roundRect(ctx, x, y, ww, hh, 10); ctx.fillStyle = '#ffffff'; ctx.fill()
    ctx.restore()
    roundRect(ctx, x, y, ww, hh, 10)
    const healthy = ctoHealthy(it), partial = ctoPartial(it)
    ctx.lineWidth = healthy || partial ? 2 : 1.2
    ctx.strokeStyle = partial ? '#f59e0b' : healthy ? '#10b981' : col
    ctx.stroke()
    // 왼쪽 타입 색 액센트 바
    ctx.fillStyle = col
    roundRect(ctx, x, y + 3, 3, hh - 6, 1.5); ctx.fill()
    // 상태 아이콘
    ctx.textAlign = 'center'; ctx.font = '8px system-ui, sans-serif'
    ctx.fillText(icon, x + padL + iconW / 2 + 1, node.y + 0.5)
    // 이름
    ctx.textAlign = 'left'; ctx.font = '600 7px system-ui, sans-serif'; ctx.fillStyle = '#1f2937'
    ctx.fillText(name, x + padL + iconW + gap, node.y)
    // 활성 신호 점
    if (healthy || partial) {
      ctx.beginPath(); ctx.arc(x + ww - 6, y + 6, 2.2, 0, 2 * Math.PI); ctx.fillStyle = partial ? '#f59e0b' : '#10b981'; ctx.fill()
    }
    node.__w = ww; node.__h = hh
  }

  const pointerArea = (node, color, ctx) => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return
    ctx.fillStyle = color
    if (node.ceo) { ctx.beginPath(); ctx.arc(node.x, node.y, 22, 0, 2 * Math.PI); ctx.fill() }
    else {
      const ww = node.__w || 70, hh = node.__h || 14
      ctx.fillRect(node.x - ww / 2, node.y - hh / 2, ww, hh)
    }
  }

  return (
    <div ref={wrapRef} style={{ width: '100%', height: 520 }}>
      <ForceGraph2D
        ref={fgRef}
        width={w}
        height={520}
        graphData={graphData}
        backgroundColor="#fafafa"
        nodeCanvasObject={draw}
        nodePointerAreaPaint={pointerArea}
        linkColor={(l) => (l.kind === 'lineage' ? '#0e7490' : '#d4dbe6')}
        linkWidth={(l) => (l.kind === 'lineage' ? 1.5 : 0.6)}
        linkDirectionalArrowLength={(l) => (l.kind === 'lineage' ? 4 : 0)}
        linkDirectionalArrowRelPos={1}
        linkDirectionalParticles={(l) => (l.kind === 'lineage' ? 2 : 0)}
        linkDirectionalParticleWidth={1.8}
        linkDirectionalParticleColor={() => '#0e7490'}
        onNodeClick={(node) => node.item && onPick(node.item)}
        cooldownTicks={140}
        onEngineStop={() => fgRef.current && fgRef.current.zoomToFit(400, 60)}
        d3VelocityDecay={0.32}
        nodeRelSize={5}
      />
    </div>
  )
}

// 그래프가 런타임 크래시해도 대시보드 전체 white-screen 안 되게 격리 + 에러 노출
class GraphBoundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(e) { return { err: e } }
  render() {
    if (this.state.err) {
      return (
        <div style={{ padding: 20, color: '#b91c1c', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }}>
          그래프 렌더 오류:{'\n'}{String((this.state.err && (this.state.err.stack || this.state.err.message)) || this.state.err)}
        </div>
      )
    }
    return this.props.children
  }
}

// Memory Core — 옵시디언 brain 글로우 연결도 (캔버스 블룸, 라이브 데이터, 클릭→모달)
const NODE_COLORS = ['#ff8c3b', '#39d98a', '#4d9bff', '#e25bd0', '#b07bff', '#ffd23b', '#22d3ee', '#f472b6']

function BrainGraph({ items, links, onNode, onHub, harnessDirty }) {
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const stateRef = useRef({ nodes: [], W: 900, H: 460 })

  const model = useMemo(() => {
    const n = items.length
    // lineage: 루트(모듈/독립)는 링에, 자식(파생물)은 부모 '우측'(+x)에 세로로 펼쳐
    // 배치한다 — 예: rtsp-streaming 오른쪽에 cam-distance·tunnel. 노드는 정적 배치라
    // 좌표만 정하면 그대로 그려진다.
    const parentOf = {}
    ;(links || []).forEach((l) => { if (l.kind === 'lineage') parentOf[l.target] = l.source })
    const kids = {}
    Object.entries(parentOf).forEach(([c, p]) => { (kids[p] = kids[p] || []).push(c) })
    const find = (nm) => items.find((x) => x.name === nm)
    const roots = items.filter((it) => !parentOf[it.name] || !find(parentOf[it.name]))
    const pos = {}
    const R = Math.max(roots.length, 1)
    roots.forEach((it, i) => {
      const ang = (i / R) * 2 * Math.PI - Math.PI / 2
      pos[it.name] = { x: 0.5 + 0.34 * Math.cos(ang), y: 0.5 + 0.37 * Math.sin(ang) }
    })
    const placeKids = (name) => {
      const ks = (kids[name] || []).filter(find)
      const p = pos[name]; if (!p) return
      ks.forEach((c, k) => {
        if (pos[c]) return
        pos[c] = {
          x: Math.min(0.95, p.x + 0.14),                                    // 부모보다 오른쪽
          y: Math.max(0.06, Math.min(0.94, p.y + (k - (ks.length - 1) / 2) * 0.12)),
        }
        placeKids(c)
      })
    }
    roots.forEach((it) => placeKids(it.name))
    items.forEach((it, i) => {                                              // 미배치(사이클) 링 fallback
      if (!pos[it.name]) {
        const ang = (i / Math.max(n, 1)) * 2 * Math.PI - Math.PI / 2
        pos[it.name] = { x: 0.5 + 0.34 * Math.cos(ang), y: 0.5 + 0.37 * Math.sin(ang) }
      }
    })
    // 겹침 방지 — 계보 체인(streaming→detection→keypoint)이 우측 클램프로 쌓이면
    // rtsp-detection↔rtsp-keypoint 가 포개진다. 충돌 완화: 너무 가까운 노드는 서로
    // 밀어내고, CEO(중심)에서도 최소거리 확보. 정적 배치라 1회 수렴이면 충분.
    const cl = (v) => Math.max(0.07, Math.min(0.94, v))
    const nm = Object.keys(pos)
    const MIND = 0.13
    for (let iter = 0; iter < 80; iter++) {
      let moved = false
      for (let a = 0; a < nm.length; a++) {
        const pc = pos[nm[a]]
        let cdx = pc.x - 0.5, cdy = pc.y - 0.5, cd = Math.hypot(cdx, cdy) || 0.0001
        if (cd < 0.15) { cdx /= cd; cdy /= cd; pc.x = cl(0.5 + cdx * 0.15); pc.y = cl(0.5 + cdy * 0.15); moved = true }
        for (let b = a + 1; b < nm.length; b++) {
          const pa = pos[nm[a]], pb = pos[nm[b]]
          let dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.hypot(dx, dy) || 0.0001
          if (d < MIND) {
            const push = (MIND - d) / 2; dx /= d; dy /= d
            pa.x = cl(pa.x - dx * push); pa.y = cl(pa.y - dy * push)
            pb.x = cl(pb.x + dx * push); pb.y = cl(pb.y + dy * push)
            moved = true
          }
        }
      }
      if (!moved) break
    }
    const nodes = [{
      id: 'CEO', label: 'DEEP.INC', x: 0.5, y: 0.5, r: 21, color: '#2dd4ef', hub: true,
      needsCommit: (harnessDirty || 0) > 0,   // 허브 = 하네스 저장소 자신
    }]
    items.forEach((it, i) => {
      nodes.push({
        id: it.name, label: it.name, item: it,
        x: pos[it.name].x, y: pos[it.name].y,
        r: 12 + (i % 3) * 2.4, color: it.type === 'module' ? '#a78bfa' : '#34d399',
        active: ctoHealthy(it), partial: ctoPartial(it),
        needsCommit: (it.git_dirty || 0) > 0,
      })
    })
    nodes.forEach((nd, i) => { nd.phase = i * 1.7; nd.speed = 0.6 + (i % 3) * 0.18 })
    const byId = {}; nodes.forEach((nd) => { byId[nd.id] = nd })
    const ls = (links || []).filter((l) => byId[l.source] && byId[l.target])
      .map((l) => ({ a: l.source, b: l.target, lineage: l.kind === 'lineage' }))
    return { nodes, byId, links: ls }
  }, [items, links, harnessDirty])
  const modelRef = useRef(model)
  modelRef.current = model

  const onClick = (e) => {
    const cv = canvasRef.current; if (!cv) return
    const rect = cv.getBoundingClientRect()
    const mx = e.clientX - rect.left, my = e.clientY - rect.top
    const { nodes, W, H } = stateRef.current
    for (const nd of nodes) {
      const dx = mx - nd.x * W, dy = my - nd.y * H
      if (dx * dx + dy * dy <= (nd.r + 11) * (nd.r + 11)) {
        if (nd.hub) { if (onHub) onHub(); return }
        if (nd.item) { onNode(nd.item); return }
      }
    }
  }

  useEffect(() => {
    const cv = canvasRef.current, wrap = wrapRef.current
    if (!cv || !wrap) return
    const ctx = cv.getContext('2d')
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let H = 460
    let W = 900, dpr = 1, raf = 0, start = null
    const st = stateRef.current; st.H = H

    const stars = []
    let rnd = 1234567
    const rand = () => { rnd = (rnd * 1103515245 + 12345) & 0x7fffffff; return rnd / 0x7fffffff }
    for (let i = 0; i < 380; i++) { const big = rand() > 0.86; stars.push({ x: rand(), y: rand(), r: big ? rand() * 1.3 + 1.1 : rand() * 0.8 + 0.2, a: rand() * 0.5 + 0.06, tw: rand() * 6.28, hue: rand() }) }
    // 느리게 떠다니는 우주먼지 (depth)
    const dust = []
    for (let i = 0; i < 26; i++) { dust.push({ x: rand(), y: rand(), r: rand() * 1.4 + 0.6, vx: (rand() - 0.5) * 0.006, vy: (rand() - 0.5) * 0.006, a: rand() * 0.12 + 0.03 }) }

    const rgba = (hex, a) => {
      const h = hex.replace('#', '')
      return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`
    }
    const resize = () => {
      W = wrap.clientWidth || 900
      H = Math.round(Math.min(720, Math.max(480, W * 0.54)))
      dpr = Math.max(1, window.devicePixelRatio || 1)
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.height = H + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      st.W = W; st.H = H
    }
    const drawNode = (nd, t) => {
      const x = nd.x * W, y = nd.y * H
      const twinkle = reduce ? 1 : (0.82 + 0.18 * Math.sin(t * nd.speed + nd.phase))
      const r = nd.r
      let ap = 1
      if (nd.active && !reduce) ap = 0.6 + 0.4 * (0.5 + 0.5 * Math.sin(t * 2.2 + nd.phase))
      ctx.save()
      const haloR = r * (nd.hub ? 11 : 7) * (nd.hub ? 1 : twinkle)
      const halo = ctx.createRadialGradient(x, y, 0, x, y, haloR)
      if (nd.hub) {
        halo.addColorStop(0, rgba('#ffffff', 0.55 * twinkle)); halo.addColorStop(0.15, rgba(nd.color, 0.45 * twinkle))
        halo.addColorStop(0.45, rgba(nd.color, 0.16 * twinkle)); halo.addColorStop(1, rgba(nd.color, 0))
      } else {
        halo.addColorStop(0, rgba(nd.color, 0.5 * twinkle)); halo.addColorStop(0.4, rgba(nd.color, 0.16 * twinkle)); halo.addColorStop(1, rgba(nd.color, 0))
      }
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(x, y, haloR, 0, 6.283); ctx.fill()
      // 링은 두 축이 겹친다: 실행중(초록/주황) · commit 필요(빨강).
      // 둘 다면 반지름을 벌려 **2줄로 함께** 보인다 (한쪽이 다른쪽을 덮지 않게).
      // 한 축만이면 기존과 같은 반지름 하나 — 단독 상태의 모양은 안 바뀐다.
      const running = nd.active || nd.partial
      if (running || nd.needsCommit) {
        const ringR = r + 5 + (reduce ? 0 : 2.5 * ap)
        const rings = []
        if (running) rings.push([ringR, nd.partial ? '#ffb547' : '#39d98a'])
        if (nd.needsCommit) rings.push([running ? ringR + 4.5 : ringR, '#ff5c66'])
        for (const [rr, rc] of rings) {
          ctx.shadowBlur = 12; ctx.shadowColor = rgba(rc, 0.9)
          ctx.strokeStyle = rgba(rc, 0.55 + 0.35 * ap); ctx.lineWidth = 1.6
          ctx.beginPath(); ctx.arc(x, y, rr, 0, 6.283); ctx.stroke()
        }
        ctx.shadowBlur = 0
      }
      ctx.shadowBlur = (nd.hub ? 44 : 22) * twinkle; ctx.shadowColor = rgba(nd.color, 0.95)
      const coreR = r * (nd.active ? (0.92 + 0.12 * ap) : (reduce ? 1 : 0.95 + 0.05 * Math.sin(t * 1.1 + nd.phase)))
      const core = ctx.createRadialGradient(x - r * 0.25, y - r * 0.25, 0, x, y, coreR)
      if (nd.hub) { core.addColorStop(0, 'rgba(255,255,255,1)'); core.addColorStop(0.35, rgba('#bdf6ff', 1)); core.addColorStop(1, rgba(nd.color, 1)) }
      else { core.addColorStop(0, 'rgba(255,255,255,0.95)'); core.addColorStop(0.4, rgba(nd.color, 1)); core.addColorStop(1, rgba(nd.color, 0.85)) }
      ctx.fillStyle = core; ctx.beginPath(); ctx.arc(x, y, coreR, 0, 6.283); ctx.fill()
      ctx.restore()
      ctx.save(); ctx.shadowBlur = 4; ctx.shadowColor = 'rgba(0,0,0,0.9)'
      ctx.font = (nd.hub ? '700 15px ' : '500 13px ') + 'system-ui, sans-serif'
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillStyle = nd.hub ? 'rgba(220,250,255,0.95)' : 'rgba(200,214,235,0.82)'
      ctx.fillText(nd.label, x, y + (nd.hub ? r + 16 : r + 12))
      ctx.restore()
    }
    const draw = (t) => {
      const { nodes, byId, links: ls } = modelRef.current
      st.nodes = nodes
      ctx.fillStyle = '#04050a'; ctx.fillRect(0, 0, W, H)
      const cx = W * 0.5, cy = H * 0.5
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * 0.6)
      g.addColorStop(0, 'rgba(20,40,55,0.35)'); g.addColorStop(0.5, 'rgba(8,14,24,0.12)'); g.addColorStop(1, 'rgba(4,5,10,0)')
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
      // 은은한 성운 (subtle nebula)
      const neb = (nx, ny, rad, col) => {
        const ng = ctx.createRadialGradient(nx, ny, 0, nx, ny, rad)
        ng.addColorStop(0, col); ng.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.fillStyle = ng; ctx.fillRect(0, 0, W, H)
      }
      const M = Math.max(W, H)
      const drift = reduce ? 0 : Math.sin(t * 0.05) * 0.03
      neb(W * (0.16 + drift), H * 0.16, M * 0.52, 'rgba(124,58,237,0.22)')
      neb(W * 0.86, H * (0.84 - drift), M * 0.48, 'rgba(34,211,238,0.16)')
      neb(W * 0.72, H * 0.20, M * 0.36, 'rgba(59,130,246,0.15)')
      neb(W * 0.40, H * 0.96, M * 0.42, 'rgba(217,70,239,0.10)')
      neb(W * (0.08 - drift), H * 0.62, M * 0.34, 'rgba(99,102,241,0.11)')
      neb(W * 0.95, H * 0.30, M * 0.30, 'rgba(167,139,250,0.10)')
      for (const s of stars) {
        const tw = reduce ? 1 : (0.6 + 0.4 * Math.sin(t * 0.8 + s.tw))
        ctx.save()
        if (s.r > 1) { ctx.shadowBlur = 6; ctx.shadowColor = 'rgba(180,210,255,0.85)' }
        ctx.beginPath(); ctx.fillStyle = `rgba(212,226,255,${(s.a * tw).toFixed(3)})`; ctx.arc(s.x * W, s.y * H, s.r, 0, 6.283); ctx.fill()
        ctx.restore()
      }
      // 떠다니는 우주먼지
      if (!reduce) for (const d of dust) {
        d.x = (d.x + d.vx * 0.016 + 1) % 1; d.y = (d.y + d.vy * 0.016 + 1) % 1
        ctx.beginPath(); ctx.fillStyle = `rgba(150,180,255,${d.a.toFixed(3)})`; ctx.arc(d.x * W, d.y * H, d.r, 0, 6.283); ctx.fill()
      }
      // 주기적 별똥별 (~9초마다 대각선 스트릭)
      if (!reduce) {
        const period = 9, tt = t % period
        if (tt < 0.7) {
          const p = tt / 0.7, sx = W * 0.12 + W * 0.78 * p, sy = H * 0.12 + H * 0.34 * p, len = M * 0.10
          const grd = ctx.createLinearGradient(sx - len, sy - len * 0.42, sx, sy)
          grd.addColorStop(0, 'rgba(255,255,255,0)'); grd.addColorStop(1, `rgba(255,255,255,${(0.85 * (1 - p)).toFixed(2)})`)
          ctx.save(); ctx.strokeStyle = grd; ctx.lineWidth = 2; ctx.lineCap = 'round'
          ctx.shadowBlur = 10; ctx.shadowColor = 'rgba(190,246,255,0.9)'
          ctx.beginPath(); ctx.moveTo(sx - len, sy - len * 0.42); ctx.lineTo(sx, sy); ctx.stroke(); ctx.restore()
        }
      }
      ls.forEach((l, li) => {
        const a = byId[l.a], b = byId[l.b]
        const ax = a.x * W, ay = a.y * H, bx = b.x * W, by = b.y * H
        if (l.lineage) {
          const pulse = reduce ? 1 : (0.75 + 0.25 * Math.sin(t * 1.4))
          ctx.save(); ctx.shadowBlur = 8; ctx.shadowColor = rgba('#39d98a', 0.6)
          const gr = ctx.createLinearGradient(ax, ay, bx, by)
          gr.addColorStop(0, rgba('#4d9bff', 0.55 * pulse)); gr.addColorStop(1, rgba('#39d98a', 0.55 * pulse))
          ctx.strokeStyle = gr; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.restore()
        } else {
          ctx.strokeStyle = 'rgba(120,150,190,0.18)'; ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        }
        // 모든 선에 이동 입자 (원자 전자처럼) — 링크별 위상차(li)로 비동기 이동
        if (!reduce) {
          const p = (t * 0.35 + li * 0.17) % 1
          const ppx = ax + (bx - ax) * p, ppy = ay + (by - ay) * p
          ctx.save(); ctx.shadowBlur = 10; ctx.shadowColor = rgba('#bdf6ff', 0.9)
          ctx.fillStyle = l.lineage ? 'rgba(255,255,255,0.95)' : 'rgba(190,225,255,0.85)'
          ctx.beginPath(); ctx.arc(ppx, ppy, l.lineage ? 2.2 : 1.8, 0, 6.283); ctx.fill(); ctx.restore()
        }
      })
      for (const nd of nodes) if (!nd.hub) drawNode(nd, t)
      for (const nd of nodes) if (nd.hub) drawNode(nd, t)
    }
    const frame = (ts) => { if (start === null) start = ts; draw((ts - start) / 1000); if (!reduce) raf = requestAnimationFrame(frame) }
    resize()
    const ro = new ResizeObserver(() => { resize(); if (reduce) draw(0) })
    ro.observe(wrap)
    if (reduce) draw(0); else raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [])

  return (
    <div ref={wrapRef} style={{ width: '100%' }}>
      <canvas ref={canvasRef} onClick={onClick}
              style={{ display: 'block', width: '100%', height: 460, borderRadius: 14, cursor: 'pointer' }} />
    </div>
  )
}

// 연결도 = Mission Control — 다크 네온 카드 그리드 (노드/프로젝트 = 글로우 카드)
const mcCss = `
.mc { background: radial-gradient(1100px 420px at 18% -12%, #2a1b4d 0%, #140f2e 42%, #0b0a1a 100%); border-radius: 20px; padding: 30px; color: #e7e9f3; }
.mc-head { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; margin-bottom: 26px; }
.mc-title { font-size: 38px; font-weight: 800; letter-spacing: -0.5px; background: linear-gradient(90deg,#c4b5fd,#67e8f9); -webkit-background-clip: text; background-clip: text; color: transparent; }
.mc-sub { color: #b4b9d0; font-size: 13px; margin-top: 5px; letter-spacing: 0.4px; }
.mc-stats { display: flex; gap: 10px; flex-wrap: wrap; }
.mc-chip { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.09); border-radius: 13px; padding: 9px 15px; display: flex; flex-direction: column; min-width: 64px; }
.mc-chip b { font-size: 19px; line-height: 1.1; }
.mc-chip span { font-size: 10px; color: #b4b9d0; letter-spacing: 1px; text-transform: uppercase; margin-top: 2px; }
.mc-core { border: 1px solid rgba(255,255,255,0.07); border-radius: 14px; overflow: hidden; margin-bottom: 24px; background: #04050a; }
.mc-cap { font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #b4b9d0; margin: 0 0 10px 2px; display: flex; align-items: center; gap: 7px; }
.mc-cap .dot { width: 6px; height: 6px; border-radius: 50%; background: #2dd4ef; box-shadow: 0 0 8px #2dd4ef; }
.mc-split { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; position: relative; }
.mc-split::before { content: ''; position: absolute; top: 0; bottom: 0; left: 50%; width: 1px; background: rgba(255,255,255,0.07); transform: translateX(-50%); }
.mc-col { min-width: 0; }
.mc-col-head { font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin: 0 0 12px 2px; display: flex; align-items: center; gap: 7px; }
.mc-col-head em { color: #b4b9d0; font-style: normal; font-weight: 600; }
.mc-dot { width: 7px; height: 7px; border-radius: 50%; }
.mc-col-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(208px,1fr)); gap: 14px; align-content: start; }
@media (max-width: 820px) { .mc-split { grid-template-columns: 1fr; } .mc-split::before { display: none; } }
.mc-card { position: relative; text-align: left; cursor: pointer; overflow: hidden; background: linear-gradient(158deg, rgba(255,255,255,0.07), rgba(255,255,255,0.015)); border: 1px solid rgba(255,255,255,0.10); border-radius: 16px; padding: 18px; color: #e7e9f3; font-family: inherit; transition: transform .16s, box-shadow .16s, border-color .16s; }
.mc-card:hover { transform: translateY(-3px); border-color: var(--a); box-shadow: 0 12px 34px -10px var(--a); }
.mc-bar { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--a); box-shadow: 0 0 14px var(--a); }
.mc-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.mc-icon { width: 44px; height: 44px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 21px; border: 1px solid; flex-shrink: 0; }
.mc-name { flex: 1; min-width: 0; }
.mc-eye { font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #b4b9d0; margin-bottom: 3px; }
.mc-nm { font-size: 16px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 14px; }
.mc-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.5px; padding: 3px 9px; border-radius: 20px; border: 1px solid; white-space: nowrap; }
.mc-cells { display: flex; gap: 8px; }
.mc-cell { flex: 1; background: rgba(0,0,0,0.28); border-radius: 10px; padding: 8px 10px; display: flex; flex-direction: column; gap: 3px; }
.mc-cell span { font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #b4b9d0; }
.mc-cell b { font-size: 14px; font-family: ui-monospace, monospace; }
.mc-open { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: var(--a); }
`

function MissionControl({ items, links, onPick, onNode, updated, onHub, harnessDirty }) {
  const accents = ['#fb923c', '#ec4899', '#38bdf8', '#34d399', '#a78bfa', '#22d3ee', '#f59e0b', '#f472b6']
  const mods = items.filter((i) => i.type === 'module')
  const projs = items.filter((i) => i.type === 'project')
  const active = items.filter(ctoHealthy).length
  const partial = items.filter(ctoPartial).length
  const badge = (it) => {
    if (ctoPartial(it)) return { t: 'CTO PARTIAL', c: '#fbbf24' }
    if (ctoHealthy(it)) return { t: 'LIVE', c: '#34d399' }
    if (it.status === 'up') return { t: 'UP', c: '#34d399' }
    if (it.status === 'partial') return { t: 'PARTIAL', c: '#fbbf24' }
    if (it.status === 'down') return { t: 'IDLE', c: '#64748b' }
    return { t: '—', c: '#64748b' }
  }
  const card = (it) => {
    const a = it.type === 'module' ? '#a78bfa' : '#34d399'
    const b = badge(it)
    return (
      <button key={it.type + '/' + it.name} className="mc-card" style={{ '--a': a }} onClick={() => onPick(it)}>
        <div className="mc-bar" />
        <div className="mc-top">
          <div className="mc-icon" style={{ background: a + '22', color: a, borderColor: a + '55' }}>{it.git_repo ? '🏆' : '⏳'}</div>
          <span className="mc-badge" style={{ color: b.c, borderColor: b.c + '66', background: b.c + '1a' }}>● {b.t}</span>
        </div>
        <div className="mc-eye">{it.type}</div>
        <div className="mc-nm">{it.name}</div>
        <div className="mc-cells">
          <div className="mc-cell"><span>offset</span><b>{it.offset ?? '—'}</b></div>
          <div className="mc-cell"><span>ports</span><b>{it.running}/{it.declared}</b></div>
          <div className="mc-cell"><span>db</span><b>{it.db && it.db !== '—' ? it.db : '—'}</b></div>
        </div>
      </button>
    )
  }
  return (
    <div className="mc">
      <style>{mcCss}</style>
      <div className="mc-head">
        <div>
          <div className="mc-title">Mission Control</div>
        </div>
        <div className="mc-stats">
          <div className="mc-chip"><b>{mods.length}</b><span>modules</span></div>
          <div className="mc-chip"><b>{projs.length}</b><span>projects</span></div>
          <div className="mc-chip"><b style={{ color: '#34d399' }}>{active}</b><span>live cto</span></div>
          <div className="mc-chip"><b style={{ color: partial ? '#fbbf24' : '#8891aa' }}>{partial}</b><span>partial</span></div>
          <div className="mc-chip"><b style={{ fontSize: 13 }}>{updated || '—'}</b><span>sync</span></div>
        </div>
      </div>
      <div className="mc-core"><BrainGraph items={items} links={links} onNode={onNode} onHub={onHub} harnessDirty={harnessDirty} /></div>
      <div className="mc-split">
        <section className="mc-col">
          <div className="mc-col-head" style={{ color: '#a78bfa' }}><span className="mc-dot" style={{ background: '#a78bfa' }} />MODULES <em>{mods.length}</em></div>
          <div className="mc-col-grid">{mods.map(card)}</div>
        </section>
        <section className="mc-col">
          <div className="mc-col-head" style={{ color: '#34d399' }}><span className="mc-dot" style={{ background: '#34d399' }} />PROJECTS <em>{projs.length}</em></div>
          <div className="mc-col-grid">{projs.map(card)}</div>
        </section>
      </div>
    </div>
  )
}

// 포트 레지스트리 — Mission Control 다크 스타일 테이블
const prCss = `
.pr { background: radial-gradient(1100px 380px at 82% -20%, #21183f 0%, #140f2e 45%, #0b0a1a 100%); border-radius: 20px; padding: 26px 28px; color: #e7e9f3; }
.pr-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.pr-title { display: inline-block; font-size: 38px; font-weight: 800; letter-spacing: -0.5px; background: linear-gradient(90deg,#c4b5fd,#67e8f9); -webkit-background-clip: text; background-clip: text; color: transparent; }
.pr-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.pr-btn { border-radius: 10px; padding: 9px 15px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; letter-spacing: 0.3px; }
.pr-btn:disabled { opacity: 0.5; cursor: default; }
.pr-cto-start { background: #14532d; color: #bbf7d0; border: 1px solid #16a34a; }
.pr-cto-start:hover:not(:disabled) { background: #166534; }
.pr-cto-stop { background: #78350f; color: #fde68a; border: 1px solid #b45309; }
.pr-cto-stop:hover:not(:disabled) { background: #92400e; }
.cto-start-choices { display: flex; flex-direction: column; gap: 10px; margin-top: 6px; }
.csc-btn { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 12px 14px; font-size: 14px; white-space: normal; text-align: left; }
.csc-sub { font-size: 11px; opacity: 0.75; font-weight: 400; }
.csc-fresh { background: #4a1d1d; color: #fecaca; border: 1px solid #b91c1c; }
.csc-fresh:hover:not(:disabled) { background: #5f2020; }
.pr-shutdown { background: #7f1d1d; color: #fecaca; border: 1px solid #b91c1c; border-radius: 10px; padding: 9px 15px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; letter-spacing: 0.3px; }
.pr-shutdown:hover:not(:disabled) { background: #991b1b; }
.pr-shutdown:disabled { opacity: 0.5; cursor: default; }
.pr-sub { color: #b4b9d0; font-size: 12px; letter-spacing: 0.4px; margin-bottom: 18px; }
.pr-wrap { overflow-x: auto; border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }
.pr-table { border-collapse: collapse; width: 100%; font-size: 12.5px; white-space: nowrap; font-family: system-ui, sans-serif; }
.pr-table th { text-align: center; padding: 11px 13px; color: #b4b9d0; font-weight: 600; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.025); }
.pr-table th.l, .pr-table td.l { text-align: left; }
.pr-table td { padding: 11px 13px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.05); color: #cdd3e3; }
.pr-table tbody tr:last-child td { border-bottom: none; }
.pr-table tbody tr:hover td { background: rgba(255,255,255,0.03); }
.pr-name { font-weight: 700; font-family: system-ui, sans-serif; }
.pr-dim { color: #8891aa; }
`

function PortRegistry({ columns, items, onPick, onShutdownAll, onCtoAll, shuttingDown, ctoStartBusy, ctoStopBusy, globalBusy }) {
  const typeC = (t) => (t === 'module' ? '#a78bfa' : '#34d399')
  const rows = [...items].sort((a, b) => (a.offset ?? 9999) - (b.offset ?? 9999))
  const readyCount = items.filter(ctoHealthy).length
  const liveCount = items.filter((it) => ctoStateOf(it) !== 'both-down').length
  const ctoStatus = (it) => {
    const state = ctoStateOf(it)
    if (state === 'healthy') return <span style={{ color: '#34d399' }}>✅ ready</span>
    if (ctoPartial(it)) return <span style={{ color: '#fbbf24' }} title={`${ctoMissing(it).join('·')} 누락`}>⚠ partial</span>
    return <span className="pr-dim">✋ inactive</span>
  }
  return (
    <div className="pr">
      <style>{prCss}</style>
      <div className="pr-head">
        <div className="pr-title">Port Registry</div>
        <div className="pr-actions">
          {onCtoAll && (
            <>
              <button
                className="pr-btn pr-cto-start"
                disabled={globalBusy || readyCount === items.length}
                onClick={() => onCtoAll('start')}
                title="모든 프로젝트·모듈의 Claude+Codex CTO pair 활성화 (partial은 복구)"
              >{ctoStartBusy ? '활성화중…' : '▶ CTO 활성화'}</button>
              <button
                className="pr-btn pr-cto-stop"
                disabled={globalBusy || liveCount === 0}
                onClick={() => onCtoAll('stop')}
                title="모든 CTO 세션 정지 — 작업 보존(세션만) · CEO·dev·docker 는 유지"
              >{ctoStopBusy ? '종료중…' : '■ CTO 종료'}</button>
            </>
          )}
          {onShutdownAll && (
            <button
              className="pr-shutdown"
              disabled={globalBusy}
              onClick={onShutdownAll}
              title="run.sh down + stop-ceo — CEO·모든 CTO·dev·docker 종료 (대시보드는 유지)"
            >{shuttingDown ? '종료중…' : '⏻ 종료'}</button>
          )}
        </div>
      </div>
      <div className="pr-wrap">
        <table className="pr-table">
          <thead>
            <tr>
              <th className="l">node</th>
              <th>off</th>
              <th>cto</th>
              <th>진행</th>
              {columns.map((c) => <th key={c.label} style={{ whiteSpace: 'pre-line' }}>{c.label.replace(' ', '\n')}</th>)}
              <th>commit</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((it) => {
              return (
                <tr key={it.type + '/' + it.name}>
                  <td className="l pr-name" style={{ color: typeC(it.type), cursor: 'pointer', textDecoration: 'underline dotted' }} onClick={() => onPick(it)} title="클릭 — 상세/컨트롤">{it.name}</td>
                  <td>{it.offset ?? <span className="pr-dim">—</span>}</td>
                  <td>{ctoStatus(it)}</td>
                  <td>{it.progress
                    ? <span style={{ fontFamily: 'ui-monospace, monospace', color: it.progress.done === it.progress.total ? '#34d399' : '#cdd3e3' }}>{it.progress.done}/{it.progress.total}</span>
                    : <span className="pr-dim">—</span>}</td>
                  {columns.map((c) => {
                    if (c.kind === 'db') {
                      return <td key={c.label}>{it.db && it.db !== '—' ? it.db : <span className="pr-dim">—</span>}</td>
                    }
                    const cell = it.cells[c.var]
                    return (
                      <td key={c.label}>
                        {cell
                          ? <span style={{ color: cell.up ? '#cdd3e3' : '#9aa3b8' }}>{cell.port} {cell.mode === 'docker' ? '🐳' : cell.mode === 'dev' ? '💻' : cell.mode === 'mock' ? <span title="목업 프리뷰 (§4.1 http.server — dev 아님)">🎨</span> : cell.mode === 'shared' ? '🔗' : <span style={{ color: '#8891aa' }}>○</span>}
                              {cell.owner && <span style={{ color: '#fbbf24', marginLeft: 4 }}
                                title={`이 포트는 '${cell.owner}' compose 프로젝트가 잡고 있다 — 이 프로젝트의 docker 종료로는 안 내려간다`}>⚠</span>}</span>
                          : <span className="pr-dim">—</span>}
                      </td>
                    )
                  })}
                  <td style={{ color: '#8891aa' }}>{it.commit_date || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// 인박스 카드/본문 공용 시각 — CEO 인박스(CeoInboxView)와 pair 인박스(PairInboxView)가
// 둘 다 상세 모달 안에서 이 클래스들을 쓴다. 모달 껍데기는 S.modal 담당.
const ibCss = `
.ib-clear-btn { background: #7f1d1d; color: #fecaca; border: 1px solid #b91c1c; border-radius: 10px; padding: 8px 14px; font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.ib-clear-btn:hover:not(:disabled) { background: #991b1b; }
.ib-clear-btn:disabled { opacity: 0.5; cursor: default; }
.ib-err { color: #fecaca; margin-bottom: 12px; font-size: 13px; }
.ib-empty { color: #8891aa; padding: 48px; text-align: center; font-size: 14px; }
.ib-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
.ib-card { text-align: left; font-family: inherit; cursor: pointer; height: 148px; display: flex; flex-direction: column; gap: 8px; background: linear-gradient(158deg, rgba(255,255,255,0.06), rgba(255,255,255,0.015)); border: 1px solid rgba(255,255,255,0.09); border-radius: 14px; padding: 13px 15px; color: #e7e9f3; overflow: hidden; transition: transform .14s, border-color .14s, box-shadow .14s; }
.ib-card:hover { transform: translateY(-2px); border-color: rgba(103,232,249,0.5); box-shadow: 0 10px 26px -12px rgba(103,232,249,0.5); }
.ib-card.unread { border-color: rgba(103,232,249,0.4); box-shadow: inset 0 0 0 1px rgba(103,232,249,0.12); }
.ib-card-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.ib-card-from { font-weight: 700; color: #67e8f9; font-family: ui-monospace, monospace; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ib-card-id { color: #8891aa; font-size: 10px; white-space: nowrap; flex-shrink: 0; }
.ib-card-preview { flex: 1; color: #b8c0d4; font-size: 11.5px; line-height: 1.45; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; white-space: pre-wrap; word-break: break-word; }
.ib-card-foot { display: flex; align-items: center; justify-content: space-between; }
.ib-card-time { color: #6b7280; font-size: 10px; }
.ib-dot { width: 7px; height: 7px; border-radius: 50%; background: #67e8f9; box-shadow: 0 0 7px #67e8f9; flex-shrink: 0; }

.ib-modal-from { font-weight: 700; color: #67e8f9; font-family: ui-monospace, monospace; font-size: 14px; }
.ib-modal-meta { margin-left: auto; color: #8891aa; font-size: 11px; white-space: nowrap; }
.ib-del-btn { background: #7f1d1d; color: #fecaca; border: 1px solid #b91c1c; border-radius: 10px; padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; }
.ib-del-btn:hover { background: #991b1b; }
.ib-read-btn { background: #0e7490; color: #e0f2fe; border: 1px solid #22d3ee; border-radius: 10px; padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; }
.ib-read-btn:hover:not(:disabled) { background: #155e75; }
.ib-read-btn:disabled { opacity: 0.5; cursor: default; }
.ib-read-tag { color: #34d399; font-size: 12px; font-weight: 700; }
.ib-note { margin-top: 18px; color: #6b7280; font-size: 11px; line-height: 1.5; }
.ib-tab { display: flex; align-items: center; gap: 5px; background: rgba(255,255,255,0.04); color: #8891aa; border: 1px solid rgba(255,255,255,0.09); border-radius: 9px; padding: 6px 12px; font-size: 12px; font-weight: 700; font-family: inherit; cursor: pointer; }
.ib-tab:hover { color: #e7e9f3; border-color: rgba(103,232,249,0.35); }
.ib-tab.on { color: #e7e9f3; background: rgba(103,232,249,0.12); border-color: rgba(103,232,249,0.5); }
.ib-tab-n { color: #6b7280; font-size: 11px; font-weight: 600; }
.ib-tab.on .ib-tab-n { color: #67e8f9; }
`

// CEO 인박스 뷰 — 중앙 허브(DEEP.INC) 클릭 시 **상세 모달 안**에 렌더된다
// (그래프 노드·PortRegistry 와 같은 모달 = 같은 이디엄, 뒤에 그래프가 남는다).
// CEO↔CTO 양방향 대화 조회. CEO 수신 메시지만 '당김'
// (read 도장 + CEO Orca terminal 주입)을 제공한다.
// 목록 ↔ 본문은 이 모달 하나 안에서 교체한다 — 모달 위에 모달을 쌓지 않는다.
function CeoInboxView() {
  const [msgs, setMsgs] = useState(null)   // CEO↔CTO 양방향 대화
  const [sys, setSys] = useState(null)     // harnessd 발신 시스템 알림
  const [tab, setTab] = useState('cto')    // 'cto' | 'system'
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(null)   // 열린 메시지 — 목록 자리에 본문을 교체 렌더
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await apiGet('/api/inbox')
        if (!r.ok) throw new Error('HTTP ' + r.status)
        const d = await r.json()
        if (!alive) return
        setMsgs(d.messages || []); setSys(d.system || []); setErr('')
      } catch (e) { if (alive) setErr(String(e)) }
    }
    load()
    const t = setInterval(load, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  // 본문 열린 상태에서 Esc = 목록으로 (모달 자체는 backdrop/✕ 로 닫는다)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setOpen(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  // 두 갈래 = CEO 대화 vs harnessd 발신 시스템 알림.
  // 시스템 알림 본문이 `[system] cto:<name> ...` 로 시작해 CTO 발신처럼 읽히므로 섹션을 나눈다.
  const loading = msgs === null || sys === null
  const list = (tab === 'cto' ? msgs : sys) || []
  const unread = list.filter((m) => !m.read).length
  const ctoUnread = (msgs || []).filter((m) => !m.read).length
  const sysUnread = (sys || []).filter((m) => !m.read).length
  const setList = (fn) => (tab === 'cto' ? setMsgs(fn) : setSys(fn))
  const direction = (m) => m.to ? `${m.from} → ${m.to}` : m.from
  // '당김' — /inbox 처럼: read 도장 + CEO 세션에 주입(CEO 가 그 메시지에 반응). 성공 시 로컬 갱신.
  const markRead = async (id) => {
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    try {
      const r = await fetch(`/api/inbox/${id}/pull`, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
      if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰 틀림 — 재입력'); return }
      if (r.status === 503) { alert('서버 DASH_TOKEN 미설정'); return }
      if (!r.ok) { alert('실패 ' + r.status); return }
      const b = await r.json().catch(() => null)
      setList((ms) => (ms || []).map((m) => (m.id === id ? { ...m, read: true } : m)))
      setOpen((o) => (o && o.id === id ? { ...o, read: true } : o))
      if (b && b.injected === false) alert('CEO 세션이 없어 read 만 처리됨 (반응 전달 안 됨)')
    } catch (e) { alert('네트워크 오류: ' + e) }
  }
  // 삭제 — 그 메시지 행 제거(비가역). confirm 게이트.
  const deleteMsg = async (id) => {
    if (!window.confirm(`메시지 #${id} 삭제? (복구 불가)`)) return
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    try {
      const r = await fetch(`/api/inbox/${id}/delete`, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
      if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰 틀림 — 재입력'); return }
      if (r.status === 503) { alert('서버 DASH_TOKEN 미설정'); return }
      if (!r.ok) { alert('실패 ' + r.status); return }
      setList((ms) => (ms || []).filter((m) => m.id !== id))
      setOpen(null)
    } catch (e) { alert('네트워크 오류: ' + e) }
  }
  // 전체 삭제 — 지금 보고 있는 섹션만 비운다(비가역). 건수 명시 confirm.
  // 시스템 알림 쪽은 데몬이 살아있는 CTO 세션분 '새 CTO 감지됨' 을 다시 넣으므로 미리 알린다.
  const clearAll = async () => {
    const isSys = tab === 'system'
    const label = isSys ? '시스템 알림' : 'CEO↔CTO 대화'
    if (!window.confirm(`전체 삭제 — ${label} ${list.length}건 전부 제거? (복구 불가)`)) return
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    try {
      const url = isSys ? '/api/inbox/system/clear' : '/api/inbox/clear'
      const r = await fetch(url, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
      if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰 틀림 — 재입력'); return }
      if (r.status === 503) { alert('서버 DASH_TOKEN 미설정'); return }
      if (!r.ok) { alert('실패 ' + r.status); return }
      setList([]); setOpen(null)
    } catch (e) { alert('네트워크 오류: ' + e) }
  }
  return (
    <div style={S.field}>
      <style>{ibCss}</style>
      <style>{piCss}</style>
      {open ? (
        <>
          <div className="pi-sub">
            <button className="pi-back" onClick={() => setOpen(null)}>← 목록</button>
            <span className="ib-modal-from">{direction(open)}</span>
            <span className="ib-modal-meta">#{open.id} · {fmtTime(open.created)}{open.read ? '' : ' · ● unread'}</span>
          </div>
          <div className="pi-body">{open.body}</div>
          <div className="pi-foot" style={{ justifyContent: 'space-between' }}>
            <button className="ib-del-btn" onClick={() => deleteMsg(open.id)}>🗑 삭제</button>
            {open.to === 'ceo' && <button className="ib-read-btn" disabled={open.read} onClick={() => markRead(open.id)}>{open.read ? '✓ 당김됨' : 'inbox'}</button>}
          </div>
        </>
      ) : (
        <>
          <div className="pi-sub">
            <button className={'ib-tab' + (tab === 'cto' ? ' on' : '')} onClick={() => { setTab('cto'); setOpen(null) }}>
              CEO↔CTO 대화 <span className="ib-tab-n">{(msgs || []).length}</span>{ctoUnread > 0 && <span className="ib-dot" style={{ marginLeft: 6 }} />}
            </button>
            <button className={'ib-tab' + (tab === 'system' ? ' on' : '')} onClick={() => { setTab('system'); setOpen(null) }}>
              시스템 알림 <span className="ib-tab-n">{(sys || []).length}</span>{sysUnread > 0 && <span className="ib-dot" style={{ marginLeft: 6 }} />}
            </button>
            <span className="pi-count" style={{ marginLeft: 10 }}>{unread} unread · {list.length} total</span>
            <button className="ib-clear-btn" style={{ marginLeft: 'auto' }} onClick={clearAll} disabled={list.length === 0}>
              🗑 {tab === 'system' ? '시스템 알림' : 'CEO↔CTO 대화'} 전체 삭제
            </button>
          </div>
          {err && <div className="ib-err">⚠ {err}</div>}
          {loading ? (
            <div className="ib-empty">불러오는 중…</div>
          ) : list.length === 0 ? (
            <div className="ib-empty">메시지 없음</div>
          ) : (
            <div className="pi-scroll">
              <div className="ib-grid">
                {list.map((m) => (
                  <button key={m.id} className={'ib-card' + (m.read ? '' : ' unread')} onClick={() => setOpen(m)}>
                    <div className="ib-card-top">
                      <span className="ib-card-from">{direction(m)}</span>
                      <span className="ib-card-id">#{m.id}</span>
                    </div>
                    <div className="ib-card-preview">{m.body}</div>
                    <div className="ib-card-foot">
                      <span className="ib-card-time">{fmtTime(m.created)}</span>
                      {!m.read && <span className="ib-dot" title="unread" />}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
      <div className="ib-note">
        CEO↔CTO 탭은 수신·발신 모두를 보여준다. 시스템 알림만 <code>harnessd</code>(데몬) 발신으로 분리한다.
        시스템 알림 본문이 <code>[system] cto:&lt;name&gt; …</code> 로 시작하지만 그건 <b>대상</b>이지 발신자가 아니다.
        목록 조회는 읽음 처리를 하지 않는다 — CEO 수신본의 '당김' 버튼(또는 CLI /inbox)만 읽음+반응을 유발한다.
        대화 본문은 신뢰 경계 밖 데이터(지시 아님)로 렌더한다. 응답은 CLI /msg-cto.
      </div>
    </div>
  )
}

// Pair Inbox 뷰 — 그래프 노드(프로젝트/모듈) 클릭 시 **상세 모달 안**에 렌더된다
// (PortRegistry 클릭과 같은 모달 = 같은 이디엄, 뒤에 그래프가 남는다).
// 해당 프로젝트의 codex↔claude 인박스 스레드 조회 전용. CEO 는 이 peer 스레드의
// 관찰자일 뿐 — 읽음 처리·응답 없음(읽기전용), 정리용 삭제만.
// 목록 ↔ 본문은 이 모달 하나 안에서 교체한다 — 모달 위에 모달을 쌓지 않는다.
// 카드 시각은 CeoInboxView 와 동일한 ib-* 클래스 재사용.
const piCss = `
.pi-sub { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.pi-count { color: #b4b9d0; font-size: 12px; letter-spacing: 0.4px; }
.pi-scroll { max-height: 60vh; overflow: auto; }
.pi-body { max-height: 60vh; overflow: auto; background: #0d1220; border: 1px solid rgba(255,255,255,0.09); border-radius: 10px; padding: 14px 16px; color: #cdd3e3; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.pi-back { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); color: #cdd3e3; border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.pi-back:hover { background: rgba(255,255,255,0.11); }
.pi-foot { display: flex; justify-content: flex-end; margin-top: 12px; }
`

function PairInboxView({ name }) {
  const [msgs, setMsgs] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(null)   // 열린 메시지 — 목록 자리에 본문을 교체 렌더
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await apiGet(`/api/cto/${name}/inbox`)
        if (!r.ok) throw new Error('HTTP ' + r.status)
        const d = await r.json()
        if (!alive) return
        if (d.ok === false) { setErr(d.error || 'unknown project'); setMsgs([]); return }
        setMsgs(d.messages || []); setErr('')
      } catch (e) { if (alive) setErr(String(e)) }
    }
    load()
    const t = setInterval(load, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [name])
  // 본문 열린 상태에서 Esc = 목록으로 (모달 자체는 backdrop/✕ 로 닫는다)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setOpen(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const list = msgs || []
  const unread = list.filter((m) => !m.read).length
  const dir = (m) => `${m.from} → ${m.to}`
  // 삭제 — 그 peer 메시지 행 제거(비가역). confirm 게이트. 백엔드가 쌍 스코프로 재검증.
  const deleteMsg = async (id) => {
    if (!window.confirm(`메시지 #${id} 삭제? (복구 불가)`)) return
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    try {
      const r = await fetch(`/api/cto/${name}/inbox/${id}/delete`, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
      if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰 틀림 — 재입력'); return }
      if (r.status === 503) { alert('서버 DASH_TOKEN 미설정'); return }
      if (!r.ok) { alert('실패 ' + r.status); return }
      setMsgs((ms) => (ms || []).filter((m) => m.id !== id))
      setOpen(null)
    } catch (e) { alert('네트워크 오류: ' + e) }
  }
  // 전체 삭제 — 이 쌍의 codex↔claude 메시지 전부 제거(비가역). 건수 명시 confirm.
  const clearAll = async () => {
    if (!window.confirm(`전체 삭제 — codex↔claude 메시지 ${list.length}건 전부 제거? (복구 불가)`)) return
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    try {
      const r = await fetch(`/api/cto/${name}/inbox/clear`, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
      if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰 틀림 — 재입력'); return }
      if (r.status === 503) { alert('서버 DASH_TOKEN 미설정'); return }
      if (!r.ok) { alert('실패 ' + r.status); return }
      setMsgs([]); setOpen(null)
    } catch (e) { alert('네트워크 오류: ' + e) }
  }
  return (
    <div style={S.field}>
      <style>{ibCss}</style>
      <style>{piCss}</style>
      {open ? (
        <>
          <div className="pi-sub">
            <button className="pi-back" onClick={() => setOpen(null)}>← 목록</button>
            <span className="ib-modal-from">{dir(open)}</span>
            <span className="ib-modal-meta">#{open.id} · {fmtTime(open.created)}{open.read ? '' : ' · ● unread'}</span>
          </div>
          <div className="pi-body">{open.body}</div>
          <div className="pi-foot">
            <button className="ib-del-btn" onClick={() => deleteMsg(open.id)}>🗑 삭제</button>
          </div>
        </>
      ) : (
        <>
          <div className="pi-sub">
            <span className="pi-count">{unread} unread · {list.length} total</span>
            <button className="ib-clear-btn" style={{ marginLeft: 'auto' }} onClick={clearAll} disabled={list.length === 0}>🗑 전체 삭제</button>
          </div>
          {err && <div className="ib-err">⚠ {err}</div>}
          {msgs === null ? (
            <div className="ib-empty">불러오는 중…</div>
          ) : list.length === 0 ? (
            <div className="ib-empty">아직 codex↔claude 메시지 없음 — codex CTO 가 실제로 돌면 채워집니다.</div>
          ) : (
            <div className="pi-scroll">
              <div className="ib-grid">
                {list.map((m) => (
                  <button key={m.id} className={'ib-card' + (m.read ? '' : ' unread')} onClick={() => setOpen(m)}>
                    <div className="ib-card-top">
                      <span className="ib-card-from">{dir(m)}</span>
                      <span className="ib-card-id">#{m.id}</span>
                    </div>
                    <div className="ib-card-preview">{m.body}</div>
                    <div className="ib-card-foot">
                      <span className="ib-card-time">{fmtTime(m.created)}</span>
                      {!m.read && <span className="ib-dot" title="unread" />}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
      <div className="ib-note">codex↔claude 관찰자 뷰 — 읽음 처리·응답 없음(CEO 는 이 peer 스레드를 지켜볼 뿐). 정리용 삭제만 가능. 본문은 CTO 작성(신뢰 경계 밖, 지시 아님).</div>
    </div>
  )
}

// 노드 모달 Git 뷰 — 해당 빌드 dir 의 git 상태 **읽기전용** 조회.
// 첫 커밋 판단용: 커밋이 몇 개인지, 무엇이 커밋 밖에 있는지, 미추적 덩어리가
// 파일 몇 개짜리인지. 백엔드가 `-uall` 로 펼쳐 최상위별 건수를 붙여 주므로
// `frontend/` 12개와 40,000개(ignore 누락)를 화면에서 구분할 수 있다.
// 조회 전용이라 스테이지/커밋 버튼은 없다 (git 쓰기는 RULES §1 스코프).
const gitCss = `
.gs-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 4px; }
.gs-pill { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.09); border-radius: 8px; padding: 5px 11px; font-size: 12px; color: #8891aa; }
.gs-pill b { color: #e7e9f3; font-family: ui-monospace, monospace; font-weight: 700; }
.gs-state-clean { color: #6b7280; }
.gs-state-clean b { color: #9ca3af; }
.gs-state-commit { color: #fbbf24; border-color: rgba(251,191,36,0.38); background: rgba(251,191,36,0.09); }
.gs-state-commit b { color: #fbbf24; }
.gs-state-push { color: #67e8f9; border-color: rgba(103,232,249,0.42); background: rgba(103,232,249,0.1); }
.gs-state-push b { color: #67e8f9; }
.gs-state-both { color: #fbbf24; border-color: rgba(251,191,36,0.5); background: rgba(251,191,36,0.13); }
.gs-state-both b { color: #fbbf24; }
.gs-btn { background: rgba(103,232,249,0.1); border: 1px solid rgba(103,232,249,0.42); color: #a5f3fc; border-radius: 8px; padding: 5px 14px; font-size: 12px; font-weight: 700; font-family: inherit; cursor: pointer; }
.gs-btn:hover:not(:disabled) { background: rgba(103,232,249,0.2); color: #e7e9f3; }
.gs-btn:disabled { opacity: 0.4; cursor: default; }
.gs-commit { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.gs-input { flex: 1; min-width: 0; background: #0d1220; border: 1px solid rgba(103,232,249,0.35); border-radius: 8px; padding: 7px 12px; font-size: 13px; font-family: inherit; color: #e7e9f3; }
.gs-input:focus { outline: none; border-color: rgba(103,232,249,0.7); }
.gs-push { margin-top: 10px; padding: 12px 14px; background: #0d1220; border: 1px solid rgba(251,191,36,0.35); border-radius: 10px; }
.gs-push-row { display: flex; gap: 12px; font-size: 12.5px; margin-bottom: 6px; }
.gs-push-k { color: #8891aa; flex: none; width: 56px; }
.gs-push-v { color: #e7e9f3; font-family: ui-monospace, monospace; word-break: break-all; }
.gs-cancel { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); color: #cdd3e3; border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 700; font-family: inherit; cursor: pointer; }
.gs-warn { color: #fbbf24; border-color: rgba(251,191,36,0.38); background: rgba(251,191,36,0.09); }
.gs-warn b { color: #fbbf24; }
.gs-sec { margin-top: 16px; }
.gs-h { color: #8891aa; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; font-weight: 600; margin-bottom: 7px; }
.gs-list { max-height: 28vh; overflow: auto; background: #0d1220; border: 1px solid rgba(255,255,255,0.09); border-radius: 10px; }
.gs-row { display: flex; align-items: center; gap: 10px; padding: 7px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: ui-monospace, monospace; font-size: 12px; }
.gs-row:last-child { border-bottom: none; }
.gs-code { color: #f59e0b; width: 22px; flex: none; white-space: pre; }
.gs-path { color: #cdd3e3; word-break: break-all; }
.gs-n { margin-left: auto; color: #6b7280; font-size: 11px; flex: none; white-space: nowrap; }
/* 버튼(gs-move)이 앞에 있는 행: auto 마진은 버튼 하나만 갖는다 — 둘 다 auto 면
   flexbox 가 남는 공간을 분배해 카운트가 중간에 뜬다 (올라감/안올라감 끝 정렬 불일치 원인). */
.gs-move + .gs-n { margin-left: 0; }
/* 커밋 필요(dirty) 마커 — status --porcelain 에 잡히는 파일, 또는 그런 파일을 품은 폴더 */
.gs-dot { color: #fbbf24; font-size: 8px; margin-left: 6px; vertical-align: 2px; }
.gs-sub { color: #67e8f9; }
.gs-dim { color: #6b7280; }
.gs-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
@media (max-width: 820px) { .gs-cols { grid-template-columns: 1fr; } }
.gs-col { min-width: 0; }
.gs-h-ok { color: #34d399; }
.gs-h-off { color: #94a3b8; }
.gs-h-st { color: #a5f3fc; }
.gs-h-cm { color: #34d399; }
.gs-row-click { cursor: pointer; }
.gs-row-click:hover { background: rgba(255,255,255,0.04); }
.gs-row-click.on { background: rgba(103,232,249,0.09); }
.gs-row-sub { padding-left: 26px; font-size: 11.5px; }
.gs-st { flex: none; width: 14px; font-weight: 700; }
.gs-st-A { color: #34d399; }
.gs-st-M { color: #fbbf24; }
.gs-st-D { color: #f87171; }
.gs-add { color: #34d399; }
.gs-del { color: #f87171; }
.gs-list-st { max-height: 22vh; }
.gs-list { max-height: 46vh; }
.gs-off-t { color: #94a3b8; }
.gs-move { margin-left: auto; flex: none; visibility: hidden; background: rgba(148,163,184,0.12); border: 1px solid rgba(148,163,184,0.3); color: #cbd5e1; border-radius: 7px; padding: 2px 9px; font-size: 12px; font-family: inherit; cursor: pointer; }
.gs-row:hover .gs-move { visibility: visible; }
.gs-move:hover { background: rgba(148,163,184,0.25); color: #f1f5f9; }
.gs-move:disabled { opacity: 0.45; cursor: default; }
.gs-row:hover .gs-n { color: #94a3b8; }
.gs-msg { margin-top: 8px; font-size: 11.5px; color: #94a3b8; }
.gs-msg.err { color: #fecaca; }
`

// base = API 접두 (`/api/cto/<name>` 또는 `/api/harness`). 빌드 dir 과 하네스
// 루트가 같은 화면을 쓰되 경로만 갈린다.
function GitStatusView({ base }) {
  const [g, setG] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState(null)   // 마지막 제외 결과 (한 줄 피드백)
  const [busy, setBusy] = useState('')   // 진행 중인 항목 경로 — 중복 클릭 방지
  const [commitOpen, setCommitOpen] = useState(false)  // 메시지 입력창 열림
  const [commitMsg, setCommitMsg] = useState('')
  const [remoteOpen, setRemoteOpen] = useState(false)  // 주소 입력창 열림
  const [remoteUrl, setRemoteUrl] = useState('')
  const [pushOpen, setPushOpen] = useState(false)      // push 확인 패널 열림
  const [openSha, setOpenSha] = useState(null)         // 펼친 커밋 해시
  const [detail, setDetail] = useState(null)           // 그 커밋의 변경 파일 목록
  const load = useCallback(async () => {
    try {
      const r = await apiGet(`${base}/git`)
      if (!r.ok) throw new Error('HTTP ' + r.status)
      const d = await r.json()
      if (d.ok === false) { setErr(d.error || 'unknown project'); setG(null); return }
      setG(d); setErr('')
    } catch (e) { setErr(String(e)) }
  }, [base])
  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  // stage — 인덱스에만 쓴다(`git add -A`). 첫 커밋일 때만 활성: 그때는 추적 파일이
  // 0이라 `-A` 가 왼쪽 "올라감" 목록과 정확히 같다.
  const stage = async () => {
    setBusy('__stage'); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/stage`, {
        method: 'POST', headers: t ? { 'X-Dash-Token': t } : {},
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      else {
        // 종류를 다 적는다 — `-A` 는 화면 왼쪽에 없는 **삭제**도 stage 하므로
        // 총계만 보여주면 그 부분이 조용히 들어간다.
        setMsg({ err: false, text: `git add -A — 총 ${d.staged} (신규 ${d.added} · 수정 ${d.modified}`
          + ` · 삭제 ${d.deleted}${d.other ? ` · 기타 ${d.other}` : ''})` })
        await load()
      }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  // unstage — stage 버튼의 되돌리기(`git reset`). **작업트리는 안 건드린다** —
  // 인덱스만 HEAD 로 되돌리므로 잘못 눌러도 잃을 파일이 없다. 그래서 commit·push 와
  // 달리 확인창 없이 1클릭이다. `-A` 로 원치 않는 경로가 섞여 들어갔을 때의 출구.
  const unstage = async () => {
    setBusy('__unstage'); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/unstage`, {
        method: 'POST', headers: t ? { 'X-Dash-Token': t } : {},
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      else {
        setMsg({ err: false, text: `stage 취소 — ${d.unstaged} 파일을 인덱스에서 내렸다`
          + ` (작업트리 무변경${d.remaining ? ` · 남은 stage ${d.remaining}` : ''})` })
        await load()
      }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  // commit — 메시지 입력이 끝나야만 실행된다. 버튼 1클릭 = 입력창 열기일 뿐이고,
  // 실제 `git commit -m` 은 사용자가 메시지를 넣고 확정했을 때만 나간다.
  const commit = async () => {
    const msg = commitMsg.trim()
    if (!msg) return
    setBusy('__commit'); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(t ? { 'X-Dash-Token': t } : {}) },
        body: JSON.stringify({ message: msg }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      else {
        setMsg({ err: false, text: `커밋 ${d.hash} — ${d.files} 파일` })
        setCommitOpen(false); setCommitMsg(''); await load()
      }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  // 커밋 상세 — 라우트가 `/show/` 인 이유는 `/commit/` 이면 git_guard 의 §1 우회
  // 차단 패턴이 이 **읽기 요청까지** 막기 때문이다.
  const loadDetail = async (sha) => {
    setOpenSha(sha); setDetail(null)
    if (!sha) return
    try {
      const r = await apiGet(`${base}/show/${sha}`)
      const d = await r.json()
      setDetail(d.ok === false ? { error: d.error } : d)
    } catch (e) { setDetail({ error: String(e) }) }
  }

  // push — 유일하게 **밖으로 나가는** 동작이라 입력 대신 확인 패널을 거친다.
  // 목적지(origin)와 보낼 커밋 수를 눌러서 보게 하는 게 목적: remote 가 바뀌어
  // 있으면 여기서 눈에 걸린다.
  const push = async () => {
    setBusy('__push'); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/push`, {
        method: 'POST', headers: t ? { 'X-Dash-Token': t } : {},
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      else { setMsg({ err: false, text: `${d.cmd} — 완료` }); setPushOpen(false); await load() }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  // remote — 로컬 설정만 바꾼다(전송 없음). 입력이 끝나야 실행된다.
  const setRemote = async () => {
    const u = remoteUrl.trim()
    if (!u) return
    setBusy('__remote'); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/remote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(t ? { 'X-Dash-Token': t } : {}) },
        body: JSON.stringify({ url: u }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      else {
        setMsg({ err: false, text: `origin ${d.replaced ? '변경' : '등록'} — ${d.url}` })
        setRemoteOpen(false); await load()
      }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  // 올라감 → 안 올라감. `.gitignore` 에 한 줄 붙일 뿐이라 커밋/인덱스는 안 건드린다.
  // 되돌리기는 그 줄 삭제 = 사용자가 파일에서 직접. 그래서 추가된 줄을 그대로 보여준다.
  const exclude = async (path) => {
    setBusy(path); setMsg(null)
    try {
      const t = localStorage.getItem('dashToken') || ''
      const r = await fetch(`${base}/gitignore/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(t ? { 'X-Dash-Token': t } : {}) },
        body: JSON.stringify({ path }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) {
        setMsg({ err: true, text: d.error || `HTTP ${r.status}` })
      } else {
        setMsg({ err: false, text: `.gitignore 에 ${d.added} 추가${d.already ? ' (이미 있음)' : ''}`
          + (d.removed_cached ? ` — 추적 중이던 ${d.removed_cached}개 파일 rm --cached (디스크 유지, 다음 커밋에서 저장소를 떠남)` : '') })
        await load()
      }
    } catch (e) { setMsg({ err: true, text: String(e) }) }
    setBusy('')
  }

  if (err) return <div style={S.field}><style>{ibCss}</style><div className="ib-err">⚠ {err}</div></div>
  if (g === null) return <div style={S.field}><style>{ibCss}</style><div className="ib-empty">불러오는 중…</div></div>
  if (!g.is_repo) {
    return (
      <div style={S.field}>
        <style>{ibCss}</style>
        <div className="ib-empty">git 저장소 아님 — <code>{g.path}</code> 에 <code>.git</code> 없음</div>
      </div>
    )
  }
  return (
    <div style={S.field}>
      <style>{ibCss}</style>
      <style>{gitCss}</style>
      <div className="gs-top">
        <span className="gs-pill">branch <b>{g.branch}</b></span>
        {/* 상태 = 독립된 두 축의 조합. dirty(커밋할 것) 와 ahead(push 할 것) 는
            따로 논다 — 고치기만 하고 커밋 안 하면 dirty>0·ahead=0 이라 push 는
            보낼 게 없다. 하나짜리 "업로드 가능/불가" 로는 그 구분이 사라진다. */}
        <span className={'gs-pill gs-state gs-state-' + g.state}>
          {g.state === 'clean' ? '● 동기화됨'
            : g.state === 'commit' ? <>● 커밋 필요 <b>{g.dirty}</b></>
            : g.state === 'push' ? <>● push 필요 <b>{g.ahead}</b></>
            : <>● 커밋 <b>{g.dirty}</b> · push <b>{g.ahead}</b></>}
        </span>
        <button className="gs-btn" onClick={stage} disabled={busy === '__stage'}
                title="git add -A — 신규·수정·삭제 전부 인덱스에 올린다 (커밋 안 함)">
          stage
        </button>
        {/* stage 의 짝 — 있어야 `-A` 로 섞여 들어간 경로를 화면에서 되돌릴 수 있다.
            stage 된 게 있을 때만 켠다(끌 게 없으면 누를 이유도 없다). */}
        <button className="gs-btn" onClick={unstage}
                disabled={g.staged.total === 0 || busy === '__unstage'}
                title={g.staged.total === 0
                  ? 'stage 된 파일이 없다'
                  : `git reset — stage 된 ${g.staged.total} 파일을 인덱스에서 내린다.`
                    + ' 작업트리는 그대로다 (파일이 지워지거나 바뀌지 않는다).'}>
          {busy === '__unstage' ? '취소 중…' : 'stage 취소'}
        </button>
        <button className="gs-btn" onClick={() => setCommitOpen((v) => !v)}
                disabled={g.staged.total === 0}
                title={g.staged.total === 0
                  ? (g.commits > 0
                    ? `커밋 ${g.commits}개 — stage 된 파일이 없다`
                    : 'stage 된 파일이 없다 — 먼저 stage')
                  : `git commit — 메시지를 넣어야 실행된다 (${g.staged.total} 파일)`}>
          {/* ✓ = 이 repo 에 커밋이 존재한다(=첫 커밋 완료). remote ✓ 와 같은 "설정됨"
              표시라 한 번 켜지면 안 꺼진다 — 밀린 작업량은 stage 카운트가 담당. */}
          commit{g.commits > 0 ? ' ✓' : ''}
        </button>
        <button className="gs-btn"
                onClick={() => { setRemoteUrl(g.remote_url || ''); setRemoteOpen((v) => !v) }}
                title={g.remote_url ? `origin: ${g.remote_url}` : 'origin 원격 주소 등록'}>
          remote{g.remote_url ? ' ✓' : ''}
        </button>
        <button className="gs-btn" onClick={() => setPushOpen((v) => !v)}
                disabled={!g.remote_url || g.ahead === 0}
                title={!g.remote_url ? 'origin 이 없다 — remote 먼저'
                  : g.ahead === 0 ? '보낼 커밋이 없다 (origin 과 동일)'
                  : `${g.ahead} 커밋을 origin 으로 — 확인 후 실행`}>
          {/* ✓ = upstream 이 잡혀 있다(= 한 번은 push 됨). (N) = 아직 안 보낸 커밋 수.
              둘은 별개라 `push ✓ (2)`(보낸 적 있고 2개 밀림)도 정상 표시다. */}
          push{g.upstream ? ' ✓' : ''}{g.remote_url && g.ahead > 0 ? ` (${g.ahead})` : ''}
        </button>
      </div>
      {pushOpen && (
        <div className="gs-push">
          <div className="gs-push-row">
            <span className="gs-push-k">목적지</span>
            <span className="gs-push-v">{g.remote_url}</span>
          </div>
          <div className="gs-push-row">
            <span className="gs-push-k">보낼 것</span>
            <span className="gs-push-v">{g.branch} · {g.ahead} 커밋
              {g.upstream ? ` → ${g.upstream}` : '  (upstream 없음 — -u 로 추적 설정)'}</span>
          </div>
          <div className="gs-commit" style={{ marginTop: 4 }}>
            <button className="gs-btn" onClick={push} disabled={busy === '__push'}>
              {busy === '__push' ? 'push 중…' : 'push 실행'}
            </button>
            <button className="gs-cancel" onClick={() => setPushOpen(false)}>취소</button>
          </div>
        </div>
      )}
      {remoteOpen && (
        <div className="gs-commit">
          <input className="gs-input" autoFocus value={remoteUrl}
                 placeholder="https://github.com/<user>/<repo> 또는 git@host:user/repo.git"
                 onChange={(e) => setRemoteUrl(e.target.value)}
                 onKeyDown={(e) => {
                   if (e.key === 'Enter') setRemote()
                   if (e.key === 'Escape') setRemoteOpen(false)
                 }} />
          <button className="gs-btn" onClick={setRemote}
                  disabled={!remoteUrl.trim() || busy === '__remote'}>
            {busy === '__remote' ? '설정 중…' : (g.remote_url ? 'origin 변경' : 'origin 등록')}
          </button>
          <button className="gs-cancel" onClick={() => setRemoteOpen(false)}>취소</button>
        </div>
      )}
      {commitOpen && (
        <div className="gs-commit">
          <input className="gs-input" autoFocus value={commitMsg} placeholder="커밋 메시지"
                 onChange={(e) => setCommitMsg(e.target.value)}
                 onKeyDown={(e) => {
                   if (e.key === 'Enter') commit()
                   if (e.key === 'Escape') { setCommitOpen(false); setCommitMsg('') }
                 }} />
          <button className="gs-btn" onClick={commit}
                  disabled={!commitMsg.trim() || busy === '__commit'}>
            {busy === '__commit' ? '커밋 중…' : `커밋 (${g.staged.total} 파일)`}
          </button>
          <button className="gs-cancel" onClick={() => { setCommitOpen(false); setCommitMsg('') }}>취소</button>
        </div>
      )}
      {g.truncated && (
        <div className="gs-sec"><span className="gs-pill gs-warn">⚠ 항목이 상한을 넘어 잘림 — .gitignore 누락 가능성</span></div>
      )}

      <div className="gs-cols">
        <div className="gs-col">
          <div className="gs-h gs-h-ok">✅ 올라감 · {g.upload.total} 파일{g.upload.tracked > 0 ? ` (추적 중 ${g.upload.tracked})` : ''}</div>
          {g.upload.total === 0 ? (
            <div className="gs-pill gs-dim">없음</div>
          ) : (
            <div className="gs-list">
              {g.upload.dirs.map((u, i) => (
                <div className="gs-row" key={'d' + i}>
                  <span className="gs-path gs-sub">{u.path}
                    {g.upload.dirty?.includes(u.path.replace(/\/$/, '')) &&
                      <span className="gs-dot" title="커밋 필요한 변경이 안에 있다">●</span>}
                  </span>
                  <button className="gs-move" disabled={busy === u.path} title={`.gitignore 에 추가 — 안 올라감으로`}
                          onClick={() => exclude(u.path)}>→</button>
                  <span className="gs-n">{u.gitkeep_only ? '.gitkeep만 — 빈 폴더 유지' : `${u.files} 파일`}</span>
                </div>
              ))}
              {g.upload.files.map((f, i) => (
                <div className="gs-row" key={'f' + i}>
                  <span className="gs-path">{f}
                    {g.upload.dirty?.includes(f) &&
                      <span className="gs-dot" title="커밋 필요한 변경">●</span>}
                  </span>
                  <button className="gs-move" disabled={busy === f || f === '.gitignore'}
                          title={f === '.gitignore' ? '규칙 파일 자체는 제외 불가' : '.gitignore 에 추가 — 안 올라감으로'}
                          onClick={() => exclude(f)}>→</button>
                </div>
              ))}
            </div>
          )}
          {msg && <div className={'gs-msg' + (msg.err ? ' err' : '')}>{msg.err ? '⚠ ' : '✓ '}{msg.text}</div>}
        </div>

        <div className="gs-col">
          <div className="gs-h gs-h-off">🚫 안 올라감 · {g.ignored.total} 파일 ({g.ignored.entries.length} 항목)</div>
          {g.ignored.entries.length === 0 ? (
            <div className="gs-pill gs-dim">없음 — .gitignore 가 아무것도 안 거른다</div>
          ) : (
            <div className="gs-list">
              {g.ignored.entries.map((e, i) => (
                <div className="gs-row" key={i}>
                  <span className={'gs-path' + (e.path.endsWith('/') ? ' gs-off-t' : '')}>{e.path}</span>
                  <span className="gs-n">{e.files} 파일</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 위 올라감/안올라감과 같은 2열 — 왼쪽 인덱스, 오른쪽 마지막 커밋.
          두 목록이 같은 모양이라 "stage 한 게 그대로 커밋됐나" 를 눈으로 대조한다. */}
      <div className="gs-cols">
        <div className="gs-col">
          {/* 삭제분은 왼쪽 "올라감"(디스크 실존분)에 없다 — 헤더에 별도 표기해
              화면과 인덱스가 어긋난 부분을 드러낸다. */}
          {/* stage 안 된 것도 같이 적는다 — 예전엔 `stage 됨 N` 만 보여서
              "인덱스에 넣은 뒤 또 고친 것"과 "새 파일"이 화면 어디에도 없었다. */}
          <div className="gs-h gs-h-st">
            📦 stage 됨 · {g.staged.total} 파일
            {g.staged.deleted > 0 ? ` · 삭제 ${g.staged.deleted} 포함` : ''}
            {g.unstaged + g.untracked > 0
              ? ` · stage 안 됨: 수정 ${g.unstaged} · 새 파일 ${g.untracked}`
              : ''}
          </div>
          {g.staged.total === 0 ? (
            <div className="gs-pill gs-dim">없음 — 인덱스가 비어 있다</div>
          ) : (
            <div className="gs-list gs-list-st">
              {g.staged.dirs.map((u, i) => (
                <div className="gs-row" key={'sd' + i}>
                  <span className="gs-path gs-sub">{u.path}</span>
                  <span className="gs-n">{u.files} 파일</span>
                </div>
              ))}
              {g.staged.files.map((f, i) => (
                <div className="gs-row" key={'sf' + i}><span className="gs-path">{f}</span></div>
              ))}
            </div>
          )}
        </div>

        <div className="gs-col">
          <div className="gs-h gs-h-cm">
            ✅ commit 됨 · {g.committed.total} 파일
            {g.committed.hash ? ` · ${g.committed.hash} ${g.committed.subject}` : ''}
          </div>
          {g.committed.total === 0 ? (
            <div className="gs-pill gs-dim">없음 — 아직 커밋 전</div>
          ) : (
            <div className="gs-list gs-list-st">
              {g.committed.dirs.map((u, i) => (
                <div className="gs-row" key={'cd' + i}>
                  <span className="gs-path gs-sub">{u.path}</span>
                  <span className="gs-n">{u.files} 파일</span>
                </div>
              ))}
              {g.committed.files.map((f, i) => (
                <div className="gs-row" key={'cf' + i}><span className="gs-path">{f}</span></div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="gs-cols">
        <div className="gs-col">
          <div className="gs-h">최근 커밋{detail ? ` · ${detail.total} 파일 +${detail.add} -${detail.del}` : ''}</div>
          {g.recent.length === 0 ? (
            <div className="gs-pill gs-dim">없음</div>
          ) : (
            <div className="gs-list">
              {g.recent.map((c, i) => (
                <React.Fragment key={'rc' + i}>
                  {/* 행 클릭 = 그 커밋이 바꾼 파일 목록 토글. diff 본문은 안 가져온다
                      (커밋 하나가 수 MB 일 수 있어서) — 파일별 +/- 까지. */}
                  <div className={'gs-row gs-row-click' + (openSha === c.hash ? ' on' : '')}
                       onClick={() => loadDetail(openSha === c.hash ? null : c.hash)}>
                    <span className="gs-sub" style={{ flex: 'none' }}>{c.hash}</span>
                    <span className="gs-path">{c.subject}</span>
                    <span className="gs-n">{c.date}</span>
                  </div>
                  {openSha === c.hash && (
                    detail === null ? <div className="gs-row gs-dim">불러오는 중…</div>
                    : detail.error ? <div className="gs-row gs-dim">⚠ {detail.error}</div>
                    : detail.files.map((f, k) => (
                        <div className="gs-row gs-row-sub" key={'df' + k}>
                          <span className={'gs-st gs-st-' + f.status}>{f.status}</span>
                          <span className="gs-path">{f.path}</span>
                          <span className="gs-n">
                            <span className="gs-add">+{f.add}</span> <span className="gs-del">-{f.del}</span>
                          </span>
                        </div>
                      ))
                  )}
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
        <div className="gs-col">
          <div className="gs-h">최근 push{g.upstream ? ` · ${g.upstream}` : ''}</div>
          {g.pushed.length === 0 ? (
            <div className="gs-pill gs-dim">{g.upstream ? '기록 없음' : '아직 push 안 함'}</div>
          ) : (
            <div className="gs-list">
              {g.pushed.map((c, i) => (
                <div className="gs-row" key={'rp' + i}>
                  <span className="gs-sub" style={{ flex: 'none' }}>{c.hash}</span>
                  <span className="gs-path">{c.subject}</span>
                  <span className="gs-n">{c.date}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// 노드 모달 DB 스키마 뷰 (정적 파싱 결과 렌더)
const schemaCss = `
.sc { max-height: 340px; overflow: auto; background: #0d1220; border: 1px solid rgba(255,255,255,0.09); border-radius: 10px; padding: 12px 14px; }
.sc-t { margin-bottom: 14px; }
.sc-t:last-of-type { margin-bottom: 4px; }
.sc-tn { color: #67e8f9; font-weight: 700; font-family: ui-monospace, monospace; font-size: 13px; margin-bottom: 5px; }
.sc-tbl { width: 100%; border-collapse: collapse; font-family: ui-monospace, monospace; font-size: 12px; }
.sc-tbl th { text-align: left; color: #8891aa; font-weight: 600; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; padding: 5px 10px; border-bottom: 1px solid rgba(255,255,255,0.14); font-family: system-ui, sans-serif; white-space: nowrap; }
.sc-tbl td { padding: 10px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: top; }
.sc-tbl tr:last-child td { border-bottom: none; }
.sc-cn { color: #e7e9f3; }
.sc-ct { color: #a78bfa; }
.sc-cf { color: #f59e0b; font-size: 11px; }
.sc-m { margin-top: 10px; color: #6b7280; font-size: 11px; font-family: system-ui, sans-serif; }
`

export default function App() {
  const [data, setData] = useState({ columns: [], items: [], links: [], access_host: '', harness_dirty: 0 })
  const [err, setErr] = useState('')
  const [updated, setUpdated] = useState('')
  const [sel, setSel] = useState(null)      // 열린 모달 항목
  const [ctoStartAsk, setCtoStartAsk] = useState(null) // CTO 실행 방식 선택 팝업 대상
  const [schema, setSchema] = useState(null) // 열린 노드의 DB 스키마 (/api/schema)
  const [selMode, setSelMode] = useState('control') // 'schema'(MissionControl 카드) | 'control'(PortRegistry) | 'inbox'(그래프 노드)
  const [nodeTab, setNodeTab] = useState('git')     // 그래프 노드 모달 탭: 'git'(기본) | 'chat'(codex↔claude)
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState('')      // 진행중 액션 ('cto'|'docker')
  const [tasks, setTasks] = useState([])    // 우측상단 작업 toast
  const [hubInbox, setHubInbox] = useState(false) // 허브(DEEP.INC) 클릭 → 모달
  const [hubTab, setHubTab] = useState('git')     // 'git'(기본, 하네스 저장소) | 'inbox'
  const taskId = useRef(0)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await apiGet('/api/state')
        if (!r.ok) throw new Error('HTTP ' + r.status)
        const d = await r.json()
        if (!alive) return
        setData({ columns: d.columns || [], items: d.items || [], links: d.links || [], access_host: d.access_host || '', harness_dirty: d.harness_dirty || 0 })
        setErr('')
        setUpdated(new Date().toLocaleTimeString())
      } catch (e) {
        if (alive) setErr(String(e))
      }
    }
    load()
    const t = setInterval(load, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  // 첫 접속(로드) 때 토큰 1회 입력 → localStorage 보관. 이후 재입력 없음.
  useEffect(() => {
    if (!localStorage.getItem('dashToken')) {
      const t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''
      if (t) localStorage.setItem('dashToken', t)
    }
  }, [])

  // 노드 모달 열릴 때 그 노드 DB 스키마 fetch (노드 바뀔 때만; 정적이라 폴링 X)
  useEffect(() => {
    if (!sel || selMode !== 'schema') { setSchema(null); return }
    let alive = true
    setSchema(null)
    apiGet(`/api/schema/${sel.name}`)
      .then((r) => r.json())
      .then((d) => { if (alive) setSchema(d) })
      .catch(() => { if (alive) setSchema({ ok: false }) })
    return () => { alive = false }
  }, [sel && sel.name, selMode])

  const copy = async (text) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        // 비-https LAN(http://192.168…) = clipboard API 막힘 → 레거시 폴백
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* 무시 */ }
  }

  const { columns, items } = data
  const groups = [
    { type: 'module', label: '모듈', icon: '📦', color: '#3b82f6', tint: '#93c5fd' },
    { type: 'project', label: '프로젝트', icon: '🚀', color: '#10b981', tint: '#6ee7b7' },
  ]

  const statusBadge = (it) => {
    const map = {
      up: { bg: '#dcfce7', fg: '#15803d', t: `✅ ${it.running}/${it.declared} Up` },
      partial: { bg: '#fef9c3', fg: '#a16207', t: `⚠ ${it.running}/${it.declared}` },
      down: { bg: '#f3f4f6', fg: '#6b7280', t: `✋ 0/${it.declared}` },
      none: { bg: '#f3f4f6', fg: '#9ca3af', t: '—' },
    }
    const s = map[it.status] || map.none
    return <span style={{ ...S.badge, background: s.bg, color: s.fg }}>{s.t}</span>
  }

  const refresh = async () => {
    try {
      const r = await apiGet('/api/state'); const d = await r.json()
      setData({ columns: d.columns || [], items: d.items || [], links: d.links || [], access_host: d.access_host || '', harness_dirty: d.harness_dirty || 0 })
      setSel((s) => (s ? (d.items || []).find((it) => it.name === s.name && it.type === s.type) || s : s))
    } catch { /* keep last */ }
  }
  // mutation 토큰 (interim 보호 — 서버 DASH_TOKEN 과 일치해야). localStorage 보관, 없으면 1회 prompt.
  const dashToken = () => {
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    return t
  }
  const mutate = async (url, forceToken) => {
    const t = forceToken !== undefined ? forceToken : dashToken()
    let r
    try { r = await fetch(url, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} }) }
    catch (e) { return { ok: false, msg: '네트워크 오류: ' + e } }
    if (r.status === 401) { if (forceToken === undefined) localStorage.removeItem('dashToken'); return { ok: false, msg: '토큰 틀림 — 재입력' } }
    if (r.status === 503) { return { ok: false, msg: '서버 DASH_TOKEN 미설정' } }
    if (!r.ok) return { ok: false, msg: '서버 오류 ' + r.status }
    let body = null
    try { body = await r.json() } catch { /* non-json */ }
    if (body && body.ok === false) return { ok: false, msg: body.error || body.out || '실패' }
    return { ok: true, body }
  }
  // 우측상단 작업 toast — addTask(running 등록) → endTask(done/failed + 자동 소멸).
  const addTask = (label) => { const id = ++taskId.current; setTasks((ts) => [...ts, { id, label, status: 'running' }]); return id }
  const endTask = (id, ok, detail) => {
    setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, status: ok ? 'done' : 'failed', detail } : t)))
    setTimeout(() => setTasks((ts) => ts.filter((t) => t.id !== id)), ok ? 2500 : 7000)
  }
  // docker up 은 detached 빌드 → 컨테이너 상태가 want 될 때까지 폴링 (3s × 120 = 6분 cap).
  const waitDocker = async (name, want) => {
    for (let i = 0; i < 120; i++) {
      await new Promise((res) => setTimeout(res, 3000))
      try {
        const d = await (await apiGet('/api/state')).json()
        // 이름만으로 찾는다 — 이름은 modules/ + claude-project/ 전역에서 유일하다
        // (harness/cli.py 스캔이 `seen.add(child.name)` 로 중복을 배제). 예전엔
        // `x.type === 'project'` 조건이 붙어 있어 **모듈 5개는 영영 매칭되지 않았고**,
        // 컨테이너가 이미 떠도 toast 가 6분(3s×120)간 '진행중' 으로 남았다.
        const it = (d.items || []).find((x) => x.name === name)
        if (it && !!it.docker_up === want) return true
      } catch { /* keep polling */ }
    }
    return false
  }
  // 액션 후 쿨다운 — refresh 로 라벨이 갱신된 뒤에도 잠깐 버튼 잠금 유지해 연타/
  // confirm-OK 연타 후속 클릭을 삼킨다 (stop→'실행' 뒤집힘 직후 재클릭 부활 방지).
  const cooldown = () => new Promise((r) => setTimeout(r, 800))
  const ctoToggle = async (it) => {
    const healthy = ctoHealthy(it)
    const partial = ctoPartial(it)
    // 완전 정지 상태에서의 '실행' 은 confirm 대신 2갈래 팝업(이어서/fresh)으로.
    // 복구(반쪽 사망)는 fresh 를 권하지 않는다 — 대화 폐기가 목적이면 종료 후 실행.
    if (!healthy && !partial) { setCtoStartAsk(it); return }
    const act = healthy ? 'stop' : 'start'
    const verb = healthy ? '종료' : '복구'
    const msg = healthy
      ? `CTO pair 종료: ${it.name}?\n(작업 보존 — Claude/Codex 세션만 정지)`
      : `CTO pair 복구: ${it.name}?\n(${ctoHalfSummary(it)} · 누락 half만 다시 실행)`
    if (!window.confirm(msg)) return
    const id = addTask(`CTO ${verb}: ${it.name}`)
    setBusy(`${it.name}:cto`)
    const res = await mutate(`/api/cto/${it.name}/${act}`)
    await refresh(); endTask(id, res.ok, res.msg); await cooldown(); setBusy('')
  }
  const ctoStart = async (it, fresh) => {
    setCtoStartAsk(null)
    const id = addTask(`CTO 실행${fresh ? ' (fresh)' : ''}: ${it.name}`)
    setBusy(`${it.name}:cto`)
    const res = await mutate(`/api/cto/${it.name}/start${fresh ? '?fresh=1' : ''}`)
    await refresh(); endTask(id, res.ok, res.msg); await cooldown(); setBusy('')
  }
  const devToggle = async (it) => {
    const act = it.dev_up ? '종료' : '실행'
    if (!window.confirm(`dev 서버 ${act}: ${it.name}? (venv uvicorn + vite)`)) return
    const id = addTask(`dev 서버 ${act}: ${it.name}`)
    setBusy(`${it.name}:dev`)
    const res = await mutate(`/api/dev/${it.name}/toggle`)
    await refresh(); endTask(id, res.ok, res.msg); await cooldown(); setBusy('')
  }
  const dockerToggle = async (it) => {
    const wantUp = !it.docker_up
    const act = it.docker_up ? '종료' : '실행(빌드 — 시간 걸림)'
    if (!window.confirm(`Docker ${act}: ${it.name}?`)) return
    const id = addTask(`Docker ${wantUp ? '빌드·실행' : '종료'}: ${it.name}`)
    setBusy(`${it.name}:docker`)
    const res = await mutate(`/api/docker/${it.name}/toggle`)
    await refresh()
    if (!res.ok) { endTask(id, false, res.msg); await cooldown(); setBusy(''); return }
    if (wantUp) {
      const ok = await waitDocker(it.name, true)  // 빌드 끝까지 busy 유지 → 빌드 중 토글 차단
      endTask(id, ok, ok ? null : '빌드 지연/실패 — .dash-docker.log 확인'); await refresh()
    } else { endTask(id, true) }
    await cooldown(); setBusy('')
  }
  // 비가역 삭제 — DASH_TOKEN 재입력 게이트 (캐시 토큰 안 씀; 미승인 삭제 방지 + 프롬프트에
  // 프로젝트명 명시 → 오클릭도 방지).
  const deleteProject = async (it) => {
    const tok = window.prompt(
      `⚠ 영구 삭제 — 복구 불가.\n${it.name} (빌드 dir·sqlite·로그·세션·컨테이너 전부 제거).\n\n삭제하려면 DASH_TOKEN 을 재입력:`,
    )
    if (!tok) return
    const id = addTask(`프로젝트 삭제: ${it.name}`)
    setBusy(`${it.name}:delete`)
    const res = await mutate(`/api/cto/${it.name}/delete`, tok)
    if (res.ok) setSel(null)
    await refresh(); endTask(id, res.ok, res.msg); await cooldown(); setBusy('')
  }
  // 모두 종료 — run.sh down (CTO/harnessd/dev/docker) + stop-ceo (CEO). 대시보드는 남음.
  // 데이터 삭제 아님(세션/프로세스만, 복구가능)이라 window.confirm 로 충분 (delete 처럼
  // DASH_TOKEN 재입력까진 안 함 — 단 endpoint 는 require_token 이라 캐시 토큰은 필요).
  const shutdownAll = async () => {
    if (!window.confirm(
      '⚠ 모두 종료?\n\nCEO + 모든 CTO 세션 + harnessd + dev 서버 + docker 스택을 종료한다.\n' +
      '(대시보드는 유지 · 빌드/DB/git 은 보존 = 복구 가능)\n\n계속?'
    )) return
    const id = addTask('모두 종료 (down + stop-ceo)')
    setBusy('__shutdown_all__')
    const res = await mutate('/api/shutdown-all')
    setSel(null)
    await refresh(); endTask(id, res.ok, res.msg); await cooldown(); setBusy('')
  }
  // 모든 CTO 일괄 활성화/정지 — CTO 세션만 (CEO·dev·docker 무관, shutdownAll 과 별개).
  // 백엔드가 순차 처리 + 끝상태 검증 후 요약(out)을 돌려준다.
  const ctoAll = async (action) => {
    const msg = action === 'start'
      ? '모든 프로젝트·모듈의 CTO pair를 활성화?\n(healthy는 건너뜀 · partial은 누락 half 복구 · Claude+Codex 시작)'
      : '모든 CTO pair를 종료?\n(작업 보존 — Claude/Codex 세션만 정지 · CEO·dev·docker 는 유지)'
    if (!window.confirm(msg)) return
    const id = addTask(action === 'start' ? '모든 CTO 활성화' : '모든 CTO 종료')
    setBusy(`__cto_all_${action}__`)
    const res = await mutate(`/api/cto-all/${action}`)
    const detail = res.ok ? (res.body && res.body.out) : res.msg
    await refresh(); endTask(id, res.ok, detail); await cooldown(); setBusy('')
  }

  const selUrl = sel && safeUrl(sel.git_url)
  const selFePort = sel && sel.cells && sel.cells.FRONTEND_PORT && sel.cells.FRONTEND_PORT.port
  // 접속 호스트 = 백엔드 DASH_ACCESS_HOST(.env). 미설정이면 브라우저 hostname 폴백.
  const accessHost = data.access_host || window.location.hostname
  const selAccess = selFePort ? `http://${accessHost}:${selFePort}` : null
  const selAccessUp = sel && sel.cells && sel.cells.FRONTEND_PORT && sel.cells.FRONTEND_PORT.up


  return (
    <div style={S.page}>
      <div style={S.head}>
        <h1 style={S.h1}>Harness</h1>
        <span style={S.meta}>{err ? `⚠ ${err}` : `갱신 ${updated}`}</span>
        <div style={S.headBtns}>
          <button
            style={S.headBtn}
            title="레포 루트 README.md 를 새 탭에서 보기 (열 때마다 최신 파일을 읽는다)"
            onClick={openReadmeTab}
          >📄 README</button>
          <button
            style={S.headBtn}
            title="제어 토큰 재입력 (서버 DASH_TOKEN 과 일치해야)"
            onClick={() => {
              const cur = localStorage.getItem('dashToken') || ''
              const t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):', cur)
              if (t !== null) { t ? localStorage.setItem('dashToken', t) : localStorage.removeItem('dashToken') }
            }}
          >🔑 토큰</button>
        </div>
      </div>

      {/* ── 포트 레지스트리 (Mission Control 스타일) ── */}
      <section style={S.section}>
        <PortRegistry
          columns={columns} items={items} onPick={(it) => { setSelMode('control'); setSel(it) }}
          onShutdownAll={shutdownAll} onCtoAll={ctoAll}
          shuttingDown={busy === '__shutdown_all__'}
          ctoStartBusy={busy === '__cto_all_start__'}
          ctoStopBusy={busy === '__cto_all_stop__'}
          globalBusy={busy.startsWith('__')}
        />
      </section>

      {/* ── 연결도 = Mission Control ── */}
      <section style={S.section}>
        {/* type='cto' = 산출물 없는 논의 전용 세션. Port Registry 에는 포트를 갖고
            뜨지만 여기서는 뺀다 — Mission Control 은 모듈·프로젝트 계보 그래프다. */}
        <MissionControl items={items.filter((it) => it.type !== 'cto')} links={data.links} harnessDirty={data.harness_dirty} onPick={(it) => { setSelMode('schema'); setSel(it) }} onNode={(it) => { setSelMode('inbox'); setNodeTab('git'); setSel(it) }} updated={updated} onHub={() => { setHubTab('git'); setHubInbox(true) }} />
      </section>

      {/* ── 상세 모달 ── */}
      {sel && (
        <div style={S.overlay} onClick={() => setSel(null)}>
          {/* inbox 모드는 본문(pre-wrap, 수 KB codex 리포트)이 들어오므로 더 넓게 */}
          <div style={{ ...S.modal, ...(selMode === 'inbox' ? S.modalWide : {}) }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalHead}>
              <span style={S.modalTitle}>
                {selMode === 'inbox'
                  ? `${sel.name} · ${nodeTab === 'git' ? 'git' : 'codex ↔ claude'}`
                  : `${sel.git_repo ? '🏆' : '⏳'} ${sel.name}`}
              </span>
              <button style={S.close} onClick={() => setSel(null)}>✕</button>
            </div>

            {selMode === 'inbox' && (
              <>
                {/* 노드 모달 안에서 뷰를 갈아끼운다 — 모달 위에 모달을 쌓지 않는 기존 이디엄 유지 */}
                <style>{ibCss}</style>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <button className={'ib-tab' + (nodeTab === 'git' ? ' on' : '')} onClick={() => setNodeTab('git')}>
                    🌿 Git 상태
                  </button>
                  <button className={'ib-tab' + (nodeTab === 'chat' ? ' on' : '')} onClick={() => setNodeTab('chat')}>
                    💬 codex ↔ claude
                  </button>
                </div>
                {nodeTab === 'chat' ? <PairInboxView name={sel.name} /> : <GitStatusView base={`/api/cto/${sel.name}`} />}
              </>
            )}

            {selMode === 'schema' && (
            <div style={S.field}>
              <div style={S.fieldLabel}>DB 스키마{schema && schema.ok && schema.engine ? ` · ${schema.engine}` : ''}</div>
              <style>{schemaCss}</style>
              {schema === null ? (
                <span style={S.none}>불러오는 중…</span>
              ) : !schema.ok ? (
                <span style={S.none}>스키마 조회 실패</span>
              ) : schema.status === 'none' ? (
                <span style={S.none}>DB 미사용 (plan only / 비DB 빌드)</span>
              ) : schema.status === 'infra' ? (
                <span style={S.none}>DB 인프라 있음 — 테이블 아직 미정의</span>
              ) : (
                <div className="sc">
                  {schema.tables.map((t) => (
                    <div className="sc-t" key={t.table}>
                      <div className="sc-tn">▸ {t.table}</div>
                      <table className="sc-tbl">
                        <thead>
                          <tr><th>컬럼</th><th>타입</th><th>제약</th></tr>
                        </thead>
                        <tbody>
                          {t.cols.map((c, i) => (
                            <tr key={i}>
                              <td className="sc-cn">{c.name}</td>
                              <td className="sc-ct">{c.type}</td>
                              <td className="sc-cf">{c.flags.length > 0 ? c.flags.join(' ') : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                  <div className="sc-m">source: {schema.source} · migrations: {schema.migrations}</div>
                </div>
              )}
            </div>
            )}

            {selMode === 'control' && (<>
            <div style={S.field}>
              <div style={S.fieldLabel}>서버 경로</div>
              <div style={S.pathRow}>
                <span style={S.path}>{sel.path}</span>
                <button style={S.copyBtn} title={copied ? '복사됨' : '복사'} onClick={() => copy(sel.path)}>
                  {copied ? '✓' : <CopyIcon />}
                </button>
              </div>
            </div>

            <div style={S.field}>
              <div style={S.fieldLabel}>Git</div>
              {selUrl ? (
                <a href={selUrl} target="_blank" rel="noopener noreferrer" style={S.gitLink}>{sel.git_url} 🔗</a>
              ) : (
                <span style={S.none}>없음 (진행중)</span>
              )}
            </div>

            <div style={S.field}>
              <div style={S.fieldLabel}>접속 URL</div>
              {selAccess ? (
                <a href={selAccess} target="_blank" rel="noopener noreferrer" style={S.gitLink}>
                  {selAccess} 🔗{!selAccessUp && <span style={S.none}> (중지됨)</span>}
                </a>
              ) : (
                <span style={S.none}>—</span>
              )}
            </div>

            <div style={S.ctrlLabel}>컨트롤</div>
            <div style={S.ctrlPanel}>
              {[
                { key: 'cto', label: ctoPartial(sel) ? 'CTO pair 복구' : 'CTO pair', sub: ctoHalfSummary(sel), on: ctoHealthy(sel), partial: ctoPartial(sel), act: () => ctoToggle(sel) },
                // dev/docker 상호배제: 같은 호스트 포트라 동시 기동 불가. 상대가 떠있으면
                // '실행' 버튼 비활성(종료 방향은 항상 허용). 백엔드 가드(main.py)와 짝.
                { key: 'dev', label: 'dev 서버', sub: 'venv uvicorn + vite', on: sel.dev_up, act: () => devToggle(sel), block: sel.has_dev === false ? 'dev.sh 없음 — 미지원' : (!sel.dev_up && sel.docker_up) ? 'Docker 실행중 — 먼저 Docker 종료' : null },
                { key: 'docker', label: 'Docker', sub: 'compose 전 서비스', on: sel.docker_up, act: () => dockerToggle(sel), block: sel.has_compose === false ? 'docker-compose 없음 — 미지원' : sel.docker_built === false ? 'docker 미구축 — CTO에게 "docker화 해" 라고 지시하면 활성화됨' : (!sel.docker_up && sel.dev_up) ? 'dev 실행중 — 먼저 dev 종료' : null },
              ].map((s) => (
                <div key={s.key} style={{ ...S.ctrlRow, ...(s.on ? S.ctrlRowOn : {}), ...(s.partial ? S.ctrlRowWarn : {}) }}>
                  <div style={S.ctrlMeta}>
                    <span style={S.ctrlName}>{s.label}</span>
                    <span style={S.ctrlSub}>{s.sub}</span>
                  </div>
                  <span style={{ ...S.ctrlState, color: s.partial ? '#fbbf24' : s.on ? '#34d399' : '#6b7488' }}>
                    {s.block ? <span style={{ color: '#8891aa', fontSize: 11 }} title={s.block}>🔒 {s.block}</span> : (s.partial ? '△ partial' : s.on ? '● 정상' : '○ 정지')}
                  </span>
                  <button
                    style={{ ...S.ctrlBtn, ...(s.partial ? S.ctrlRepair : s.on ? S.ctrlStop : S.ctrlGo), ...((busy === `${sel.name}:${s.key}` || s.block) ? S.actOff : {}) }}
                    disabled={busy === `${sel.name}:${s.key}` || !!s.block}
                    title={s.block || ''}
                    onClick={s.act}
                  >
                    {busy === `${sel.name}:${s.key}` ? '…' : (s.partial ? '복구' : s.on ? '종료' : '실행')}
                  </button>
                </div>
              ))}
            </div>

            <div style={S.ctrlLabel}>위험구역</div>
            <div style={S.ctrlPanel}>
              <div style={S.ctrlRow}>
                <div style={S.ctrlMeta}>
                  <span style={S.ctrlName}>프로젝트 삭제</span>
                  <span style={S.ctrlSub}>dir·sqlite·로그·세션·컨테이너 전부 제거 — 복구 불가</span>
                </div>
                <button
                  style={{ ...S.ctrlBtn, ...S.dangerBtn, ...(busy === `${sel.name}:delete` ? S.actOff : {}) }}
                  disabled={busy === `${sel.name}:delete`}
                  onClick={() => deleteProject(sel)}
                >{busy === `${sel.name}:delete` ? '…' : '🗑 삭제'}</button>
              </div>
            </div>
            </>)}
          </div>
        </div>
      )}

      {/* ── CEO 인박스 모달 (중앙 허브 DEEP.INC 클릭) ── */}
      {hubInbox && (
        <div style={S.overlay} onClick={() => setHubInbox(false)}>
          <div style={{ ...S.modal, ...S.modalWide }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalHead}>
              <span style={S.modalTitle}>
                DEEP.INC · {hubTab === 'git' ? 'git (하네스)' : 'Inbox · CEO'}
              </span>
              <button style={S.close} onClick={() => setHubInbox(false)}>✕</button>
            </div>
            {/* 노드 모달과 같은 이디엄 — 탭으로 뷰만 교체. git 은 하네스 루트 저장소. */}
            <style>{ibCss}</style>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <button className={'ib-tab' + (hubTab === 'git' ? ' on' : '')} onClick={() => setHubTab('git')}>
                🌿 Git 상태
              </button>
              <button className={'ib-tab' + (hubTab === 'inbox' ? ' on' : '')} onClick={() => setHubTab('inbox')}>
                💬 CEO Inbox
              </button>
            </div>
            {hubTab === 'git' ? <GitStatusView base="/api/harness" /> : <CeoInboxView />}
          </div>
        </div>
      )}
      {/* ── CTO 실행 방식 선택 (이어서 / fresh) — 상세 모달(z:50) 위에 떠야
           하므로 마지막 sibling + zIndex 60 (상세 모달에서 열리는 팝업) ── */}
      {ctoStartAsk && (
        <div style={{ ...S.overlay, zIndex: 60 }} onClick={() => setCtoStartAsk(null)}>
          <div style={{ ...S.modal, width: 'min(420px, 92vw)' }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalHead}>
              <span style={S.modalTitle}>CTO pair 실행 · {ctoStartAsk.name}</span>
              <button style={S.close} onClick={() => setCtoStartAsk(null)}>✕</button>
            </div>
            <div className="cto-start-choices">
              <button className="pr-btn pr-cto-start csc-btn" onClick={() => ctoStart(ctoStartAsk, false)}>
                이어서 시작
                <span className="csc-sub">이전 대화 복원 (--resume) · Claude+Codex+Designer 기동</span>
              </button>
              <button className="pr-btn csc-btn csc-fresh" onClick={() => ctoStart(ctoStartAsk, true)}>
                Fresh 시작
                <span className="csc-sub">Claude·Codex 대화 + 페어 메시지 내역 초기화 · 빌드/스펙은 유지</span>
              </button>
            </div>
          </div>
        </div>
      )}

      <Toast tasks={tasks} />
    </div>
  )
}

function Toast({ tasks }) {
  if (!tasks.length) return null
  return (
    <div style={S.toastWrap}>
      <style>{`@keyframes dashBar{0%{left:-45%}100%{left:100%}}`}</style>
      {tasks.map((t) => (
        <div key={t.id} style={S.toast}>
          <div style={S.toastHead}>
            <span style={S.toastLabel}>{t.label}</span>
            <span style={S.toastStatus}>
              {t.status === 'running' ? '진행중' : t.status === 'done' ? '✅ 완료' : '⚠ 실패'}
            </span>
          </div>
          <div style={S.toastTrack}>
            {t.status === 'running'
              ? <div style={S.toastBarRun} />
              : <div style={{ ...S.toastBarFill, background: t.status === 'done' ? '#34d399' : '#f87171' }} />}
          </div>
          {t.detail ? <div style={S.toastDetail}>{t.detail}</div> : null}
        </div>
      ))}
    </div>
  )
}

const S = {
  page: { fontFamily: 'system-ui, sans-serif', padding: 32, color: '#e7e9f3', background: '#0b0a1a', minHeight: '100vh' },
  head: { display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 24 },
  h1: { fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: '-0.3px', background: 'linear-gradient(90deg,#c4b5fd,#67e8f9)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' },
  meta: { fontSize: 12, color: '#b4b9d0', fontFamily: 'ui-monospace, monospace' },
  // 헤더 버튼 묶음 — marginLeft:auto 는 **묶음에만** 건다. 버튼마다 걸면 flex 가 남은
  // 공간을 버튼 수만큼 쪼개서 앞 버튼이 화면 가운데로 밀린다(2026-07-21 실측 x=671).
  headBtns: { marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 },
  headBtn: { fontSize: 12, padding: '5px 12px', borderRadius: 8, border: '1px solid #3a3f5a', background: '#1c1f30', color: '#c4b5fd', cursor: 'pointer', fontWeight: 600 },
  toastWrap: { position: 'fixed', top: 16, right: 16, display: 'flex', flexDirection: 'column', gap: 10, zIndex: 1000, width: 320 },
  toast: { background: '#15172a', border: '1px solid #2a2f48', borderRadius: 10, padding: '12px 14px', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' },
  toastHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 },
  toastLabel: { fontSize: 13, fontWeight: 600, color: '#e7e9f3', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  toastStatus: { fontSize: 11, color: '#b4b9d0', flexShrink: 0 },
  toastTrack: { position: 'relative', height: 6, borderRadius: 4, background: '#2a2f48', overflow: 'hidden' },
  toastBarRun: { position: 'absolute', top: 0, bottom: 0, width: '45%', borderRadius: 4, background: 'linear-gradient(90deg,#c4b5fd,#67e8f9)', animation: 'dashBar 1.1s ease-in-out infinite' },
  toastBarFill: { position: 'absolute', top: 0, bottom: 0, left: 0, width: '100%', borderRadius: 4 },
  toastDetail: { fontSize: 11, color: '#9aa0bd', marginTop: 6, lineHeight: 1.4 },
  section: { marginBottom: 28 },
  h2: { fontSize: 15, color: '#555', display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 12px' },
  count: { fontSize: 12, color: '#999', background: '#eee', borderRadius: 10, padding: '1px 8px', marginLeft: 4 },
  grid: { display: 'flex', flexWrap: 'wrap', gap: 12 },
  card: {
    display: 'flex', alignItems: 'center', gap: 10, border: '2px solid', borderRadius: 10,
    padding: '14px 20px', fontSize: 15, fontWeight: 600, background: '#fff', minWidth: 120,
  },
  link: { cursor: 'pointer' },
  empty: { color: '#bbb', fontSize: 14 },

  ctrlLabel: { fontSize: 11, color: '#b4b9d0', margin: '22px 0 9px', fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase' },
  ctrlPanel: { display: 'flex', flexDirection: 'column', gap: 8 },
  ctrlRow: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '9px 11px',
    background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 13,
    transition: 'border-color .15s, background .15s',
  },
  ctrlRowOn: { background: 'rgba(52,211,153,0.06)', borderColor: 'rgba(52,211,153,0.28)' },
  ctrlRowWarn: { background: 'rgba(245,158,11,0.07)', borderColor: 'rgba(245,158,11,0.38)' },
  ctrlFace: {
    width: 42, height: 42, borderRadius: 11, objectFit: 'cover', flexShrink: 0,
    border: '1px solid rgba(167,139,250,0.4)', boxShadow: '0 0 14px rgba(124,58,237,0.45)',
  },
  ctrlMeta: { display: 'flex', flexDirection: 'column', gap: 1, flex: 1, minWidth: 0 },
  ctrlName: { fontSize: 14, fontWeight: 700, color: '#e7e9f3' },
  ctrlSub: { fontSize: 11, color: '#8891aa' },
  ctrlState: { fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' },
  ctrlBtn: {
    minWidth: 58, padding: '7px 14px', borderRadius: 9, fontSize: 13, fontWeight: 700,
    border: '1px solid', cursor: 'pointer', fontFamily: 'inherit', transition: 'opacity .15s',
  },
  ctrlGo: { background: '#059669', color: '#fff', borderColor: '#047857' },
  ctrlRepair: { background: '#b45309', color: '#fff', borderColor: '#92400e' },
  ctrlStop: { background: 'rgba(248,113,113,0.13)', color: '#fca5a5', borderColor: 'rgba(248,113,113,0.4)' },
  dangerBtn: { background: '#dc2626', color: '#fff', borderColor: '#b91c1c' },
  actOff: { opacity: 0.4, cursor: 'not-allowed' },

  tableWrap: { overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 10, background: '#fff' },
  graphWrap: { border: '1px solid #e5e7eb', borderRadius: 10, background: '#fff', padding: 12 },
  graphHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  toggle: { display: 'flex', gap: 4, background: '#eee', borderRadius: 8, padding: 3 },
  tbtn: { border: 'none', background: 'none', borderRadius: 6, padding: '4px 12px', fontSize: 13, cursor: 'pointer', color: '#666' },
  tbtnOn: { background: '#fff', color: '#111', fontWeight: 600, boxShadow: '0 1px 2px rgba(0,0,0,0.1)' },
  table: { borderCollapse: 'collapse', width: '100%', fontSize: 13, whiteSpace: 'nowrap' },
  th: {
    textAlign: 'center', padding: '10px 12px', background: '#f9fafb', color: '#6b7280',
    fontWeight: 600, borderBottom: '1px solid #e5e7eb', position: 'sticky', top: 0,
  },
  thLeft: { textAlign: 'left' },
  row: { borderBottom: '1px solid #f3f4f6' },
  td: { padding: '10px 12px', borderBottom: '1px solid #f3f4f6' },
  tdName: { fontWeight: 600, textAlign: 'left' },
  tdMid: { padding: '10px 12px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' },
  tdPort: { padding: '10px 12px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' },
  dash: { color: '#d1d5db' },
  badge: { padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 },

  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(4,5,10,0.72)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, zIndex: 50,
  },
  modal: {
    position: 'relative',
    background: 'radial-gradient(900px 320px at 82% -30%, #21183f 0%, #140f2e 45%, #0b0a1a 100%)',
    border: '1px solid rgba(255,255,255,0.10)', borderRadius: 18, padding: '24px 26px',
    width: 'min(560px, 92vw)', color: '#e7e9f3',
    boxShadow: '0 24px 70px -20px rgba(0,0,0,0.7), 0 0 0 1px rgba(124,58,237,0.10)',
    // 본문이 길면 뷰포트를 넘어간다 — overlay 가 가운데 정렬이라 위아래가 같이
    // 잘려서 상단 버튼 줄이 화면 밖으로 나갔다(2026-08-01). 모달 자체를 스크롤시킨다.
    // (overlay padding 20 × 2 를 뺀 값)
    maxHeight: 'calc(100vh - 40px)', overflowY: 'auto',
  },
  // 인박스 모드(노드·허브) — 본문이 수 KB pre-wrap 이라 control/schema 모달보다 넓게.
  modalWide: { width: 'min(1000px, 92vw)' },
  modalHead: { display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 },
  novaImg: {
    width: 58, height: 58, borderRadius: 14, objectFit: 'cover', flexShrink: 0,
    border: '1px solid rgba(167,139,250,0.45)', boxShadow: '0 0 18px rgba(124,58,237,0.5)',
  },
  modalTitle: {
    fontSize: 20, fontWeight: 800, letterSpacing: '-0.3px', flex: 1,
    background: 'linear-gradient(90deg,#c4b5fd,#67e8f9)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
  },
  close: { border: 'none', background: 'rgba(255,255,255,0.06)', width: 30, height: 30, borderRadius: 8, fontSize: 15, color: '#b4b9d0', cursor: 'pointer', lineHeight: 1 },
  field: { marginBottom: 16 },
  fieldLabel: { fontSize: 11, color: '#b4b9d0', marginBottom: 6, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase' },
  pathRow: { display: 'flex', alignItems: 'stretch', gap: 8 },
  path: {
    flex: 1, background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 8,
    padding: '10px 12px', fontSize: 13, wordBreak: 'break-all', color: '#cdd3e3', fontFamily: 'ui-monospace, monospace',
  },
  copyBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 38,
    border: '1px solid rgba(255,255,255,0.10)', borderRadius: 8, background: 'rgba(255,255,255,0.04)', color: '#b4b9d0', cursor: 'pointer',
  },
  gitLink: { color: '#67e8f9', textDecoration: 'none', fontSize: 14, wordBreak: 'break-all' },
  none: { color: '#6b7488', fontSize: 14 },
}
