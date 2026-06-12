# CTO 진행상황 소리 알림 (선택적 Stop hook)

다중 CTO / 긴 build 를 돌릴 때, 매번 화면을 보지 않아도 주의가 필요한 시점에
알림음을 받으려면 사용자 `settings.json` 에 `Stop` hook 한 줄을 추가한다.

> CTO 는 이 설정을 **자동으로 박지 않는다** — 사용자가 원할 때만 안내한다
> (사용자 환경 침범 X).

```json
"hooks": {
  "Stop": [
    {
      "hooks": [
        { "type": "command", "command": "paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || true" }
      ]
    }
  ]
}
```

macOS: `afplay /System/Library/Sounds/Glass.aiff`.
