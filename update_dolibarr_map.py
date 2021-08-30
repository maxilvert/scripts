import mysql.connector

import csv
import requests
import json
import os
import unidecode
import argparse
import sys
import re

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
    def __init__(self):
        password = os.environ['DOLIBARR_DB_PASS']
        self.mydb = mysql.connector.connect(
          host="localhost",
          user="root",
          password=password,
          database="dolibarr"
        )
        
        self.mycursor = self.mydb.cursor()
        self.url_re = re.compile('((https?:\/\/)?(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})')
    
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
    
    
    def fetch_gps_multimatch(self, features, soc, interactive):
        match = []
        for m in features:
            if soc[3].lower() == m['properties']['city'].lower():
                match.append([m['geometry']['coordinates'], m['properties']['label']])
    
        if len(match) == 0:
            raise UDM_Error("no match", soc)
        elif len(match) > 1:
            if not interactive:
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
    
    
    def extract_gps_data(self, res, soc, interactive=False):
        if 'features' not in res.keys():
            raise UDM_Error("request failed", soc)
        
        features = res['features']
        if len(features) == 0:
            raise UDM_Error("no match", soc)
        elif len(features)  > 1:
            return self.fetch_gps_multimatch(features, soc, interactive)
        else:
            return features[0]['geometry']['coordinates']
    
    
    def update_dolibarr(self, soc, gps, dry_run):
        if dry_run:
            print(f'{soc[0]} could be updated with ({gps[1]},{gps[0]})')
        else:
            update_gps_sql = "update llx_societe_extrafields \
            join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
            set latitude=%s, longitude=%s \
            where nom=%s;"
            val = (gps[1], gps[0], soc[0])
            self.mycursor.execute(update_gps_sql, val)
            self.mydb.commit()
            print(f"{self.mycursor.rowcount} record(s) affected. {soc[0]} updated with ({gps[1]},{gps[0]})")
    
    def valid_data(self, soc):
        ok = soc[1] != None and soc[2] != None and soc[3] != None
        ok = ok and soc[1] != '' and soc[2] != '' and soc[3] != ''
        if not ok:
            raise UDM_Error("invalid data", soc)
    
    def update_gps(self, args, societe_list):
        for soc in societe_list:
            try: 
                self.valid_data(soc)
                res = self.fetch_adress(soc)
                gps = self.extract_gps_data(res, soc, args.interactive)
                self.update_dolibarr(soc, gps, args.dry_run)
    
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
            
    def improve_url(self, url, presta):
        if url is None:
            return None

        res = self.url_re.search(url)
        
        
        if res is None:
            print(f'Warning: URL "{url}" not valid for "{presta}" setting it to null')
            return None
        #else:
        #    print(f'URL {url} ok for "{presta}", {res}')



        if 'http://' in url or 'https://' in url:
            return url
        else:
            return 'http://' + url

    def csv_filename(self, basename, ext, category):
        if category == "Comptoirs d'échanges":
            name = 'comptoirs'
        else:
            name = unidecode.unidecode(category.lower().replace(' ', '_'))
    
        return f"{basename}_{name}.{ext}"
    
    def gen_csv_osm(self, basename):    
        presta_with_gps_categorie_sql = "select nom,address,town,latitude,longitude,description_francais,url from llx_societe_extrafields \
                                         join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
                                         join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                                         join llx_categorie on llx_categorie.rowid=fk_categorie \
                                         where latitude is not NULL and client=1 and status=1 and label=%s;"
    
        for category in self.fetch_categories():
            val = (category,)
            self.mycursor.execute(presta_with_gps_categorie_sql, val)
            presta = self.mycursor.fetchall()
            with open(self.csv_filename(basename, 'csv', category), 'w') as csvfile:
                writer = csv.writer(csvfile, delimiter=';', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(("nom","adresse","commune","latitude", "longitude", "description", "url"))
                for p in presta:
                    try:
                        if self.valid_gps(p):
                            plist = list(p)
                            plist[6] = self.improve_url(plist[6], plist[0])
                            writer.writerow(plist)
                    except UDM_Error as e:
                        print(e.message)

    def gen_json_gogo(self, basename):    
        presta_with_gps_sql = "select nom,address,town,latitude,longitude,description_francais,url from llx_societe_extrafields \
                                         join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
                                         where latitude is not NULL and client=1 and status=1;"
    
        category_sql = "select label from llx_societe \
                           join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                           join llx_categorie on llx_categorie.rowid=fk_categorie \
                           where nom=%s;"

        self.mycursor.execute(presta_with_gps_sql)
        presta = self.mycursor.fetchall()
        all_presta = []
        for p in presta:

            self.mycursor.execute(category_sql, (p[0],))
            category = self.mycursor.fetchall()
            if category == []:
                print(f'Warning: no category for presta "{p[0]}"')
            try:
                if self.valid_gps(p):
                    to_add = {}
                    to_add['id'] = p[0]
                    to_add['address'] = p[1] 
                    to_add['town'] = p[2] 
                    to_add['latitude'] = p[3]
                    to_add['longitude'] = p[4]
                    to_add['description'] = p[5]
                    to_add['url'] = self.improve_url(p[6], p[0])
                    to_add['category'] = [cat[0] for cat in category]
                    all_presta.append(to_add)
            except UDM_Error as e:
                print(e.message)
        json_dict = {}
        json_dict['license'] = 'To be determined'
        json_dict['source'] = 'De Main en Main Dolibarr database'
        json_dict['network'] = all_presta

        with open(basename + '.json', 'w') as json_file:
            json_file.write(json.dumps(json_dict, ensure_ascii=False))




def export(args):
    ddbm = dolibarr_DB_manager()
    if args.format == 'csv':
        ddbm.gen_csv_osm(args.output)
    elif args.format == 'json':
        ddbm.gen_json_gogo(args.output)


def update(args):
    ddbm = dolibarr_DB_manager()
    list_soc = ddbm.fetch_societe_no_gps(only_presta=True)
    ddbm.update_gps(args, list_soc)

def status(args):
    ddbm = dolibarr_DB_manager()
    list_soc = ddbm.fetch_societe_no_gps(only_presta= not args.show_all)
    ddbm.print_soc(list_soc)

def build_parser():
    # create the top-level parser
    parser = argparse.ArgumentParser(prog='manage_dolibarr_db')
    subparsers = parser.add_subparsers(help='sub-command help')
    # create the parser for the "status" command
    parser_status = subparsers.add_parser('status', help='Shows all companies (only presta by default) with no valid GPS data')
    parser_status.add_argument('-a', '--show_all', help='Shows all companies without valid GPS data', action="store_true")
    parser_status.set_defaults(func=status)

    # create the parser for the "export" command
    parser_export = subparsers.add_parser('export', help='Export data from the Dolibarr DB')
    parser_export.add_argument('-f', '--format', type=str, default="json", choices=['json', 'csv'], help='Format of the file generated (default json)')
    parser_export.add_argument('-o', '--output', type=str, default="Prestataires_gps", help='Filename for the data exported (default Prestataires_gps)')
    parser_export.set_defaults(func=export)

    # create the parser for the "update" command
    parser_update = subparsers.add_parser('update', help='Update the Dolibarr DB with GPS info')
    parser_update.add_argument('-i', '--interactive', help='Equivalent to --update_db_with_gps_info but with interactive choice when several matches are available', action="store_true")
    parser_update.add_argument('-d', '--dry_run', help='Shows all modifications that would be committed but dolibarr DB remains untouched', action="store_true")
    parser_update.set_defaults(func=update)


    return parser

if __name__ == "__main__":
    p =  build_parser()
    if len(sys.argv[1:]) == 0:
        p.print_help(sys.stderr)
        sys.exit(1)
    
    args = p.parse_args(sys.argv[1:])
    if args.func != None:
        args.func(args)

    

        
