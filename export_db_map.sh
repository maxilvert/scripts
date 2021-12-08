PUBLIC_HTML=/var/www/html
MDDB_DIR=$HOME/scripts
DATE=$(date +%Y-%m-%d)
LOGFILE=$MDDB_DIR/logs/$DATE.log
. $MDDB_DIR/dolibarr_db_pass.sh

mkdir -p $PUBLIC_HTML/$DATE
cd $MDDB_DIR/tex

### generation des annuaires ###
# Gen tex file from Dolibarr DB
python3 $MDDB_DIR/manage_dolibarr_db.py export -f tex -o presta > $LOGFILE 2>&1
# Compile all 3 A4 versions
pdflatex annuaire_category.tex >> $LOGFILE 2>&1
pdflatex annuaire_alpha.tex >> $LOGFILE 2>&1
pdflatex annuaire_code-postal.tex >> $LOGFILE 2>&1

# Gen A5 booklet version based on categories
FNAME=annuaire_category_A5
pdflatex $FNAME.tex
NPAGES=$(pdfinfo $FNAME.pdf | grep Pages | cut -d ':' -f 2)
TO_ADD=$(((4 - NPAGES % 4)%4))
echo $NPAGES $TO_ADD
if [[ $TO_ADD -gt 0 ]]
then
  pdftk A=$FNAME.pdf B=blank.pdf cat A B1-$TO_ADD output pok.pdf 
else
  mv $FNAME.pdf  pok.pdf
fi

pdfbook2 -o 10 -i 110 -t 10 -b 10 pok.pdf
mv pok-book.pdf $FNAME-book.pdf
rm -f pok.pdf 
mv $FNAME.pdf $FNAME-book.pdf annuaire_category.pdf annuaire_alpha.pdf annuaire_code-postal.pdf $PUBLIC_HTML/$DATE


#generation des donnees pour la mise a jour des cartes
cd $PUBLIC_HTML/$DATE
python3 $MDDB_DIR/manage_dolibarr_db.py export -f json >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py export -f csv >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py update --dry_run >> $LOGFILE 2>&1
cd ..
rm current
ln -s $DATE current
