import py_compile, glob
errs=[]
files = glob.glob("app/**/*.py", recursive=True)
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        errs.append((f, str(e).splitlines()[-1]))
print("total app files:", len(files))
print("compile errors:", len(errs))
for f,e in errs:
    print(" -", f, "|", e)
with open("app/models.py", encoding="utf-8") as fh:
    lines = fh.readlines()
tab_lines = [i+1 for i,l in enumerate(lines) if l.startswith("\t")]
print("models.py TAB-start lines:", len(tab_lines), tab_lines[:10])
