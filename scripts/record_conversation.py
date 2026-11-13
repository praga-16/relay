"""Archive the actual supplied build prompt; never collect .env or IDE buffer contents."""
from pathlib import Path
from app.settings import ROOT


def main():
    source=Path('C:/Users/Coderays_User/.codex/attachments/f031bbdb-9aba-43eb-af57-73b5fc2d389f/Pasted text.txt')
    destination=ROOT/'reports/prompt_records';destination.mkdir(parents=True,exist_ok=True)
    if source.exists():
        target=destination/'final_build_instruction.txt'
        if not target.exists():target.write_bytes(source.read_bytes())


if __name__=='__main__':main()
