import unittest
import sys
import copy
from pprint import pprint

import update_dolibarr_map as udm

dmem = ('De Main en Main', 'Villa des violettes, impasse Odeau', 'Billère', 43.3022, -0.39749, "Association porteuse de la Monnaie Locale Complémentaire du Béarn, la T!nda. Comptoir d'échange sur événement ou sur rendez-vous (téléphoner).")

aquiu = ('Aquiu', '28 rue Carnot', '64000', 'Pau', 1, 1)
res_aquiu = {'type': 'FeatureCollection', 'version': 'draft', 'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-0.369283, 43.301366]}, 'properties': {'label': '28 Rue Carnot 64000 Pau', 'score': 0.8840318181818182, 'housenumber': '28', 'id': '64445_0790_00028', 'name': '28 Rue Carnot', 'postcode': '64000', 'citycode': '64445', 'x': 426532.61, 'y': 6250524.22, 'city': 'Pau', 'context': '64, Pyrénées-Atlantiques, Nouvelle-Aquitaine', 'type': 'housenumber', 'importance': 0.72435, 'street': 'Rue Carnot'}}], 'attribution': 'BAN', 'licence': 'ETALAB-2.0', 'query': '28 rue Carnot', 'filters': {'postcode': '64000'}, 'limit': 5}
 
res_aquiu_multi_ok = copy.deepcopy(res_aquiu)
res_aquiu_multi_ok['features'].append(copy.deepcopy(res_aquiu['features'][0])) 
res_aquiu_multi_ok['features'][0]['properties']['city'] = 'Billère'

class fake_args:
    def __init__(self, status=True, show_all=False, update_db_with_gps_info=False):
        self.status = status
        self.show_all = show_all
        self.update_db_with_gps_info = update_db_with_gps_info

class test_update_dolibarr_map(unittest.TestCase):
  
    def test_db_connection(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        self.assertTrue(ddbm.mydb is not None and ddbm.mycursor is not None,  'Connection issue with Dolibarr database')
      
    def test_fetch_categories(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        res = ddbm.fetch_categories()
        expected = ['Agriculture', 'Alimentation', 'Art et culture', 'Artisanat',
                'Associations', 'Autre', 'Commerce', "Comptoirs d'échanges", 
                'Habitat', 'Marchés', 'Restauration', 'Santé', 'Service', 
                'Sport et loisirs', 'Transport']
        for i in res:
            self.assertTrue(res==expected,  f'{res}\ndifferent from\n{expected}')
      
    def test_valid_gps_1(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(dmem)
        inputs[3] = 'lol'
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.valid_gps(inputs)
  
        self.assertTrue(f'Gen_csv error: GPS coordinate ({inputs[4]},{inputs[3]}) not valid for "{inputs[0]}" => not in CSV file' in str(context.exception))
    
    def test_valid_gps_2(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(dmem)
        inputs[3] = '49.3'
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.valid_gps(inputs)
  
        self.assertTrue(f'Gen_csv error: GPS coordinate ({inputs[4]},{inputs[3]}) not in Bearn for "{inputs[0]}" => not in CSV file' in str(context.exception))
  
    def test_valid_gps_3(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(dmem)
        res = ddbm.valid_gps(inputs)
  
        self.assertTrue(res == True, f'GPS data not valid for {inputs}')
    
    def test_csv_name_1(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = "Comptoirs d'échanges"
        name = 'comptoirs'
        expected = f"Prestataires_gps_{name}.csv"
        res = ddbm.csv_filename(inputs)
  
        self.assertTrue(res == expected, f'"{expected}" was expected, got "{res}" for input "{inputs}"')
    
    def test_csv_name_2(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = "Art et culture"
        name = 'art_et_culture'
        expected = f"Prestataires_gps_{name}.csv"
        res = ddbm.csv_filename(inputs)
  
        self.assertTrue(res == expected, f'"{expected}" was expected, got "{res}" for input "{inputs}"')
    
    #def test_fetch_adress(self):
    #    inputs = list(aquiu)
    #    res = udm.fetch_adress(inputs)
  
    #    self.assertTrue(res == res_aquiu, f'data fetched {res} not corresponding to expeceted {res_aquiu}')
    
    def gen_UDM_Error_message(self, inputs, message, match=None):
        msg = f'[presta] Error: {message} for "{inputs[0]}", address ({inputs[1]}), postcode ({inputs[2]}) and town ({inputs[3]}), gps info not updated'
        if match is None:
            return msg
        else:
            possible_match = ''
            for val in match:
                possible_match += f'\n\tPossible match : {val["properties"]["label"]}'
            return msg + possible_match
  
  
    def test_extract_gps_data_fail(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        expected = self.gen_UDM_Error_message(inputs, 'request failed')
        
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.extract_gps_data({}, inputs)
        
        self.assertTrue(expected == context.exception.message)
  
    def test_extract_gps_data_nomatch(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        res_aquiu_nomatch = copy.deepcopy(res_aquiu)
        res_aquiu_nomatch['features'] = []
  
        expected = self.gen_UDM_Error_message(inputs, 'no match')
  
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.extract_gps_data(res_aquiu_nomatch, inputs)
  
        self.assertTrue(expected == context.exception.message)
  
    def test_extract_gps_data_ok(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        expected = [-0.369283, 43.301366]
        res = ddbm.extract_gps_data(res_aquiu, inputs)
  
        self.assertTrue(expected == res, f'"{expected}" was expected, got "{res}" for input "{inputs}"')
  
    def test_fetch_gps_multimatch_nomatch(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        res_aquiu_multi_nomatch = copy.deepcopy(res_aquiu_multi_ok)
        res_aquiu_multi_nomatch['features'][1]['properties']['city'] = 'Lons'
        expected = self.gen_UDM_Error_message(inputs, 'no match')
  
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.fetch_gps_multimatch(res_aquiu_multi_nomatch['features'], inputs)
  
        self.assertTrue(expected == context.exception.message, f'"{expected}" was expected, got "{context.exception.message}" for input "{inputs}"')
  
    def test_fetch_gps_multimatch_multimatch(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        res_aquiu_multi_multimatch = copy.deepcopy(res_aquiu_multi_ok)
        res_aquiu_multi_multimatch['features'][0]['properties']['city'] = 'Pau'
        expected = self.gen_UDM_Error_message(inputs, '2 matches', res_aquiu_multi_multimatch['features'])
  
        with self.assertRaises(udm.UDM_Error) as context:
            ddbm.fetch_gps_multimatch(res_aquiu_multi_multimatch['features'], inputs)
  
        self.assertTrue(expected == context.exception.message, f'"{expected}" was expected, got "{context.exception.message}" for input "{inputs}"')
  
    def test_fetch_gps_multimatch_ok(self):
        args = fake_args()
        ddbm = udm.dolibarr_DB_manager(args)
        inputs = list(aquiu)
        expected = [-0.369283, 43.301366]
        res = ddbm.fetch_gps_multimatch(res_aquiu_multi_ok['features'], inputs)
  
        self.assertTrue(expected == res, f'"{expected}" was expected, got "{res}" for input "{inputs}"')

def runTest(method_to_test):
  if len(method_to_test) == 0:
    suite = test_all()
  else:
    suite = unittest.TestSuite()
    for i in method_to_test:
      suite.addTest(test_update_dolibarr_map(i))

  unittest.TextTestRunner(verbosity=2).run(suite)
  
def test_all():
  return unittest.TestLoader().loadTestsFromTestCase(test_update_dolibarr_map)
  
if __name__ == "__main__":
  """Without argument, all tests are executed otherwise only methods put as argument are executed"""
  runTest(sys.argv[1:])
  
