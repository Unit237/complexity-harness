# Security policy

Complexity Harness reads source trees and writes local JSON or Markdown
artifacts. It does not require repository credentials, agent credentials, or
production access.

Do not place secrets in repository inventories, snapshots, architectural
memory, refactor jobs, tests, or issue reports.

For a suspected vulnerability, use GitHub's private vulnerability reporting
for `Unit237/complexity-harness`. Please include the affected version, a minimal
reproduction, and the security impact. Avoid opening a public issue until the
report has been assessed.
