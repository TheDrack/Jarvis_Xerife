import subprocess
import sys

COMMIT = "4a874c36f4f982222f03f816268733088d7f2fa7"

def run(cmd):
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        sys.exit(result.returncode)

run("git config user.name 'github-actions'")
run("git config user.email 'actions@github.com'")

run(f"git reset --hard {COMMIT}")
run("git push origin HEAD --force")