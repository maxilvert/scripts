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
        self.mydb = mysql.connector.connect(
          host=os.environ['DOLIBARR_DB_HOST'],
          user=os.environ['DOLIBARR_DB_USER'],
          password=os.environ['DOLIBARR_DB_PASS'],
          database=os.environ['DOLIBARR_DB_DATABASE'],
        )

        self.mycursor = self.mydb.cursor()
        self.url_re = re.compile(
            '((https?:\/\/)?(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})')

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
        payload = {'q': societe[1], 'postcode': societe[2]}
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
                print(
                    f'{len(match)} matches for "{soc[0]}" with address "{soc[1]}" and town "{soc[3]}"\nPossible match:')
                for proposition, val in enumerate(match):
                    print(f'[{proposition}] : {val[1]}')

                print(f'[{len(match)}] : none of the proposition is correct')
                choice = input('Your choice: ')
                choice_id = self.convert_choice(choice)
                if choice_id >= 0 and choice_id < len(match):
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
        elif len(features) > 1:
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
        categories_sql = "select label from llx_categorie;"
        self.mycursor.execute(categories_sql)
        cat = self.mycursor.fetchall()
        res = []
        for c in cat:
            if c[0] != "Adresse d'activité" and c[0] != "Etiquettes" and c[
                0] != 'Frestaurant':  # TODO remove category 'Frestaurant'
                res.append(c[0])
        return res

    def valid_gps(self, presta):

        try:
            lon = float(presta[4])
            lat = float(presta[3])
        except ValueError:
            raise UDM_Error(
                f'Gen_csv error: GPS coordinate ({presta[4]},{presta[3]}) not valid for "{presta[0]}" => not in CSV file')

        if lon > -2 and lon < 1 and lat > 42 and lat < 44:
            return True
        else:
            raise UDM_Error(
                f'Gen_csv error: GPS coordinate ({lon},{lat}) not in Bearn for "{presta[0]}" => not in CSV file')

    def improve_url(self, url, presta):
        if url is None:
            return None

        res = self.url_re.search(url)

        if res is None:
            print(f'Warning: URL "{url}" not valid for "{presta}" setting it to "no_url"')
            return 'no_url'

        if 'http://' in url or 'https://' in url:
            return url
        else:
            return 'http://' + url

    def csv_filename(self, basename, category):
        if category == "Comptoirs d'échanges":
            name = 'comptoirs'
        else:
            name = unidecode.unidecode(category.lower().replace(' ', '_'))

        return f"{basename}_{name}.csv"

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
            with open(self.csv_filename(basename, category), 'w') as csvfile:
                writer = csv.writer(csvfile, delimiter=';', quotechar='|', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(("nom", "adresse", "commune", "latitude", "longitude", "description", "url"))
                for p in presta:
                    try:
                        if self.valid_gps(p):
                            plist = list(p)
                            plist[6] = self.improve_url(plist[6], plist[0])
                            writer.writerow(plist)
                    except UDM_Error as e:
                        print(e.message)

    def gen_json_gogo(self, basename):    
        presta_with_gps_sql = """SELECT
	sp.lastname AS nom,
	TRIM(TRIM('\n' FROM SUBSTRING_INDEX(REPLACE(sp.address, '\r\n', '\n'), '/', -1))) AS address,
	TRIM(SUBSTRING_INDEX(sp.town, '/', -1)) AS town,
	IFNULL(spe.latitude, '') AS latitude,
	IFNULL(spe.longitude, '') AS longitude,
	IFNULL(REPLACE(spe.description_francais, '\r\n', '\n'), '') AS description_francais,
	IFNULL(s.url, '') AS url
FROM llx_societe s
JOIN llx_socpeople sp ON s.rowid = sp.fk_soc
JOIN llx_socpeople_extrafields spe ON sp.rowid = spe.fk_object
JOIN llx_categorie_contact cc ON sp.rowid = cc.fk_socpeople
	AND cc.fk_categorie = 370 -- Adresse d'activité
WHERE s.code_client IS NOT NULL AND s.client = 1 AND s.status = 1
;
"""
    
        category_sql = """SELECT label FROM llx_socpeople
JOIN llx_categorie_contact ON llx_categorie_contact.fk_socpeople = llx_socpeople.rowid
JOIN llx_categorie ON llx_categorie.rowid = llx_categorie_contact.fk_categorie
	AND llx_categorie.fk_parent = 444 -- sous-catégorie de "Annuaire général"
WHERE lastname=%s
;
 """

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

    def latexify(self, str_in):
        str_out = str_in.replace('&', '\\&')
        str_out = str_out.replace('«', '\\og{}')
        str_out = str_out.replace('»', '\\fg{}')
        str_out = str_out.replace('<', '\\textlesser')
        str_out = str_out.replace('>', '\\textgreater')
        str_out = str_out.replace('%', '\\%')

        return str_out

    def flatten_category(self, category):
        return [c[0] for c in category]

    def format_phone(self, phone):
        num = phone.split()
        phone_out = ' '.join(num)
        if len(phone_out) == 10:
            out = ''
            for i in range(2, 11, 2):
                out += phone_out[i - 2:i] + ' '
            phone_out = out

        return phone_out

    def category_txt(self, category):
        if category == []:
            return ''
        else:
            cat = category[0]
            for c in category[1:]:
                if c != "Comptoirs d'échanges":
                    cat += ', ' + c
            return cat

    def presta_tex(self, p, category, comptoir_only):
        to_print = '\\makecell*[{{p{\\nameWidth}}}]{\n'

        # Name and category in parenthesis
        to_print += '\\textbf{%s} (%s)\\\\\n' % (self.latexify(p[0]), self.category_txt(category))
        # Add the "Comptoirs d'échange" stamp in the description if not in the
        # dedicated section to comptoirs d'échange
        if "Comptoirs d'échanges" in category and not comptoir_only:
            to_print += "\\colorbox{colorComptoir}{\\textbf{Comptoirs d'échanges}}\\\\\n"
        # Description if any
        if p[3] is not None and p[3] != '':
            to_print += '%s\n' % (self.latexify(p[3]))
        to_print += '}\n&\n'
        to_print += '\\makecell*[{{p{\\dataWidth}}}]{\n'
        # if street available, print it
        if p[1] is not None and p[1] != '':
            to_print += '%s, ' % (p[1])
        # zip and town
        to_print += '%s %s\\\\\n' % (p[6], p[2])
        # phone if available
        if p[5] is not None:
            to_print += '%s\\\\\n' % (self.format_phone(p[5]))
        # Website if available
        if p[4] is not None and p[4] != '':
            to_print += '{\\small \\url{%s}}\n' % (self.latexify(self.improve_url(p[4], p[0])))
        to_print += '}\n\\\\\n\\hline\n'
        return to_print

    def sorting_sql(self, sorting_field):
        if sorting_field == 'nom':
            return 'nom'
        elif sorting_field == 'zip':
            return 'zip,town,nom'

    def gen_tex_alpha(self, basename, sorting_field):
        sorting_sql = self.sorting_sql(sorting_field)

        presta_sql = f"select nom,address,town,description_francais,url,phone,zip from llx_societe_extrafields \
                                         join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
                                         where client=1 and status=1\
                                         order by {sorting_sql};"

        category_sql = "select label from llx_societe \
                           join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                           join llx_categorie on llx_categorie.rowid=fk_categorie \
                           where nom=%s;"

        self.mycursor.execute(presta_sql)
        presta = self.mycursor.fetchall()
        to_print = ''
        for p in presta:
            self.mycursor.execute(category_sql, (p[0],))
            category = self.flatten_category(self.mycursor.fetchall())
            to_print += self.presta_tex(p, category, comptoir_only=False)

        with open(basename + f'_{sorting_field}_alpha.tex', 'w') as tex_file:
            tex_file.write(to_print)

    def gen_tex_category(self, basename, sorting_field, comptoir_only=True):
        sorting_sql = self.sorting_sql(sorting_field)
        presta_sql = f"select nom,address,town,description_francais,url,phone,zip from llx_societe_extrafields \
                                         join llx_societe on llx_societe_extrafields.fk_object = llx_societe.rowid \
                                         join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                                         join llx_categorie on llx_categorie.rowid=fk_categorie \
                                         where client=1 and status=1 and label=%s\
                                         order by {sorting_sql};"

        category_sql = "select label from llx_societe \
                           join llx_categorie_societe on llx_categorie_societe.fk_soc=llx_societe.rowid \
                           join llx_categorie on llx_categorie.rowid=fk_categorie \
                           where nom=%s;"

        if comptoir_only:
            category = ["Comptoirs d'échanges"]
            fname = basename + f'_{sorting_field}_comptoir.tex'
        else:
            category = self.fetch_categories()
            category.remove("Comptoirs d'échanges")
            fname = basename + f'_{sorting_field}_category.tex'

        to_print = ''
        for cat in category:
            self.mycursor.execute(presta_sql, (cat,))
            presta = self.mycursor.fetchall()
            if len(presta) > 0:
                to_print += '\\Needspace{5\\baselineskip}\n'
                to_print += '\\section*{%s}\n' % (cat)
                to_print += '\\addcontentsline{toc}{section}{%s}\n' % (cat)
                to_print += '\\begin{longtable}{|m{\\nameWidth} | m{\\dataWidth}|}\n\\hline\nNom & Coordonnées  \\\\\n\\hline\n\\endhead\n'

                for p in presta:
                    self.mycursor.execute(category_sql, (p[0],))
                    category = self.flatten_category(self.mycursor.fetchall())
                    to_print += self.presta_tex(p, category, comptoir_only)
                to_print += '\\end{longtable}\n'
                to_print += '\\vspace{2cm}\n\n'

        with open(fname, 'w') as tex_file:
            tex_file.write(to_print)

    def gen_tex_gogo(self, basename):
        self.gen_tex_alpha(basename, 'nom')
        self.gen_tex_alpha(basename, 'zip')
        self.gen_tex_category(basename, 'nom', comptoir_only=True)
        self.gen_tex_category(basename, 'zip', comptoir_only=True)
        self.gen_tex_category(basename, 'nom', comptoir_only=False)


def export(args):
    ddbm = dolibarr_DB_manager()
    if args.format == 'csv':
        ddbm.gen_csv_osm(args.output)
    elif args.format == 'json':
        ddbm.gen_json_gogo(args.output)
    elif args.format == 'tex':
        ddbm.gen_tex_gogo(args.output)


def update(args):
    ddbm = dolibarr_DB_manager()
    list_soc = ddbm.fetch_societe_no_gps(only_presta=True)
    ddbm.update_gps(args, list_soc)


def status(args):
    ddbm = dolibarr_DB_manager()
    list_soc = ddbm.fetch_societe_no_gps(only_presta=not args.show_all)
    ddbm.print_soc(list_soc)


def build_parser():
    # create the top-level parser
    parser = argparse.ArgumentParser(prog='manage_dolibarr_db')
    subparsers = parser.add_subparsers(help='sub-command help')
    # create the parser for the "status" command
    parser_status = subparsers.add_parser('status',
                                          help='Shows all companies (only presta by default) with no valid GPS data')
    parser_status.add_argument('-a', '--show_all', help='Shows all companies without valid GPS data',
                               action="store_true")
    parser_status.set_defaults(func=status)

    # create the parser for the "export" command
    parser_export = subparsers.add_parser('export', help='Export data from the Dolibarr DB')
    parser_export.add_argument('-f', '--format', type=str, default="json", choices=['json', 'csv', 'tex'],
                               help='Format of the file generated (default json)')
    parser_export.add_argument('-o', '--output', type=str, default="Prestataires_gps",
                               help='Filename for the data exported (default Prestataires_gps)')
    parser_export.set_defaults(func=export)

    # create the parser for the "update" command
    parser_update = subparsers.add_parser('update', help='Update the Dolibarr DB with GPS info')
    parser_update.add_argument('-i', '--interactive',
                               help='Equivalent to --update_db_with_gps_info but with interactive choice when several matches are available',
                               action="store_true")
    parser_update.add_argument('-d', '--dry_run',
                               help='Shows all modifications that would be committed but dolibarr DB remains untouched',
                               action="store_true")
    parser_update.set_defaults(func=update)

    return parser


if __name__ == "__main__":
    p = build_parser()
    if len(sys.argv[1:]) == 0:
        p.print_help(sys.stderr)
        sys.exit(1)

    args = p.parse_args(sys.argv[1:])
    if args.func != None:
        args.func(args)
