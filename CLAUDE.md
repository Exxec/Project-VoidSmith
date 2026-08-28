# VoidSmith Agent Notes

`AGENTS.md` is the canonical contributor and agent contract. Read and follow
its required document order before changing code. This short file exists only
for tools that automatically discover `CLAUDE.md`; it intentionally does not
duplicate implementation history or local review notes.

VoidSmith is offline, deterministic, explainable, and source-read-only. Keep
legality separate from quality, preserve unknown scripted behavior, and do not
commit Starsector/mod data, reports, entity lists, or local calibration output.

For the current project plan, use `ROADMAP.md`. For commands, packaging, and
user-facing behavior, use `README.md`, `docs/QUICK_START.md`, and
`docs/DEVELOPER_GUIDE.md`. Run the portable suite after behavior changes:

```powershell
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```
