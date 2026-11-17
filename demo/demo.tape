Output demo/demo.gif
Set FontSize 18
Set Width 1100
Set Height 720
Set TypingSpeed 40ms

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
