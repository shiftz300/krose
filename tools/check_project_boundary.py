#!/usr/bin/env python3
"""Prove that the engine and its tests build without research/output/Python.

Only frozen assets, product source, tests and CMake are copied to a disposable
checkout. Logs and the source fingerprint report remain in build/.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(path):
    manifest=json.loads((path/'manifest.json').read_text())
    for item in manifest['files']:
        source=path/item['file']
        assert source.stat().st_size==item['bytes'] and digest(source)==item['sha256'],source
    return manifest


def main():
    runtime=bundle(ROOT/'assets/concert-se-grand')
    fixtures=bundle(ROOT/'tests/fixtures/concert-se-grand')
    factory=bundle(ROOT/'assets/program-library')
    program_fixtures=bundle(ROOT/'tests/fixtures/full-programs')
    performance_fixtures=bundle(ROOT/'tests/fixtures/performance')
    arp_fixtures=bundle(ROOT/'tests/fixtures/arpeggiator')
    sources=[ROOT/'CMakeLists.txt',*sorted((ROOT/'cmake').glob('*.cmake')),*sorted((ROOT/'src').rglob('*')),
             *sorted((ROOT/'tests').glob('*.cpp'))]
    for path in (ROOT/'src').rglob('*'):
        if path.is_file() and path.suffix in ('.cpp', '.c', '.h', '.mm'):
            text=path.read_text()
            for forbidden in ('research/','KROSSAPP.bin','program_firmware','unicorn'):
                assert forbidden not in text,(path,forbidden)
    for path in [ROOT/'CMakeLists.txt', *sorted((ROOT/'cmake').glob('*.cmake')), *sorted((ROOT/'src').rglob('CMakeLists.txt'))]:
        text=path.read_text()
        for forbidden in ('CMAKE_SOURCE_DIR}/research','CMAKE_SOURCE_DIR}/docs','CMAKE_SOURCE_DIR}/output','find_package(Python3','prepare_voice_assets.py','prepare_plugin_assets.py'):
            assert forbidden not in text,(path,forbidden)
    logs=ROOT/'build/structure-isolation';logs.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='product-only-',dir=ROOT/'build') as temporary:
        isolated=Path(temporary);checkout=isolated/'source';checkout.mkdir()
        shutil.copyfile(ROOT/'CMakeLists.txt',checkout/'CMakeLists.txt')
        for name in ('src','cmake','assets','tests'):shutil.copytree(ROOT/name,checkout/name)
        assert all(not (checkout/name).exists() for name in ('research','docs','output','EXPCM001','tools'))
        build=isolated/'build'
        commands=[('configure',['cmake','-S',str(checkout),'-B',str(build),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
                               '-DSEGRAND_BUILD_PLUGIN=OFF','-DSEGRAND_BUILD_TOOLS=OFF','-DCMAKE_DISABLE_FIND_PACKAGE_Python3=TRUE']),
                  ('build',['cmake','--build',str(build),'-j','6']),
                  ('ctest',['ctest','--test-dir',str(build),'--output-on-failure'])]
        for name,command in commands:
            with (logs/(name+'.log')).open('w') as stream:subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
        assert '100% tests passed out of 8' in (logs/'ctest.log').read_text()
        assert not (build/'CMakeCache.txt').read_text().find('Python3_EXECUTABLE:')>=0
        for name in ('SEGrand.samples','ConcertEqData.h','NativeVoiceData.h'):
            assert digest(build/'generated'/name)==digest(ROOT/'assets/concert-se-grand'/name)
    result=dict(scope='Disposable product-only engine checkout; no research, output, EXPCM001 or tools directory; Python3 discovery disabled',
                runtime_asset_files=len(runtime['files'])+len(factory['files']),ARM_fixture_files=len(fixtures['files'])+len(program_fixtures['files'])+len(performance_fixtures['files'])+len(arp_fixtures['files']),isolated_CTest=[8,8],
                source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sources if p.is_file()},
                log_sha256={str(p.relative_to(ROOT)):digest(p) for p in logs.glob('*.log')},
                factory_manifest_sha256=digest(ROOT/'assets/program-library/manifest.json'),
                runtime_manifest_sha256=digest(ROOT/'assets/concert-se-grand/manifest.json'),
                fixture_manifest_sha256=digest(ROOT/'tests/fixtures/concert-se-grand/manifest.json'),
                deployment='No plugin built or installed by this isolated check')
    (ROOT/'build/project-boundary-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS product-only build and 8 CTests with research/output/tools absent and Python discovery disabled')


if __name__=='__main__':main()
