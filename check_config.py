import glob, os

# Check for .env files
for root in [r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED', r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend']:
    print(f"\n--- {root} ---")
    for f in glob.glob(os.path.join(root, '.env*')):
        print(f"  {f}")
        try:
            with open(f, 'r') as fp:
                content = fp.read()
            print(content[:500])
            print("...")
        except:
            print("  (cannot read)")

# Check docker-compose override
for f in glob.glob(r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\docker-compose*.yml'):
    print(f"\n--- {f} ---")
    with open(f, 'r') as fp:
        print(fp.read()[:500])
        print("...")