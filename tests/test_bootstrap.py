import contextlib,hashlib,io,json,stat,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap as b
class BootstrapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def archive(self,name='folder/data.txt',payload=b'data',mode=None):
  p=self.root/'sample.zip'
  with zipfile.ZipFile(p,'w') as z:
   info=zipfile.ZipInfo(name)
   if mode:info.external_attr=mode<<16
   z.writestr(info,payload)
  return p
 def test_valid_archive(self):
  b.extract_checked(self.archive(),self.root/'out');self.assertEqual((self.root/'out/folder/data.txt').read_bytes(),b'data')
 def test_parent_traversal(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('../outside'),self.root/'out')
  self.assertFalse((self.root/'outside').exists())
 def test_backslash_traversal(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive(r'..\outside'),self.root/'out')
 def test_absolute_path(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('/outside'),self.root/'out')
 def test_alternate_stream(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('file:stream'),self.root/'out')
 def test_reserved_windows_name(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('CON.txt'),self.root/'out')
 def test_trailing_dot(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('folder./file'),self.root/'out')
 def test_symlink(self):
  with self.assertRaises(ValueError):b.extract_checked(self.archive('link',mode=stat.S_IFLNK|0o777),self.root/'out')
 def test_duplicate_case_path(self):
  p=self.archive('A.txt')
  with zipfile.ZipFile(p,'a') as z:z.writestr('a.txt','other')
  with self.assertRaises(ValueError):b.extract_checked(p,self.root/'out')
 def test_no_partial_extraction_before_rejection(self):
  p=self.archive('good.txt')
  with zipfile.ZipFile(p,'a') as z:z.writestr('../bad','bad')
  with self.assertRaises(ValueError):b.extract_checked(p,self.root/'out')
  self.assertFalse((self.root/'out/good.txt').exists())
 def test_size_limit(self):
  with patch.object(b,'MAX_UNPACKED',2):
   with self.assertRaises(ValueError):b.extract_checked(self.archive(),self.root/'out')
 def test_existing_destination_not_overwritten(self):
  out=self.root/'out';out.mkdir();(out/'keep').write_text('old')
  with self.assertRaises(FileExistsError):b.extract_checked(self.archive(),out)
  self.assertEqual((out/'keep').read_text(),'old')
 def test_digest_checks_real_bytes(self):
  p=self.root/'file';p.write_bytes(b'known')
  row={'size':5,'sha256':hashlib.sha256(b'known').hexdigest()};b.verify_archive(p,row)
  p.write_bytes(b'other')
  with self.assertRaises(ValueError):b.verify_archive(p,row)
 def test_size_mismatch(self):
  p=self.root/'file';p.write_bytes(b'known')
  with self.assertRaises(ValueError):b.verify_archive(p,{'size':1,'sha256':'0'*64})
 def test_https_only(self):
  with self.assertRaises(ValueError):b.safe_url('http://github.com/project')
 def test_unapproved_host(self):
  with self.assertRaises(ValueError):b.safe_url('https://github.com.invalid/project')
 def test_embedded_credentials_rejected(self):
  with self.assertRaises(ValueError):b.safe_url('https://'+':'.join(('user','pass'))+'@'+'github.com/project')
 def test_unknown_port_rejected(self):
  with self.assertRaises(ValueError):b.safe_url('https://github.com:444/project')
 def test_redirect_checked(self):
  with self.assertRaises(ValueError):b.Redirects().redirect_request(None,None,302,'',{},'https://invalid.example/file')
 def metadata(self):
  r=b.manifest('gf2');return r,{'tag_name':r['tag'],'draft':False,'prerelease':False,'assets':[{'name':r['asset'],'size':r['size'],'digest':'sha256:'+r['sha256'],'browser_download_url':b.release_url(r)}]}
 def test_exact_release_accepted(self):
  r,m=self.metadata();b.check_metadata(r,m)
 def test_missing_digest_blocked(self):
  r,m=self.metadata();m['assets'][0].pop('digest')
  with self.assertRaises(ValueError):b.check_metadata(r,m)
 def test_changed_digest_blocked(self):
  r,m=self.metadata();m['assets'][0]['digest']='sha256:'+'0'*64
  with self.assertRaises(ValueError):b.check_metadata(r,m)
 def test_wrong_tag_blocked(self):
  r,m=self.metadata();m['tag_name']='v999.0.0'
  with self.assertRaises(ValueError):b.check_metadata(r,m)
 def test_changed_asset_url_blocked(self):
  r,m=self.metadata();m['assets'][0]['browser_download_url']='https://github.com/other/file'
  with self.assertRaises(ValueError):b.check_metadata(r,m)
 def test_draft_blocked(self):
  r,m=self.metadata();m['draft']=True
  with self.assertRaises(ValueError):b.check_metadata(r,m)
 def test_preview_does_not_download(self):
  with patch.object(b,'open_url',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
   self.assertEqual(b.main(['download','--game','gf2']),0)
 def test_initialize_preserves_config(self):
  (self.root/'config.example').mkdir();(self.root/'config.example/example.json').write_text('{}')
  with patch.object(b,'PROJECT',self.root):
   self.assertEqual(b.initialize()['created'],['example.json'])
   (self.root/'config.local/example.json').write_text('user-change')
   self.assertEqual(b.initialize()['created'],[])
  self.assertEqual((self.root/'config.local/example.json').read_text(),'user-change')
if __name__=='__main__':unittest.main()
