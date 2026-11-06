import unittest
import render_home

class ModelSelectionDescription(unittest.TestCase):
    def row(self, **values):
        return dict(id='publisher/model-4b', name='model-4b', author='publisher', slug='publisher-model-4b', task='text-generation', params_h='4.0B', license='apache-2.0', trending=3, downloads=20, likes=2, **values)

    def test_selection_fields_reach_real_catalog_record(self):
        _, rows = render_home.normalize({'models':[self.row()]}, 'https://modelradar.kymatalabs.com/')
        description = rows[0]['description']
        for expected in ['text-generation', '4.0B', 'apache-2.0']:
            self.assertIn(expected, description)

    def test_missing_license_or_parameters_are_not_inferred(self):
        row = self.row(); row.update(license=None, params_h=None, task='—')
        _, rows = render_home.normalize({'models':[row]}, 'https://modelradar.kymatalabs.com/')
        self.assertIn('License not supplied', rows[0]['description'])
        self.assertIn('Parameter count not supplied', rows[0]['description'])
        self.assertIn('Task not supplied', rows[0]['description'])

if __name__ == '__main__': unittest.main()
