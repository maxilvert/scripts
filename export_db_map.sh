PUBLIC_HTML=/var/www/html
MDDB_DIR=$HOME/scripts
DATE=$(date +%Y-%m-%d)
LOGFILE=$MDDB_DIR/logs/$DATE.log
. $MDDB_DIR/dolibarr_db_pass.sh

mkdir -p $PUBLIC_HTML/$DATE
cd $MDDB_DIR/tex

#generation des annuaires
python3 $MDDB_DIR/manage_dolibarr_db.py export -f tex -o presta > $LOGFILE 2>&1
pdflatex annuaire_category.tex >> $LOGFILE 2>&1
pdflatex annuaire_alpha.tex >> $LOGFILE 2>&1
pdfbook2 -o 10 -i 110 -t 10 -b 10 annuaire_category.pdf >> $LOGFILE 2>&1
pdfbook2 -o 10 -i 110 -t 10 -b 10 annuaire_alpha.pdf >> $LOGFILE 2>&1
mv *.pdf $PUBLIC_HTML/$DATE


#generation des donnees pour la mise a jour des cartes
cd $PUBLIC_HTML/$DATE
python3 $MDDB_DIR/manage_dolibarr_db.py export -f json >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py export -f csv >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py update --dry_run >> $LOGFILE 2>&1
cd ..
ls
rm current
ln -s $DATE current
