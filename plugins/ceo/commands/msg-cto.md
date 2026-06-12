---
description: Send a message to a CTO. Usage: /msg-cto <name> "<message>"
argument-hint: <name> "<message>"
---

Send a message to CTO `$0` via the harness CLI.

!cto='$0'; [[ "$cto" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "error: cto name must be kebab-case (lowercase, digits, hyphens). Usage: /msg-cto <name> \"<message>\""; exit 1; }; printf '%s' '$1' | harness send --to "cto:$cto" --body-stdin
