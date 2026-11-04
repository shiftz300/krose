"""Research workspace paths, including references in pre-split evidence.

ROOT is the research directory. Old reports retain their original bytes and
project-relative path strings; this adapter resolves those paths without
rewriting evidence or creating duplicate/symlink source trees. New reports
should use PRODUCT_ROOT as their relative-path base.
"""
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOT = PRODUCT_ROOT / 'research'
PRODUCT_TOOLS = {'bootstrap_plugin.py', 'check_project_boundary.py', 'package_plugin.py',
                 'render_piano.cpp', 'benchmark_piano.cpp'}
PRODUCT_BUILDS = {'plugin', 'sanitize', 'deps', 'downloads', 'structure-isolation'}


class ResearchPath(type(Path())):
    def __truediv__(self, key):
        result = super().__truediv__(key)
        legacy_assets = PRODUCT_ROOT / 'assets/factory-starter'
        if result.is_relative_to(legacy_assets):
            return ResearchPath(PRODUCT_ROOT / 'assets/program-library' / result.relative_to(legacy_assets))
        try:
            parts = result.relative_to(RESEARCH_ROOT).parts
        except ValueError:
            return result
        if not parts:
            return result
        if parts[0] == 'research':
            return ResearchPath(RESEARCH_ROOT.joinpath(*parts[1:]))
        if parts[:2] == ('assets', 'factory-starter'):
            return ResearchPath(PRODUCT_ROOT.joinpath('assets', 'program-library', *parts[2:]))
        if parts[0] in {'src', 'assets', 'tests', 'cmake', 'licenses', 'CMakeLists.txt'}:
            return ResearchPath(PRODUCT_ROOT.joinpath(*parts))
        if parts[0] == 'tools' and len(parts) > 1:
            if parts[1] in PRODUCT_TOOLS:
                return ResearchPath(PRODUCT_ROOT.joinpath(*parts))
            if parts[1] in {'test_native_filter.cpp', 'test_native_voice.cpp', 'test_piano_engine.cpp', 'test_vst3_host.cpp', 'test_concert_effects_sanitize.c'}:
                return ResearchPath(PRODUCT_ROOT.joinpath('tests', *parts[1:]))
        if parts[0] == 'build' and len(parts) > 1 and parts[1] in PRODUCT_BUILDS:
            return ResearchPath(PRODUCT_ROOT.joinpath(*parts))
        return result


ROOT = ResearchPath(RESEARCH_ROOT)
