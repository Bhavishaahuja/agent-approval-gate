Output demo/demo.gif
Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 720
Set TypingSpeed 40ms

# off camera: make `uvx agent-approval-gate` run this checkout (works before it is on PyPI)
# and build it once so the recording does not show a build
Hide
# vhs starts a clean bash without ~/.bashrc, so add the usual places uv lives
Type `export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/home/linuxbrew/.linuxbrew/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`
Enter
Type `uvx() { command uvx --from "$PWD" "$@"; }`
Enter
Type "uvx agent-approval-gate --version >/dev/null 2>&1; clear"
Enter
Sleep 15s
Show

Type "uvx agent-approval-gate demo"
Enter
Sleep 2s
# medium risk: answer "always", the second rename runs without asking
Type "a"
Sleep 500ms
Enter
Sleep 2s
# high risk: read the preview, then approve
Type "y"
Sleep 500ms
Enter
Sleep 4s
