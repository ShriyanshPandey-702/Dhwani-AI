"""
Phase 1 training package — deliberately separate from `evaluation/`.

`evaluation/` must never import from here, and nothing here may import a
test-set loader. Keeping them apart makes leakage a structural impossibility
rather than a matter of discipline.
"""
