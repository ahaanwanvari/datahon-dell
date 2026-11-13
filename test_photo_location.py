import csv,hashlib,io
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image,ImageFilter
from photo_location import PhotoLocator
from scenarios import Scenarios


class PhotoLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data';self.data.mkdir();(self.data/'images').mkdir()
        self.rows=[]
        for i in range(3):
            image=Image.fromarray(np.random.default_rng(i).integers(0,256,(160,160,3),dtype=np.uint8)).filter(ImageFilter.GaussianBlur(1))
            path=self.data/f'images/{i}.png';image.save(path)
            self.rows.append({'image_id':str(i),'image_path':f'images/{i}.png','latitude':str(30+i*.1),'longitude':'-95','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'locality':f'Place {i}'})
        self.write_manifest();self.locator=PhotoLocator(self.root/'state',self.data)
    def write_manifest(self):
        with (self.data/'image_metadata.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=self.rows[0]);writer.writeheader();writer.writerows(self.rows)
    def test_original_and_reencoded_content(self):
        raw=(self.data/'images/0.png').read_bytes()
        result=self.locator.match(raw)
        self.assertEqual(result['method'],'exact_file');self.assertEqual(result['suggested']['lat'],30)
        with Image.open(io.BytesIO(raw)) as image:
            buffer=io.BytesIO();image.save(buffer,format='PNG',compress_level=0)
        self.assertEqual(self.locator.match(buffer.getvalue())['method'],'exact_pixels')
    def test_resized_jpeg_and_unrelated_photo(self):
        with Image.open(self.data/'images/1.png') as image:
            image=image.resize((100,100));buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=55)
        result=self.locator.match(buffer.getvalue())
        self.assertEqual(result['method'],'visual_copy');self.assertEqual(result['suggested']['image_id'],'1')
        buffer=io.BytesIO();Image.new('RGB',(160,160),(255,0,255)).save(buffer,format='PNG')
        self.assertEqual(self.locator.match(buffer.getvalue())['method'],'none')
    def test_duplicate_content_at_different_coordinates_is_ambiguous(self):
        self.rows[1].update(image_path=self.rows[0]['image_path'],sha256=self.rows[0]['sha256'])
        self.write_manifest()
        result=self.locator.match((self.data/'images/0.png').read_bytes())
        self.assertTrue(result['ambiguous']);self.assertIsNone(result['suggested']);self.assertEqual(len(result['candidates']),2)
    def test_reference_path_is_registered(self):
        with self.assertRaises(ValueError):self.locator.reference('../../secret')


class ConfirmationTests(unittest.TestCase):
    def test_unconfirmed_location_cannot_start_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost','test',None);identity='a'*32;store.folder(identity).mkdir()
            store.write(identity,{'id':identity,'state':'ready'})
            with self.assertRaisesRegex(ValueError,'Confirm the photo location'):store.start_plan(identity,'30, -95')
            with self.assertRaises(ValueError):store.confirm_location(identity,float('nan'),-95)
            confirmed=store.confirm_location(identity,30,-95)
            self.assertEqual(confirmed['lat'],30)
            self.assertEqual(store.read(identity)['confirmed_location']['method'],'user_confirmed_map_pin')
    def test_changing_confirmed_pin_clears_old_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost','test',None);identity='b'*32;store.folder(identity).mkdir()
            store.write(identity,{'id':identity,'state':'planned','plan':{'stale':True}})
            store.confirm_location(identity,30,-95)
            self.assertNotIn('plan',store.read(identity));self.assertEqual(store.read(identity)['state'],'ready')


if __name__=='__main__':unittest.main()
