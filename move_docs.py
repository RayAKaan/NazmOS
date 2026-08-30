import os, shutil

src = r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\docs\codebase-audit'
dst = r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\docs\phase_a_audit'

os.makedirs(dst, exist_ok=True)

for f in os.listdir(src):
    if f.endswith('.md'):
        shutil.move(os.path.join(src, f), os.path.join(dst, f))
        print(f'Moved: {f}')

print(f'\nAll .md files moved to: {dst}')