import unittest
from core import validate_model_signature
class ModelBindingTests(unittest.TestCase):
    def setUp(self):self.signature=[1077,1040,120,[520,250,550,700],'euclidean_px'];self.model={'signature':self.signature}
    def test_calibrated_dimensions_accepted(self):validate_model_signature(self.model,list(self.signature))
    def test_reproduces_user_resize_and_explains_it(self):
        with self.assertRaisesRegex(ValueError,'客户区宽度.*1080.*1077.*客户区高度.*1045.*1040'):
            validate_model_signature(self.model,[1080,1045,120,[520,250,550,700],'euclidean_px'])
    def test_same_size_different_dpi_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'DPI'):validate_model_signature(self.model,[1077,1040,144,[520,250,550,700],'euclidean_px'])
    def test_changed_roi_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'ROI'):validate_model_signature(self.model,[1077,1040,120,[0,0,550,700],'euclidean_px'])
