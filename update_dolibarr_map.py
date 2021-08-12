import mysql.connector

import csv
import requests
import json
import os
import unidecode
import argparse
import sys

class UDM_Error(Exception):
    def __init__(self, message, societe=None, match=None):
        if societe is None:
            self.message = message
        else:
            self.message = f'[{self.soc_type(societe)}] Error: {message} for "{societe[0]}", address ({societe[1]}), postcode ({societe[2]}) and town ({societe[3]}), gps info not updated'
            if match is not None:
                possible_match = ''
                for val in match:
                    possible_match += f'\n\tPossible match : {val[1]}'
                self.message += possible_match

    def soc_type(self, soc):
        if soc[4] == 1 and soc[5] == 1:
            return 'presta'
        elif soc[4] == 1 and soc[5] == 0:
            return 'former presta'
        elif soc[4] == 2 and soc[5] == 1:
            return 'prospect'
        elif soc[4] == 2 and soc[5] == 0:
            return 'prospect closed ??'
        else: 
            return '??'

class dolibarr_DB_manager:
    def __init__(self, args):
        password = os.environ['DOLIBARR_DB_PASS']
        self.mydb = mysql.connector.connect(
          host="localhost",
          user="root",
          password=password,
          database="dolibarr"
        )
        
        self.mycursor = self.mydb.cursor()
        self.status = args.status
        self.show_all = args.show_all
        self.update_db_with_gps_info = args.update_db_with_gps_info
        self.interactive_update_db_with_gps_info = args.interactive_update_db_with_gps_info
    
    def fetch_societe_no_gps(self, only_presta):
        sql_request = "select nom,address,zip,town,client,status from llx_societe_extrafields \
        join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
        where latitude is null"
    
        condition = ''
        if only_presta:
            condition = 'and client=1 and status=1'
        
        sql_request = f"{sql_request} {condition};"
        self.mycursor.execute(sql_request)
    
        return self.mycursor.fetchall()
    
    def print_soc(self, soc_list):
        if len(soc_list) == 0:
            print("GPS data valid for all companies")
        else:
            print(f"{len(soc_list)} companies without valid GPS data:")
            for s in soc_list:
                print(f'{s[0]}')
    
    def fetch_adress(self, societe):
        payload = {'q' : societe[1], 'postcode': societe[2]}
        r = requests.get('https://api-adresse.data.gouv.fr/search/', params=payload)
        return json.loads(r.text)
    
    def convert_choice(self, choice):
        try:
            return int(choice)
        except ValueError:
            return -1
    
    
    def fetch_gps_multimatch(self, features, soc):
        match = []
        for m in features:
            if soc[3].lower() == m['properties']['city'].lower():
                match.append([m['geometry']['coordinates'], m['properties']['label']])
    
        if len(match) == 0:
            raise UDM_Error("no match", soc)
        elif len(match) > 1:
            if not self.interactive_update_db_with_gps_info:
                raise UDM_Error(f"{len(match)} matches", soc, match)
            else:
                print(f'{len(match)} matches for "{soc[0]}" with address "{soc[1]}" and town "{soc[3]}"\nPossible match:')
                for proposition, val in enumerate(match):
                    print(f'[{proposition}] : {val[1]}')
    
                print(f'[{len(match)}] : none of the proposition is correct')
                choice = input('Your choice: ')
                choice_id = self.convert_choice(choice)
                if choice_id >=0 and choice_id < len(match):
                    return match[choice_id][0]
                else:
                    raise UDM_Error("no match", soc)
        else:
            return match[0][0]
    
    
    def extract_gps_data(self, res, soc):
        if 'features' not in res.keys():
            raise UDM_Error("request failed", soc)
        
        features = res['features']
        if len(features) == 0:
            raise UDM_Error("no match", soc)
        elif len(features)  > 1:
            return self.fetch_gps_multimatch(features, soc)
        else:
            return features[0]['geometry']['coordinates']
    
    
    def update_dolibarr(self, soc, gps):
        update_gps_sql = "update llx_societe_extrafields join llx_societe on \
        llx_societe_extrafields.fk_object = llx_societe.rowid set latitude=%s, \
        longitude=%s where nom=%s;"
        val = (gps[1], gps[0], soc[0])
        self.mycursor.execute(update_gps_sql, val)
        self.mydb.commit()
        print(self.mycursor.rowcount, "record(s) affected for %s"%soc[0])
    
    def valid_data(self, soc):
        ok = soc[1] != None and soc[2] != None and soc[3] != None
        ok = ok and soc[1] != '' and soc[2] != '' and soc[3] != ''
        if not ok:
            raise UDM_Error("invalid data", soc)
    
    def update_gps(self, societe_list):
        for soc in societe_list:
            try: 
                self.valid_data(soc)
                res = self.fetch_adress(soc)
                gps = self.extract_gps_data(res, soc)
                self.update_dolibarr(soc, gps)
    
            except UDM_Error as e:
                print(e.message)
    
    def fetch_categories(self):
        categories_sql= "select label from llx_categorie;"
        self.mycursor.execute(categories_sql)
        cat = self.mycursor.fetchall()
        res = []
        for c in cat:
            if c[0] != "Adresse d'activité" and c[0] != "Etiquettes" and c[0] != 'Frestaurant':  #TODO remove category 'Frestaurant'
                res.append(c[0])
        return res
    
    def valid_gps(self, presta):
    
        try:
            lon = float(presta[4])
            lat = float(presta[3])
        except ValueError:
            raise UDM_Error(f'Gen_csv error: GPS coordinate ({presta[4]},{presta[3]}) not valid for "{presta[0]}" => not in CSV file')
    
    
        if lon > -2 and lon < 1 and lat > 42 and lat < 44:
            return True
        else:
            raise UDM_Error(f'Gen_csv error: GPS coordinate ({lon},{lat}) not in Bearn for "{presta[0]}" => not in CSV file')
            
    def csv_filename(self, category):
        if category == "Comptoirs d'échanges":
            name = 'comptoirs'
        else:
            name = unidecode.unidecode(category.lower().replace(' ', '_'))
    
        return f"Prestataires_gps_{name}.csv"
    
    def gen_csv_osm(self):    
        presta_with_gps_categorie= "select nom,address,town,latitude,longitude,description_francais from llx_societe_extrafields \
                                         join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
                                         join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                                         join llx_categorie on llx_categorie.rowid=fk_categorie \
                                         where latitude is not NULL and client=1 and status=1 and label=%s;"
    
        for category in self.fetch_categories():
            val = (category,)
            self.mycursor.execute(presta_with_gps_categorie, val)
            presta = self.mycursor.fetchall()
            with open(self.csv_filename(category), 'w') as csvfile:
                writer = csv.writer(csvfile, delimiter=';', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(("nom","adresse","commune","latitude", "longitude", "description"))
                for p in presta:
                    try:
                        if self.valid_gps(p):
                            writer.writerow(p)
                    except UDM_Error as e:
                        print(e.message)
    def run(self):
        if self.status:
            list_soc = self.fetch_societe_no_gps(only_presta=True)
            self.print_soc(list_soc)

        if self.show_all:
            list_soc = self.fetch_societe_no_gps(only_presta=False)
            self.print_soc(list_soc)

        if self.update_db_with_gps_info or self.interactive_update_db_with_gps_info:
            list_soc = self.fetch_societe_no_gps(only_presta=True)
            self.update_gps(list_soc)


def build_parser():
    # create the top-level parser
    parser = argparse.ArgumentParser(prog='manage_dolibarr_db')
    parser.add_argument('-s', '--status', help='Shows all presta without valid GPS data (true by default)', action="store_true")
    parser.add_argument('-a', '--show_all', help='Shows all companies without valid GPS data', action="store_true")
    parser.add_argument('-u', '--update_db_with_gps_info', help='Fetch GPS info for Dolibarr entries without GPS info and update Dolibarr DB for these entries', action="store_true")
    parser.add_argument('-i', '--interactive_update_db_with_gps_info', help='Equivalent to --update_db_with_gps_info but with interactive choice when several matches are available', action="store_true")

    return parser

def manage_default(args):
    if not args.status and not args.update_db_with_gps_info and not args.show_all and not args.update_db_with_gps_info:
        args.status = True
    return args
        

if __name__ == "__main__":
    p =  build_parser()
    args = p.parse_args(sys.argv[1:])
    args = manage_default(args)
    ddbm = dolibarr_DB_manager(args)
    ddbm.run()
    

        
