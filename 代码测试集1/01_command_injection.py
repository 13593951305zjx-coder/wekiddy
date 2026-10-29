import os
import subprocess


def run_user_command(user_input: str) -> None:
    # Expected: PY-CMD-001 and PY-CMD-002
    os.system("ping " + user_input)
    subprocess.run(user_input, shell=True, check=False)

