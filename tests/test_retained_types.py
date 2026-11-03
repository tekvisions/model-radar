from pathlib import Path
import json,tempfile,unittest
import url_lifecycle

ROOT=Path(url_lifecycle.__file__).parent
REAL=json.loads((ROOT/'url.lifecycle').read_text())
class RetainedTypeTests(unittest.TestCase):
 def fixture(self,d):
  root=Path(d);entry=REAL['retained_references'][0];policy={k:REAL[k] for k in ['host','site_name','detail_prefix']};policy.update(captured_public_urls=['https://'+REAL['host']+'/',entry['canonical_url']],retained_references=[entry]);(root/'url.lifecycle').write_text(json.dumps(policy));key='models' if REAL['detail_prefix']=='m' else 'items';(root/'data.json').write_text(json.dumps({key:[{'slug':entry['slug']}]}));(root/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://'+REAL['host']+'/</loc></url></urlset>');path=root/entry['canonical_url'].split('.com/',1)[1]/'index.html';path.parent.mkdir(parents=True);path.write_text('ranked fixture');return root,path,key,entry
 def test_ranked_record_owns_its_existing_page(self):
  with tempfile.TemporaryDirectory() as d:
   root,path,key,entry=self.fixture(d);self.assertEqual(url_lifecycle.render_retained(root),0);self.assertEqual(path.read_text(),'ranked fixture')
 def test_missing_record_gets_correct_site_type_and_no_rank(self):
  with tempfile.TemporaryDirectory() as d:
   root,path,key,entry=self.fixture(d);(root/'data.json').write_text(json.dumps({key:[]}));self.assertEqual(url_lifecycle.render_retained(root),1);text=path.read_text();self.assertIn('retained reference | '+REAL['site_name'],text);self.assertIn('outside the current ranked discovery snapshot',text);self.assertIn('CreativeWork' if key=='models' else 'SoftwareSourceCode',text);self.assertEqual(url_lifecycle.verify(root)['explicitly_retired'],[])
 def test_wrong_route_prefix_stays_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root,path,key,entry=self.fixture(d);(root/'data.json').write_text(json.dumps({key:[]}));policy=json.loads((root/'url.lifecycle').read_text());policy['detail_prefix']='p' if key=='models' else 'm';(root/'url.lifecycle').write_text(json.dumps(policy))
   with self.assertRaisesRegex(ValueError,'unsafe or mismatched'):url_lifecycle.render_retained(root)
 def test_symlink_output_stays_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root,path,key,entry=self.fixture(d);(root/'data.json').write_text(json.dumps({key:[]}));outside=root/'outside.html';outside.write_text('unchanged');path.unlink();path.symlink_to(outside)
   with self.assertRaisesRegex(ValueError,'symlinks'):url_lifecycle.render_retained(root)
   self.assertEqual(outside.read_text(),'unchanged')
if __name__=='__main__':unittest.main()
