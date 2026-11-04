"""Small format/rollback regressions; no real sample upload or product writes."""
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

TOOL=Path(__file__).resolve().parents[2]/'tools/release/runtime_assets.py'
FACTORY='assets/program-library/Factory.samples'
CONCERT='assets/concert-se-grand/SEGrand.samples'


class RuntimeArchives(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.archive=self.root/'runtime.tar.xz'
        self.lock=self.root/'lock.json'

    def tearDown(self):
        self.tmp.cleanup()

    def put(self,name,data):
        target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        (target.parent/'manifest.json').write_text(json.dumps(dict(files=[dict(file=target.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())])))

    def run_tool(self,action,success=True):
        result=subprocess.run([sys.executable,str(TOOL),action,str(self.archive),'--root',str(self.root),'--lock',str(self.lock)],capture_output=True,text=True)
        self.assertEqual(result.returncode==0,success,result.stderr)

    def native(self):
        self.put(FACTORY,b'KRPRG003'+struct.pack('<I',3)+bytes(range(256))*3)
        self.put(CONCERT,b'SEGRAND1'+struct.pack('<I',2)+b'view')

    def test_native_roundtrip(self):
        self.native();expected=[(self.root/n).read_bytes() for n in [FACTORY,CONCERT]]
        self.run_tool('pack');self.assertEqual(json.loads(self.lock.read_text())['tag'],'runtime-assets-v2')
        for name in [FACTORY,CONCERT]:(self.root/name).unlink()
        self.run_tool('extract')
        self.assertEqual([(self.root/n).read_bytes() for n in [FACTORY,CONCERT]],expected)

    def test_legacy_roundtrip(self):
        table=24+224*4+256*2+129*2
        header=bytearray(table+32);header[:8]=b'KRPRG002';struct.pack_into('<II',header,8,2,1)
        struct.pack_into('<I',header,table+4,4);struct.pack_into('<Q',header,table+24,len(header))
        mono=bytes(range(12));self.put(FACTORY,header+mono)
        view=bytearray(32+84*32);view[:8]=b'SEGRAND1';struct.pack_into('<II',view,8,1,84)
        stereo=bytes(byte for frame in range(4) for channel in range(2) for byte in mono[frame*3:frame*3+3])
        for i in range(84):
            struct.pack_into('<I',view,32+i*32+12,4);struct.pack_into('<Q',view,32+i*32+24,len(view)+i*len(stereo))
        self.put(CONCERT,view+stereo*84);expected=(self.root/CONCERT).read_bytes()
        self.run_tool('pack');self.run_tool('extract');self.assertEqual((self.root/CONCERT).read_bytes(),expected)

    def test_invalid_second_bank_never_replaces_first(self):
        self.native();self.run_tool('pack')
        (self.root/FACTORY).write_bytes(b'keep factory');(self.root/CONCERT).write_bytes(b'keep concert')
        manifest=self.root/CONCERT;metadata=json.loads((manifest.parent/'manifest.json').read_text());metadata['files'][0]['sha256']='0'*64
        (manifest.parent/'manifest.json').write_text(json.dumps(metadata))
        self.run_tool('extract',False)
        self.assertEqual((self.root/FACTORY).read_bytes(),b'keep factory');self.assertEqual(manifest.read_bytes(),b'keep concert')

    def test_unsafe_member_and_bad_archive_hash(self):
        self.native();self.run_tool('pack');original=self.archive.read_bytes()
        self.archive.write_bytes(original+b'bad');self.run_tool('extract',False)
        with tarfile.open(self.archive,'w:xz') as tar:
            for name in [FACTORY,'../escape']:
                info=tarfile.TarInfo(name);info.size=1;tar.addfile(info,io.BytesIO(b'x'))
        metadata=json.loads(self.lock.read_text());metadata['sha256']=hashlib.sha256(self.archive.read_bytes()).hexdigest();self.lock.write_text(json.dumps(metadata))
        self.run_tool('extract',False);self.assertFalse((self.root.parent/'escape').exists())


if __name__=='__main__':unittest.main()
