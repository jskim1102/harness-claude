import React, { useEffect, useMemo, useRef, useState } from 'react'
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
    ctx.lineWidth = it.cto_active ? 2 : 1.2
    ctx.strokeStyle = it.cto_active ? '#f59e0b' : col
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
    if (it.cto_active) {
      ctx.beginPath(); ctx.arc(x + ww - 6, y + 6, 2.2, 0, 2 * Math.PI); ctx.fillStyle = '#f59e0b'; ctx.fill()
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

function BrainGraph({ items, links, onPick }) {
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const stateRef = useRef({ nodes: [], W: 900, H: 460 })

  const model = useMemo(() => {
    const n = items.length
    const nodes = [{ id: 'CEO', label: 'CEO', x: 0.5, y: 0.5, r: 21, color: '#2dd4ef', hub: true }]
    items.forEach((it, i) => {
      const ang = (i / Math.max(n, 1)) * 2 * Math.PI - Math.PI / 2
      nodes.push({
        id: it.name, label: it.name, item: it,
        x: 0.5 + 0.34 * Math.cos(ang), y: 0.5 + 0.37 * Math.sin(ang),
        r: 12 + (i % 3) * 2.4, color: it.type === 'module' ? '#a78bfa' : '#34d399', active: it.cto_active,
      })
    })
    nodes.forEach((nd, i) => { nd.phase = i * 1.7; nd.speed = 0.6 + (i % 3) * 0.18 })
    const byId = {}; nodes.forEach((nd) => { byId[nd.id] = nd })
    const ls = (links || []).filter((l) => byId[l.source] && byId[l.target])
      .map((l) => ({ a: l.source, b: l.target, lineage: l.kind === 'lineage' }))
    return { nodes, byId, links: ls }
  }, [items, links])
  const modelRef = useRef(model)
  modelRef.current = model

  const onClick = (e) => {
    const cv = canvasRef.current; if (!cv) return
    const rect = cv.getBoundingClientRect()
    const mx = e.clientX - rect.left, my = e.clientY - rect.top
    const { nodes, W, H } = stateRef.current
    for (const nd of nodes) {
      if (nd.hub || !nd.item) continue
      const dx = mx - nd.x * W, dy = my - nd.y * H
      if (dx * dx + dy * dy <= (nd.r + 11) * (nd.r + 11)) { onPick(nd.item); return }
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
      if (nd.active) {
        const ringR = r + 5 + (reduce ? 0 : 2.5 * ap)
        ctx.shadowBlur = 12; ctx.shadowColor = rgba('#ffb547', 0.9)
        ctx.strokeStyle = rgba('#ffb547', 0.55 + 0.35 * ap); ctx.lineWidth = 1.6
        ctx.beginPath(); ctx.arc(x, y, ringR, 0, 6.283); ctx.stroke(); ctx.shadowBlur = 0
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
      for (const l of ls) {
        const a = byId[l.a], b = byId[l.b]
        const ax = a.x * W, ay = a.y * H, bx = b.x * W, by = b.y * H
        if (l.lineage) {
          const pulse = reduce ? 1 : (0.75 + 0.25 * Math.sin(t * 1.4))
          ctx.save(); ctx.shadowBlur = 8; ctx.shadowColor = rgba('#39d98a', 0.6)
          const gr = ctx.createLinearGradient(ax, ay, bx, by)
          gr.addColorStop(0, rgba('#4d9bff', 0.55 * pulse)); gr.addColorStop(1, rgba('#39d98a', 0.55 * pulse))
          ctx.strokeStyle = gr; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.restore()
          if (!reduce) {
            const p = (t * 0.35) % 1, ppx = ax + (bx - ax) * p, ppy = ay + (by - ay) * p
            ctx.save(); ctx.shadowBlur = 10; ctx.shadowColor = rgba('#bdf6ff', 0.9); ctx.fillStyle = 'rgba(255,255,255,0.95)'
            ctx.beginPath(); ctx.arc(ppx, ppy, 2.2, 0, 6.283); ctx.fill(); ctx.restore()
          }
        } else {
          ctx.strokeStyle = 'rgba(120,150,190,0.13)'; ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        }
      }
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

function MissionControl({ items, links, onPick, updated }) {
  const accents = ['#fb923c', '#ec4899', '#38bdf8', '#34d399', '#a78bfa', '#22d3ee', '#f59e0b', '#f472b6']
  const mods = items.filter((i) => i.type === 'module')
  const projs = items.filter((i) => i.type === 'project')
  const active = items.filter((i) => i.cto_active).length
  const badge = (it) => {
    if (it.cto_active) return { t: 'LIVE', c: '#34d399' }
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
          <div className="mc-chip"><b style={{ fontSize: 13 }}>{updated || '—'}</b><span>sync</span></div>
        </div>
      </div>
      <div className="mc-core"><BrainGraph items={items} links={links} onPick={onPick} /></div>
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
.pr-title { display: inline-block; font-size: 38px; font-weight: 800; letter-spacing: -0.5px; background: linear-gradient(90deg,#c4b5fd,#67e8f9); -webkit-background-clip: text; background-clip: text; color: transparent; margin-bottom: 18px; }
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
.pr-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 20px; font-size: 10px; font-weight: 700; border: 1px solid; letter-spacing: 0.4px; }
`

function PortRegistry({ columns, items }) {
  const typeC = (t) => (t === 'module' ? '#a78bfa' : '#34d399')
  const badge = (it) => {
    if (it.status === 'up') return { t: 'UP', c: '#34d399' }
    if (it.status === 'partial') return { t: 'PARTIAL', c: '#fbbf24' }
    if (it.status === 'down') return { t: 'DOWN', c: '#64748b' }
    return { t: '—', c: '#64748b' }
  }
  const rows = [...items].sort((a, b) => (a.offset ?? 9999) - (b.offset ?? 9999))
  return (
    <div className="pr">
      <style>{prCss}</style>
      <div className="pr-title">Port Registry</div>
      <div className="pr-wrap">
        <table className="pr-table">
          <thead>
            <tr>
              <th className="l">node</th>
              <th>off</th>
              <th>cto</th>
              {columns.map((c) => <th key={c.label}>{c.label}</th>)}
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((it) => {
              const b = badge(it)
              return (
                <tr key={it.type + '/' + it.name}>
                  <td className="l pr-name" style={{ color: typeC(it.type) }}>{it.name}</td>
                  <td>{it.offset ?? <span className="pr-dim">—</span>}</td>
                  <td>{it.cto_active ? <span style={{ color: '#34d399' }}>✅ active</span> : <span className="pr-dim">✋ inactive</span>}</td>
                  {columns.map((c) => {
                    if (c.kind === 'db') {
                      return <td key={c.label}>{it.db && it.db !== '—' ? it.db : <span className="pr-dim">—</span>}</td>
                    }
                    const cell = it.cells[c.var]
                    return (
                      <td key={c.label}>
                        {cell
                          ? <span style={{ color: cell.up ? '#cdd3e3' : '#9aa3b8' }}>{cell.port} {cell.mode === 'docker' ? '🐳' : cell.mode === 'dev' ? '💻' : <span style={{ color: '#8891aa' }}>○</span>}</span>
                          : <span className="pr-dim">—</span>}
                      </td>
                    )
                  })}
                  <td><span className="pr-badge" style={{ color: b.c, borderColor: b.c + '66', background: b.c + '1a' }}>● {b.t}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function App() {
  const [data, setData] = useState({ columns: [], items: [], links: [] })
  const [err, setErr] = useState('')
  const [updated, setUpdated] = useState('')
  const [sel, setSel] = useState(null)      // 열린 모달 항목
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState('')      // 진행중 액션 ('cto'|'docker')

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/state')
        if (!r.ok) throw new Error('HTTP ' + r.status)
        const d = await r.json()
        if (!alive) return
        setData({ columns: d.columns || [], items: d.items || [], links: d.links || [] })
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
      const r = await fetch('/api/state'); const d = await r.json()
      setData({ columns: d.columns || [], items: d.items || [], links: d.links || [] })
      setSel((s) => (s ? (d.items || []).find((it) => it.name === s.name && it.type === s.type) || s : s))
    } catch { /* keep last */ }
  }
  // mutation 토큰 (interim 보호 — 서버 DASH_TOKEN 과 일치해야). localStorage 보관, 없으면 1회 prompt.
  const dashToken = () => {
    let t = localStorage.getItem('dashToken') || ''
    if (!t) { t = window.prompt('대시보드 제어 토큰 (서버 DASH_TOKEN):') || ''; if (t) localStorage.setItem('dashToken', t) }
    return t
  }
  const mutate = async (url) => {
    const t = dashToken()
    const r = await fetch(url, { method: 'POST', headers: t ? { 'X-Dash-Token': t } : {} })
    if (r.status === 401) { localStorage.removeItem('dashToken'); alert('토큰이 틀렸습니다 — 다시 시도하세요.') }
    else if (r.status === 503) { alert('mutation 비활성 — 서버에 DASH_TOKEN 환경변수를 설정하세요.') }
    return r
  }
  const ctoToggle = async (it) => {
    const act = it.cto_active ? 'stop' : 'start'
    const msg = it.cto_active
      ? `CTO 세션 종료: ${it.name}?\n(작업 보존 — 세션/프로세스만 정지)`
      : `CTO 세션 실행: ${it.name}?`
    if (!window.confirm(msg)) return
    setBusy('cto')
    try { await mutate(`/api/cto/${it.name}/${act}`) } finally { setBusy(''); refresh() }
  }
  const devToggle = async (it) => {
    const act = it.dev_up ? '종료' : '실행'
    if (!window.confirm(`dev 서버 ${act}: ${it.name}? (venv uvicorn + vite)`)) return
    setBusy('dev')
    try { await mutate(`/api/dev/${it.name}/toggle`) } finally { setBusy(''); refresh() }
  }
  const dockerToggle = async (it) => {
    const act = it.docker_up ? '종료' : '실행(빌드 — 시간 걸릴 수 있음)'
    if (!window.confirm(`Docker ${act}: ${it.name}?`)) return
    setBusy('docker')
    try { await mutate(`/api/docker/${it.name}/toggle`) } finally { setBusy(''); refresh() }
  }

  const selUrl = sel && safeUrl(sel.git_url)
  const selFePort = sel && sel.cells && sel.cells.FRONTEND_PORT && sel.cells.FRONTEND_PORT.port
  const selAccess = selFePort ? `http://${window.location.hostname}:${selFePort}` : null
  const selAccessUp = sel && sel.cells && sel.cells.FRONTEND_PORT && sel.cells.FRONTEND_PORT.up

  return (
    <div style={S.page}>
      <div style={S.head}>
        <h1 style={S.h1}>Harness</h1>
        <span style={S.meta}>{err ? `⚠ ${err}` : `갱신 ${updated}`}</span>
      </div>

      {/* ── 포트 레지스트리 (Mission Control 스타일) ── */}
      <section style={S.section}>
        <PortRegistry columns={columns} items={items} />
      </section>

      {/* ── 연결도 = Mission Control ── */}
      <section style={S.section}>
        <MissionControl items={items} links={data.links} onPick={setSel} updated={updated} />
      </section>

      {/* ── 상세 모달 ── */}
      {sel && (
        <div style={S.overlay} onClick={() => setSel(null)}>
          <div style={S.modal} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalHead}>
              <span style={S.modalTitle}>{sel.git_repo ? '🏆' : '⏳'} {sel.name}</span>
              <button style={S.close} onClick={() => setSel(null)}>✕</button>
            </div>

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
                { key: 'cto', label: 'CTO 세션', sub: '터미널 attach 로 운전', on: sel.cto_active, act: () => ctoToggle(sel) },
                { key: 'dev', label: 'dev 서버', sub: 'venv uvicorn + vite', on: sel.dev_up, act: () => devToggle(sel) },
                { key: 'docker', label: 'Docker', sub: 'compose 전 서비스', on: sel.docker_up, act: () => dockerToggle(sel) },
              ].map((s) => (
                <div key={s.key} style={{ ...S.ctrlRow, ...(s.on ? S.ctrlRowOn : {}) }}>
                  <div style={S.ctrlMeta}>
                    <span style={S.ctrlName}>{s.label}</span>
                    <span style={S.ctrlSub}>{s.sub}</span>
                  </div>
                  <span style={{ ...S.ctrlState, color: s.on ? '#34d399' : '#6b7488' }}>
                    {s.on ? '● 실행중' : '○ 정지'}
                  </span>
                  <button
                    style={{ ...S.ctrlBtn, ...(s.on ? S.ctrlStop : S.ctrlGo), ...(busy ? S.actOff : {}) }}
                    disabled={!!busy}
                    onClick={s.act}
                  >
                    {busy === s.key ? '…' : (s.on ? '종료' : '실행')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const S = {
  page: { fontFamily: 'system-ui, sans-serif', padding: 32, color: '#e7e9f3', background: '#0b0a1a', minHeight: '100vh' },
  head: { display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 24 },
  h1: { fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: '-0.3px', background: 'linear-gradient(90deg,#c4b5fd,#67e8f9)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' },
  meta: { fontSize: 12, color: '#b4b9d0', fontFamily: 'ui-monospace, monospace' },
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
  ctrlStop: { background: 'rgba(248,113,113,0.13)', color: '#fca5a5', borderColor: 'rgba(248,113,113,0.4)' },
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
  },
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
